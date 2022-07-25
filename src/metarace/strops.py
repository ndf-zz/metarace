# SPDX-License-Identifier: MIT
"""String filtering, truncation and padding."""

# Note: These functions consider unicode string length and
#       displayed string length to be equal, so any string with zero
#	length characters (eg combining) will be incorrectly
#	truncated and/or padded. Output to fixed-width displays
#	like DHI and track announce will be incorrect.

import re
from random import randint

# replace codepoints 0->255 with space unless overridden
# "protective" against unencoded ascii strings and control chars
SPACEBLOCK = ''
for i in range(0, 256):
    SPACEBLOCK += chr(i)


# unicode translation 'map' class
class unicodetrans(object):

    def __init__(self, keep='', replace=SPACEBLOCK, replacechar=' '):
        self.comp = dict((ord(c), replacechar) for c in replace)
        for c in keep:
            self.comp[ord(c)] = c

    def __getitem__(self, k):  # override to return a None
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
    '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', '', '')
BIBSERLIST_UTRANS = unicodetrans(
    '.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz')
WEBFILE_UTRANS = unicodetrans(
    '_0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz', '.',
    '_')
# special case: map controls and spaces, but keep everything else
PRINT_UTRANS = {}
for cp in range(0, 0x20):
    PRINT_UTRANS[cp] = ' '
for cp in range(0x7f, 0xa1):
    PRINT_UTRANS[cp] = ' '
for cp in range(0x2000, 0x200B):
    PRINT_UTRANS[cp] = ' '
PRINT_UTRANS[0x1680] = ' '
PRINT_UTRANS[0x180e] = ' '
PRINT_UTRANS[0x202f] = ' '
PRINT_UTRANS[0x205f] = ' '
PRINT_UTRANS[0x3000] = ' '
PRINT_UTRANS[0xffa0] = ' '

# timing channels - this duplicates defs in timy
CHAN_START = 0
CHAN_INT = 9
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

DNFCODEMAP = {'otl': 0, 'dsq': 1, 'dnf': 3, 'dns': 4, '': 2}


def cmp_no(x, y):
    """Replicate py2 cmp() for numeric quantities."""
    if x == y:
        return 0
    elif x < y:
        return -1
    else:
        return 1


def cmp_dnf(x, y):
    """Comparison func for two dnf codes."""
    if x not in DNFCODEMAP:
        x = ''
    if y not in DNFCODEMAP:
        y = ''
    return cmp_no(DNFCODEMAP[x], DNFCODEMAP[y])


def rand_key(data=None):
    """Return a random integer key for shuffling."""
    return randint(0, 0xffffffff)


def riderno_key(bib):
    """Return a comparison key for sorting rider number strings."""
    return bibstr_key(bib)


def dnfcode_key(code):
    """Return a rank/dnf code sorting key."""
    # rank [rel] '' dsq hd|otl dnf dns
    dnfordmap = {
        'rel': 8000,
        '': 8500,
        'otl': 8800,
        'dnf': 9000,
        'dns': 9500,
        'dsq': 10000,
    }
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
        sval = ord(ser[0]) << 12
    return sval | (bval & 0xfff)


def randstr(data=None):
    """Return a string of random digits."""
    return str(randint(10000, 99999))


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
    return (riderno_key(hv[0]), riderno_key(hv[1]))


def fitname(first, last, width, trunc=False):
    """Return a truncated name field for fixed-width display.

    Attempts to modify name to fit within width as follows:

    'First Lastone-Lasttwo'

	1: Split lastname ->	'First Lasttwo'
	2: Abbreviate first -> 	'F. Lastone-Lasttwo'
	3: Both ->		'F. Lasttwo'

    If trunc is set, truncate and replace final char with
    ellipsis '\u2026':		'F. Lastt...'
    """
    ret = ''
    fstr = first.strip().title()
    lstr = last.strip().upper()
    if len(fstr) + len(lstr) >= width:
        lshrt = lstr.split('-')[-1].strip()
        if len(fstr) + len(lshrt) >= width:
            fshrt = fstr
            if fstr and len(fstr) > 1:
                fshrt = fstr[0] + '.'
            if len(fshrt) + len(lstr) >= width:
                lstr = lshrt
                if len(fstr) + len(lshrt) >= width:
                    # Abbrev first with split last
                    fstr = fshrt
                else:
                    # Full first with split last
                    pass
            else:
                # Abbrev first with full last
                fstr = fshrt
        else:
            # Full first with split last
            lstr = lshrt
    ret = ' '.join([fstr, lstr]).strip()
    if trunc and len(ret) > width:
        if width > 4:
            ret = ret[0:(width - 1)] + '\u2026'  # Ellipsis
        else:
            ret = ret[0:width]
    return ret


