
"""String filtering, truncation and padding."""

import re
import os
import random

# replace codepoints 0->255 with space unless overridden
# "protective" against unencoded ascii strings and control chars
SPACEBLOCK = ''
for i in range(0,256):
    SPACEBLOCK += chr(i)

# unicode translation 'map' class
class unicodetrans:
  def __init__(self, keep='', replace=SPACEBLOCK, replacechar=' '):
    self.comp = dict((ord(c),replacechar) for c in replace)
    for c in keep:
        self.comp[ord(c)] = c
  def __getitem__(self, k):	# override to return a None
    return self.comp.get(k)

INTEGER_UTRANS = unicodetrans('-0123456789')
NUMERIC_UTRANS = unicodetrans('-0123456789.e')
PLACELIST_UTRANS = unicodetrans(
'-0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
PLACESERLIST_UTRANS = unicodetrans(
'-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
BIBLIST_UTRANS = unicodetrans(
'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
RIDERNO_UTRANS = unicodetrans(
'0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','','')
BIBSERLIST_UTRANS = unicodetrans(
'.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
WEBFILE_UTRANS = unicodetrans(
'_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','.','_')
# special case: map controls and spaces, but keep everything else
PRINT_UTRANS = {}
for cp in range(0,0x20):
    PRINT_UTRANS[cp] = ' '
for cp in range(0x7f,0xa1):
    PRINT_UTRANS[cp] = ' '
for cp in range(0x2000,0x200B):
    PRINT_UTRANS[cp] = ' '
PRINT_UTRANS[0x1680] = ' '
PRINT_UTRANS[0x180e] = ' '
PRINT_UTRANS[0x202f] = ' '
PRINT_UTRANS[0x205f] = ' '
PRINT_UTRANS[0x3000] = ' '
PRINT_UTRANS[0xffa0] = ' '

# timing channels - this duplicates defs in timy
CHAN_START = 0
CHAN_FINISH = 1
CHAN_PA = 2
CHAN_PB = 3
CHAN_200 = 4
CHAN_100 = 5
CHAN_50 = 0  # TODO: use for AUX line into C0
CHAN_AUX = 6 # channels 6-8 are not connected with original TSW-1 cable
CHAN_7 = 7
CHAN_8 = 8
CHAN_INT = 9  # complete the keypad - a key not from timy
CHAN_UNKNOWN = -1

# running number comparisons
RUNNER_NOS = {
 'red': 0,
 'whi': 1,
 'blu': 2,
 'yel': 3,
 'grn': 4,
 'pin': 5,
 'bla': 6,
 'gry': 7,
 'ora': 8,
 'pur': 9,
 'rdw': 10,
 'blw': 11,
 'ylw': 12,
 'grw': 13
}

# UCI penalties: EN/Track
UCITRACKCODES = {
 'A': 'warning',
 'B': 'fined [amt]',
 'C': 'relegated',
 'D': 'disqualified'
}

UCITRACKPEN = {
 '1': 'for not holding [his] line during the final sprint',
 '2': 'for riding on the blue band during the sprint',
 '3': 'for deliberately riding on the blue band during the race',
 '4': 'for not having held [his] line during the last 200 metres of the race',
 '5': 'for irregular movement to prevent [his] opponent from passing',
 '6': 'for dangerous riding in the final bend',
 '7': 'for dangerous riding during the race',
 '8': "for entering the sprinter's lane when the opponent was already there",
 '9': 'for moving down towards the inside of the track when a rival was already there',
 '10': 'for moving down towards the inside of the track and forcing the other competitor off the track',
 '11': 'for crowding [his] opponent with the intention of causing [him] to slow down',
 '12': 'for moving outward with the intention of forcing the opponent to go up',
 '13': 'for going down too quickly after overtaking [his] opponent',
 '14': 'for deliberate and flagrant fault against [ext]',
 '15': 'for causing the crash of [his] opponent',
 '16': 'for having blocked an opponent',
 '21': 'for pushing [his] rival',
 '17': 'for being late at the start line',
 '19': 'for incorrect gestures',
 '20': 'for incorrect behaviour',
 '23': 'for incorrect behaviour or disrespect towards an official',
 '27': 'for protest with hands off handlebar',
 '30': 'for ignoring commissaires instructions to leave track after being overlapped',
 '31': 'for failure to obey commissaires instructions',
 '32': 'for failing to maintain proper control of the bicycle',
 '33': 'for taking off [his] helmet when on the track after passing the finish line',
 '18': 'for wearing only one number',
 '24': 'for foling or mutilating the race number',
 '22': 'for improper attire/advertising during the protocol ceremony',
 '25': 'for improper advertising on national jersey or short',
 '29': 'for not being ready with extra wheels or other equipment at the start',
 '28': 'for using two persons to give information the the [rider]',
 '29': 'qualified to [event] but did not start without justification'
}

DNFCODEMAP = { 'hd': 0,
               'dsq': 1,
               'dnf': 3,
               'dns': 4,
               '': 2}

def cmp_dnf(x, y):
    """Comparison func for two dnf codes."""
    if x not in DNFCODEMAP:
        x = ''
    if y not in DNFCODEMAP:
        y = ''
    return cmp(DNFCODEMAP[x], DNFCODEMAP[y])
    
def riderno_key(bib):
    """Return a comparison key for sorting rider number strings."""
    return bibstr_key(bib)

def dnfcode_key(code):
    """Return a rank/dnf code sorting key."""
    # rank [rel] '' dsq hd|otl dnf dns
    dnfordmap = {
                 'rel':8000,
                 '':8500,
                 'hd':8800,'otl':8800,
                 'dnf':9000,
                 'dns':9500,
                 'dsq':10000,}
    ret = 0
    if code is not None:
        code = code.lower()
        if code in dnfordmap:
            ret = dnfordmap[code]
        else:
            code = code.strip('.')
            if code.isdigit():
                ret = int(code)
    return ret

def bibstr_key(bibstr=''):
    """Return a comparison key for sorting rider bib.ser strings."""
    (bib, ser) = bibstr2bibser(bibstr)
    bval = 0
    if bib.isdigit():
        bval = int(bib)
    else:
        sbib = bib.translate(INTEGER_UTRANS).strip()
        if sbib and sbib.isdigit():
            bval = int(sbib)
        else:
            if bib.lower()[0:3] in RUNNER_NOS:
                bval = RUNNER_NOS[bib.lower()[0:3]]
            else:
                bval = id(bib)
    sval = 0
    if ser != '':
        sval = ord(ser[0])<<12
    return sval | (bval&0xfff)

def randstr():
    """Return a string of random digits."""
    return str(random.randint(10000,99999))

def promptstr(prompt='', value=''):
    """Prefix a non-empty string with a prompt, or return empty."""
    ret = ''
    if value:
        ret = prompt + ' ' + value
    return ret

def listsplit(liststr=''):
    """Return a split and stripped list."""
    ret = []
    for e in liststr.split(','):
        ret.append(e.strip())
    return ret

def heatsplit(heatstr):
    """Return a failsafe heat/lane pair for the supplied heat string."""
    hv = heatstr.split('.')
    while len(hv) < 2:
        hv.append('0')
    return(riderno_key(hv[0]), riderno_key(hv[1]))
    
def fitname(first, last, width, trunc=False):
    """Return a 'nicely' truncated name field for display.

    Attempts to modify name to fit in width as follows:

    1: 'First Lastone-Lasttwo'    - simple concat
    2: 'First Lasttwo'            - ditch hypenated name
    3: 'First V Lastname'	  - abbrev Von parts
    4: 'F. Lasttwo'               - abbrev first name
    5: 'F Lasttwo'                - get 1 xtra char omit period
    6: 'F. Lasttwo'               - give up and return name for truncation

    If optional param trunc is set and field would be longer than
    width, truncate and replace the last char with elipsis '...'
    Unless only two char longer than field - then just chop final chars

    """
    ret = ''
    fstr = first.strip().title()
    lstr = last.strip().upper()
    trystr = (fstr + ' ' + lstr).strip()
    if len(trystr) > width:
        lstr = lstr.split('-')[-1].strip()	# Hyphen
        trystr = fstr + ' ' + lstr
        if len(trystr) > width:
            lstr = lstr.replace('VON ','V ')	# Von part
            lstr = lstr.replace('VAN ','V ')
            trystr = fstr + ' ' + lstr
            if len(trystr) > width:
                if len(fstr) > 0:		# initial first name
                    trystr = fstr[0] + '. ' + lstr
                else:
                    trystr = lstr
                if len(trystr) == width + 1 and len(fstr) > 0:  # opportunistic
                    trystr = fstr[0] + ' ' + lstr
    if trunc:
        ret = trystr[0:width]
        if width > 4:
            if len(trystr) > width+1:
                ret = trystr[0:(width - 1)] + chr(0x2026)
                ##ret = trystr[0:(width - 3)] + '...'
    else:
        ret = trystr
    return ret

def drawno_encirc(drawstr=''):
    ret = drawstr
    if drawstr.isdigit():	# can toint
        try:
            ival = int(drawstr)
            if ival > 0 and ival <= 10:
                ret = ('\u00a0' + 	# hack to get full line height?
                       chr(0x245f + ival)) # CP U+2460 "Circled digit"
        except:
            pass
    return ret

def num2ord(place):
    """Return ordinal for the given place."""
    omap = { '1' : 'st',
             '2' : 'nd',
             '3' : 'rd',
             '11' : 'th',
             '12' : 'th',
             '13' : 'th' }
    if place in omap:
        return place + omap[place]
    elif place.isdigit():
        if len(place) > 1 and place[-1] in omap: # last digit 1,2,3
            return place + omap[place[-1]]
        else:
            return place + 'th'
    else:
        return place

def rank2int(rank):
    """Convert a rank/placing string into an integer."""
    ret = None
    try:
        ret = int(rank.replace('.',''))
    except:
        pass
    return ret

def mark2int(handicap):
    """Convert a handicap string into an integer number of metres."""
    handicap = handicap.decode('utf-8','replace').strip().lower()
    ret = None				# not recognised as handicap
    if handicap != '':
        if handicap[0:3] == 'scr':		# 'scr{atch}'
            ret = 0
        else:				# try [number]m form
           handicap = handicap.translate(INTEGER_UTRANS).strip()
           try:
               ret = int(handicap)
           except:
               pass
    return ret
       
def truncpad(srcline, length, align='l', elipsis=True):
    """Return srcline truncated and padded to length, aligned as requested."""
    ret = srcline[0:length]
    if length > 6:
        if len(srcline) > length+2 and elipsis:
            ret = srcline[0:(length - 3)] + '...'	# repl with elipsis?
    if align == 'l':
        ret = ret.ljust(length)
    elif align == 'r':
        ret = ret.rjust(length)
    else:
        ret = ret.center(length)
    return ret

def search_name(namestr):
    return str(namestr).translate(RIDERNO_UTRANS).strip().lower().encode('ascii','ignore')

def resname_bib(bib, first, last, club):
    """Return rider name formatted for results with bib (champs/live)."""
    ret = bib + ' ' + fitname(first, last, 64)
    if club is not None and club != '':
        if len(club) < 4:
            club=club.upper()
        ret += ' (' + club + ')'
    return ret

def resname(first, last=None, club=None):
    """Return rider name formatted for results."""
    ret = fitname(first, last, 64)
    if club is not None and club != '':
        if len(club) < 4:
            club=club.upper()
        ret += ' (' + club + ')'
    return ret

def listname(first, last=None, club=None):
    """Return a rider name summary field for non-edit lists."""
    ret = fitname(first, last, 32)
    if club:
        if len(club) < 4:
            club=club.upper()
        ret += ' (' + club + ')'
    return ret

def reformat_bibserlist(bibserstr):
    """Filter and return a bib.ser start list."""
    return ' '.join(bibserstr.decode('utf-8','replace').translate(BIBSERLIST_UTRANS).split())

def reformat_bibserplacelist(placestr):
    """Filter and return a canonically formatted bib.ser place list."""
    placestr = placestr.decode('utf-8', 'replace')
    if '-' not in placestr:		# This is the 'normal' case!
        return reformat_bibserlist(placestr)
    # otherwise, do the hard substitutions...
    # TODO: allow the '=' token to indicate RFPLACES ok 
    placestr = placestr.translate(PLACESERLIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)	# remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)		# combine dupes
    return ' '.join(placestr.strip('-').split())

def reformat_biblist(bibstr):
    """Filter and return a canonically formatted start list."""
    return ' '.join(bibstr.decode('utf-8','replace').translate(BIBLIST_UTRANS).split())

def reformat_riderlist(riderstr, rdb=None, series=''):
    """Filter, search and return a list of matching riders for entry."""
    ret = ''
    ##riderstr = riderstr.translate(PLACELIST_TRANS).lower()
    riderstr = riderstr.decode('utf-8', 'replace').lower()

    # special case: 'all' -> return all riders from the sepcified series.
    if rdb is not None and riderstr.strip().lower() == 'all':
        riderstr = ''
        for r in rdb:
            if r[5] == series:
                ret += ' ' + r[0]
    
    # pass 1: search for categories
    if rdb is not None:
        for cat in sorted(rdb.listcats(series), key=len, reverse=True):
            if len(cat) > 0 and cat.lower() in riderstr:
                ret += ' ' + rdb.biblistfromcat(cat, series)
                riderstr = riderstr.replace(cat.lower(), '')

    # pass 2: append riders and expand any series if possible
    riderstr = reformat_placelist(riderstr)
    for nr in riderstr.split():
        if '-' in nr:
            # try for a range...
            l = None
            n = None
            for r in nr.split('-'):
                if l is not None:
                    if l.isdigit() and r.isdigit():
                        start = int(l)
                        end = int(r)
                        if start < end:
                            c = start
                            while c < end:
                                ret += ' ' + str(c)
                                c += 1
                        else:
                            ret += ' ' + l	# give up on last val
                    else:
                        # one or both not ints
                        ret += ' ' + l
                else:
                    pass
                l = r
            if l is not None: # catch final value
                ret += ' ' + l
        else:
            ret += ' ' + nr
    # pass 3: reorder and join for return
    #rvec = list(set(ret.split()))
    ##rvec.sort(key=riderno_key)	# don't lose ordering for seeds
    #return u' '.join(rvec)
    return ret

def placeset(spec=''):
    """Convert a place spec into an ordered set of place ints."""

    # NOTE: ordering of the set must be retained to correctly handle
    #       autospecs where the order of the places is not increasing
    #       eg: sprint semi -> sprint final, the auto spec is: 3,1,2,4
    #       so the 'winners' go to the gold final and the losers to the
    #       bronze final.
    spec = spec.decode('utf-8','replace')
    ret = ''
    spec = reformat_placelist(spec)
    # pass 1: expand ranges
    for nr in spec.split():
        if '-' in spec:
            # try for a range...
            l = None
            n = None
            for r in nr.split('-'):
                if l is not None:
                    if l.isdigit() and r.isdigit():
                        start = int(l)
                        end = int(r)
                        if start < end:
                            c = start
                            while c < end:
                                ret += ' ' + str(c)
                                c += 1
                        else:
                            ret += ' ' + l	# give up on last val
                    else:
                        # one or both not ints
                        ret += ' ' + l
                else:
                    pass
                l = r
            if l is not None: # catch final value
                ret += ' ' + l
        else:
            ret += ' ' + nr
    # pass 2: filter out non-numbers
    rset = []
    for i in ret.split():
        if i.isdigit():
            ival = int(i)
            if ival not in rset:
                rset.append(ival)
    return rset

def reformat_placelist(placestr):
    """Filter and return a canonically formatted place list."""
    placestr = placestr.decode('utf-8','replace')
    if '-' not in placestr:		# This is the 'normal' case!
        return reformat_biblist(placestr)
    # otherwise, do the hard substitutions...
    placestr = placestr.translate(PLACELIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)	# remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)		# combine dupes
    return ' '.join(placestr.strip('-').split())

def confopt_bool(confstr):
    """Check and return a boolean option from config."""
    if isinstance(confstr, str):
        if confstr.lower() in ['yes', 'true', '1']:
            return True
        else:
            return False
    else:
        return bool(confstr)

def plural(count=0):
    """Return plural extension for provided count."""
    ret = 's'
    if count == 1:
        ret = ''
    return ret

def confopt_riderno(confstr, default=''):
    """Check and return rider number, filtered only."""
    return confstr.translate(RIDERNO_UTRANS).strip()

def confopt_float(confstr, default=None):
    """Check and return a floating point number."""
    ret = default
    try:
        ret = float(confstr)
    except:	# catches the float(None) problem
        pass
    return ret

def confopt_distunits(confstr):
    """Check and return a valid unit from metres or laps."""
    if confstr.lower() == 'laps':
        return 'laps'
    else:
        return 'metres' 

def confopt_int(confstr, default=None):
    """Check and return a valid integer."""
    ret = default
    try:
        ret = int(confstr)
    except:
        pass	# ignore errors and fall back on default
    return ret

def confopt_posint(confstr, default=None):
    """Check and return a valid positive integer."""
    ret = default
    try:
        ret = int(confstr)
        if ret < 0:
            ret = default
    except:
        pass	# ignore errors and fall back on default
    return ret

def confopt_dist(confstr, default=None):
    """Check and return a valid distance unit."""
    return confopt_posint(confstr, default)

def chan2id(chanstr='0'):
    """Return a channel ID for the provided string, without fail."""
    ret = CHAN_UNKNOWN
    if (isinstance(chanstr, str) and len(chanstr) > 1
        and chanstr[0] == 'C' and chanstr[1].isdigit()):
        ret = int(chanstr[1])
    else:
        try:
            ret = int(chanstr)
        except:
            pass # other errors will re-occur later anyhow
    if ret < CHAN_UNKNOWN or ret > CHAN_INT:
        ret = CHAN_UNKNOWN
    return ret

def id2chan(chanid=0):
    """Return a normalised channel string for the provided channel id."""
    ret = 'C?'
    if isinstance(chanid, int) and chanid >= CHAN_START and chanid <= CHAN_INT:
        ret = 'C' + str(chanid)
    return ret

def confopt_chan(confstr, default=None):
    """Check and return a valid timing channel id string."""
    ret = chan2id(default)
    ival = chan2id(confstr)
    if ival != CHAN_UNKNOWN:
        ret = ival
    return ret

def confopt_pair(confstr, value, default=None):
    """Return value or the default."""
    ret = default
    if confstr.lower() == value.lower():
        ret = value
    return ret

def confopt_list(confstr, list=[], default=None):
    """Return an element from list or default."""
    ret = default
    for elem in list:
        if confstr.lower() == elem.lower():
            ret = elem
            break
    return ret

def bibstr2bibser(bibstr=''):
    """Split a bib.series string and return bib and series."""
    a = bibstr.strip().split('.')
    ret_bib = ''
    ret_ser = ''
    if len(a) > 0:
        ret_bib = a[0]
    if len(a) > 1:
        ret_ser = a[1]
    return (ret_bib, ret_ser)

def lapstring(lapcount=None):
    lapstr = ''
    if lapcount:
        lapstr = str(lapcount) + ' Lap'
        if lapcount > 1:
            lapstr += 's'
    return lapstr

def bibser2bibstr(bib='', ser=''):
    """Return a valid bib.series string."""
    ret = bib
    if ser != '':
        ret += '.' + ser
    return ret

def titlesplit(src='', linelen=24):
    """Split a string on word boundaries to try and fit into 3 fixed lines."""
    ret = ['', '', '']
    words = src.split()
    wlen = len(words)
    if wlen > 0:
        line = 0
        ret[line] = words.pop(0)
        for word in words:
            pos = len(ret[line])
            if pos + len(word) >= linelen:
                # new line
                line += 1
                if line > 2:
                    break
                ret[line] = word
            else:
                ret[line] += ' ' + word
    return ret

class countback(object):
    __hash__ = None
    """Simple dict wrapper for countback store/compare."""
    def __init__(self, cbstr=None):
        self.__store = {}
        if cbstr is not None:
            self.fromstring(cbstr)

    def maxplace(self):
        """Return maximum non-zero place."""
        ret = 0
        if len(self.__store) > 0:
            ret = max(self.__store.keys())
        return ret
    def fromstring(self, cbstr):
        propmap = {}
        cbvec = cbstr.split(',')
        if len(cbvec) > 0:
            for i in range(0,len(cbvec)):
                if cbvec[i].isdigit():
                    propmap[i] = int(cbvec[i])
        self.__store = {}
        for k in propmap:
            self.__store[k] = propmap[k]

    def __str__(self):
        ret = []
        for i in range(0,self.maxplace()+1):
            if i in self.__store and self.__store[i] != 0:
                ret.append(str(self.__store[i]))
            else:
                ret.append('-')
        return ','.join(ret)
    def __len__(self):
        return len(self.__store.len)
    def __getitem__(self, key):
        """Use a default value id, but don't save it."""
        if key in self.__store:
            return self.__store[key]
        else:
            return 0
    def __setitem__(self, key, value):
        self.__store[key] = value
    def __delitem__(self, key):
        del(self.__store[key])
    def __iter__(self):
        return iter(self.__store.keys())
    def __contains__(self, item):
        return item in self.__store
    def __lt__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False # assume all same
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a < b
                break
        return ret
    def __le__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True # assume all same
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a < b
                break
        return ret
    def __eq__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            if self[i] != other[i]:
                ret = False
                break
        return ret
    def __ne__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            if self[i] != other[i]:
                ret = True
                break
        return ret
    def __gt__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False # assume all same
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a > b
                break
        return ret
    def __ge__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True # assume all same
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a > b
                break
        return ret
    def __add__(self, other):
        """Add two countbacks together and return a new cb>=self >=other."""
        if not isinstance(other, countback):
            return NotImplemented
        ret = countback(str(self))
        for i in range(0,max(self.maxplace(), other.maxplace())+1):
            ret[i] += other[i]
        return ret