def drawno_encirc(drawstr=''):
    ret = ''
    try:
        if drawstr.isdigit():
            ret = drawstr
            ival = int(drawstr)
            if ival > 0 and ival <= 10:
                ret = (
                    '\u00a0' +  # nbsp to get full line height
                    chr(0x245f + ival))  # CP U+2460 "Circled digit"
    except Exception:
        pass
    return ret


def rank2ord(place):
    """Return ordinal for the given place."""
    omap = {
        '1': 'st',
        '2': 'nd',
        '3': 'rd',
        '11': 'th',
        '12': 'th',
        '13': 'th'
    }
    ret = place
    if place.isdigit():
        if len(place) > 1 and place[-2:] in omap:
            ret = place + omap[place[-2:]]
        else:
            if len(place) > 1 and place[-1] in omap:  # last digit 1,2,3
                ret = place + omap[place[-1]]
            else:
                ret = place + 'th'
    return ret


def rank2int(rank):
    """Convert a rank/placing string into an integer."""
    ret = None
    try:
        ret = int(rank.replace('.', ''))
    except Exception:
        pass
    return ret


def mark2int(handicap):
    """Convert a handicap string into an integer number of metres."""
    handicap = handicap.strip().lower()
    ret = None  # not recognised as handicap
    if handicap != '':
        if handicap[0:3] == 'scr':  # 'scr{atch}'
            ret = 0
        else:  # try [number]m form
            handicap = handicap.translate(INTEGER_UTRANS).strip()
            try:
                ret = int(handicap)
            except Exception:
                pass
    return ret


def truncpad(srcline, length, align='l', ellipsis=True):
    """Return srcline truncated and padded to length, aligned as requested."""
    # truncate
    if len(srcline) > length:
        if ellipsis and length > 4:
            ret = srcline[0:(length - 1)] + '\u2026'  # Ellipsis
        else:
            ret = srcline[0:length]
    else:
        # pad
        if len(srcline) < length:
            if align == 'l':
                ret = srcline.ljust(length)
            elif align == 'r':
                ret = srcline.rjust(length)
            else:
                ret = srcline.center(length)
        else:
            ret = srcline
    return ret


def resname_bib(bib, first, last, club):
    """Return rider name formatted for results with bib."""
    ret = [bib, ' ', fitname(first, last, 64)]
    if club is not None and club != '':
        if len(club) < 4:
            club = club.upper()
        ret.extend([' (', club, ')'])
    return ''.join(ret)


def resname(first, last=None, club=None):
    """Return rider name formatted for results."""
    ret = fitname(first, last, 64)
    if club is not None and club != '':
        if len(club) < 4:
            club = club.upper()
        ret = ''.join([ret, ' (', club, ')'])
    return ret


def listname(first, last=None, club=None):
    """Return a rider name summary field for non-edit lists."""
    ret = fitname(first, last, 32)
    if club:
        if len(club) < 4:
            club = club.upper()
        ret = ''.join([ret, ' (', club, ')'])
    return ret


def reformat_bibserlist(bibserstr):
    """Filter and return a bib.ser start list."""
    return ' '.join(bibserstr.translate(BIBSERLIST_UTRANS).split())


def reformat_bibserplacelist(placestr):
    """Filter and return a canonically formatted bib.ser place list."""
    if '-' not in placestr:  # This is the 'normal' case!
        return reformat_bibserlist(placestr)
    # otherwise, do the hard substitutions...
    placestr = placestr.translate(PLACESERLIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)  # remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)  # combine dupes
    return ' '.join(placestr.strip('-').split())


def reformat_biblist(bibstr):
    """Filter and return a canonically formatted start list."""
    return ' '.join(bibstr.translate(BIBLIST_UTRANS).split())


def riderlist_split(riderstr, rdb=None, series=''):
    """Filter, search and return a list of matching riders for entry."""
    ret = []
    riderstr = riderstr.lower()

    # special case: 'all' -> return all riders from the specified series.
    if rdb is not None and riderstr.strip() == 'all':
        riderstr = ''
        for r in rdb:
            if r[5] == series:
                ret.append(r[0])

    # pass 1: search for categories
    if rdb is not None:
        for cat in sorted(rdb.listcats(series), key=len, reverse=True):
            if len(cat) > 0 and cat.lower() in riderstr:
                ret.extend(rdb.biblistfromcat(cat, series))
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
                                ret.append(str(c))
                                c += 1
                        else:
                            ret.append(l)
                    else:
                        # one or both not ints
                        ret.append(l)
                else:
                    pass
                l = r
            if l is not None:  # catch final value
                ret.append(l)
        else:
            ret.append(nr)
    return ret


def placeset(spec=''):
    """Convert a place spec into an ordered set of place ints."""

    # NOTE: ordering of the set must be retained to correctly handle
    #       autospecs where the order of the places is not increasing
    #       eg: sprint semi -> sprint final, the auto spec is: 3,1,2,4
    #       so the 'winners' go to the gold final and the losers to the
    #       bronze final.
    ret = []
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
                                ret.append(str(c))
                                c += 1
                        else:
                            ret.append(l)  # give up on last val
                    else:
                        # one or both not ints
                        ret.append(l)
                else:
                    pass
                l = r
            if l is not None:  # catch final value
                ret.append(l)
        else:
            ret.append(nr)
    # pass 2: filter out non-numbers, only places considered
    rset = []
    for i in ret:
        if i.isdigit():
            ival = int(i)
            if ival not in rset:
                rset.append(ival)
    return rset


def reformat_placelist(placestr):
    """Filter and return a canonically formatted place list."""
    if '-' not in placestr:
        return reformat_biblist(placestr)
    # otherwise, do the hard substitutions...
    placestr = placestr.translate(PLACELIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)  # remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)  # combine dupes
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


def confopt_str(confob, default=None):
    """Check and return a plain string for the provided value."""
    ret = default
    if isinstance(confob, str):
        ret = confob
    return ret


def confopt_riderno(confstr, default=''):
    """Check and return rider number, filtered only."""
    return confstr.translate(RIDERNO_UTRANS).strip()


def confopt_float(confstr, default=None):
    """Check and return a floating point number."""
    ret = default
    try:
        ret = float(confstr)
    except Exception:
        pass
    return ret


def confopt_distunits(confstr):
    """Check and return a valid unit from metres or laps."""
    if 'lap' in confstr.lower():
        return 'laps'
    else:
        return 'metres'


def confopt_int(confstr, default=None):
    """Check and return a valid integer."""
    ret = default
    try:
        ret = int(confstr)
    except Exception:
        pass
    return ret


def confopt_posint(confstr, default=None):
    """Check and return a valid positive integer."""
    ret = default
    try:
        ret = int(confstr)
        if ret < 0:
            ret = default
    except Exception:
        pass
    return ret


def confopt_dist(confstr, default=None):
    """Check and return a valid distance unit."""
    return confopt_posint(confstr, default)


def chan2id(chanstr='0'):
    """Return a channel ID for the provided string, without fail."""
    ret = CHAN_UNKNOWN
    if (isinstance(chanstr, str) and len(chanstr) > 1 and chanstr[0] == 'C'
            and chanstr[1].isdigit()):
        ret = int(chanstr[1])
    else:
        try:
            ret = int(chanstr)
        except Exception:
            pass
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
    ret = chan2id(confstr)
    if ret == CHAN_UNKNOWN:
        ret = chan2id(default)
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
    look = confstr.lower()
    if look in list:
        ret = look
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
