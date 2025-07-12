# SPDX-License-Identifier: MIT
"""String filtering, truncation and padding."""

import re
from random import randint
import grapheme
from contextlib import suppress

# replace codepoints 0->255 with space unless overridden
# "protective" against unencoded ascii strings and control chars
SPACEBLOCK = ''
for i in range(0, 256):
    SPACEBLOCK += chr(i)


# unicode translation 'map' class
class unicodetrans:

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
# special case: map out controls, but keep everything else
PRINT_UTRANS = {}
for cp in range(0, 0x20):
    PRINT_UTRANS[cp] = ' '
for cp in range(0x7f, 0xa1):
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
    'RED': 0,
    'WHI': 1,
    'BLU': 2,
    'YEL': 3,
    'GRN': 4,
    'PIN': 5,
    'BLA': 6,
    'GRY': 7,
    'ORA': 8,
    'PUR': 9,
    'RDW': 10,
    'BLW': 11,
    'YLW': 12,
    'GRW': 13
}

DNFCODEMAP = {'otl': -1, 'abd': 1, 'dsq': 2, 'dnf': 3, 'dns': 4, '': 0}
_UNPLACEDRANK = 100000  # Arbitrarily large ranking for unplaced


def rand_key(data=None):
    """Return a random integer key for shuffling."""
    return randint(0, 0xffffffff)


def riderno_key(bib):
    """Return a comparison key for sorting rider number strings."""
    return bibstr_key(bib)


def dnfcode_key(code):
    """Return a rank/dnf code sorting key."""
    ret = _UNPLACEDRANK
    if code is not None:
        code = code.lower()
        if code in DNFCODEMAP:
            ret += DNFCODEMAP[code]
        else:
            code = code.rstrip('.')
            with suppress(ValueError, TypeError):
                ret = int(code)
    return ret


def bibstr_key(bibstr=''):
    """Return a comparison key for sorting rider bib.ser strings."""
    bib, ser = bibstr2bibser(bibstr)
    return '% 6s:% 4s' % (ser, bib)


def randstr(data=None):
    """Return a string of random digits."""
    return str(randint(10000, 99999))


def promptstr(prompt='', value=''):
    """Prefix a non-empty string with a prompt, or return empty."""
    ret = ''
    if value:
        ret = prompt + ' ' + value
    return ret


def heatsplit(heatstr):
    """Return a sortable heat/lane pair for the supplied heat string."""
    hv = heatstr.split('.')
    while len(hv) < 2:
        hv.append('0')
    return (int(hv[0]), int(hv[1]))


def fitname(first, last, width, trunc=False):
    """Return a truncated name string of width or less graphemes
       shortened to fit with priority:

          Firstnamer FAMILY-LASTNAME
          Firstnamer LASTNAME
          F. FAMILY-LASTNAME
          F. LASTNAME
          LASTNAME
          F. LAST...
    """
    # Note: Use rider.fitname() for a caching version

    # Full name: 'Firstname FAMILY-LASTNAME'
    ret = ''
    fn = first.strip().title()
    fl = grapheme.length(fn)
    ln = last.strip().upper()
    ll = grapheme.length(ln)
    flen = fl + ll
    if fl and ll:
        flen += 1
    if flen > width:
        # Try without hyphen: 'Firstname LASTNAME'
        lshrt = ln.split('-')[-1].strip()
        lsl = grapheme.length(lshrt)
        flen = fl + lsl
        if fl and lsl:
            flen += 1
        if flen > width and ln:
            if fl > 2:
                # Retry with abbreviated firstname: 'F. FAMILY-LASTNAME'
                fshrt = grapheme.slice(fn, end=1) + '.'
                fn = fshrt
                fsl = 2
                flen = fsl + ll
                if fsl and ll:
                    flen += 1
        else:
            ln = lshrt
    if fn and ln:
        ret = ' '.join((fn, ln))
    elif fn:
        ret = fn
    else:
        ret = ln
    if trunc and grapheme.length(ret) > width:
        if width > 4:
            ret = grapheme.slice(ret, end=width - 1) + '\u2026'
        else:
            ret = grapheme.slice(ret, end=width)
    return ret


def drawno_encirc(drawstr=''):
    ret = ''
    with suppress(ValueError, TypeError):
        ival = int(drawstr)
        ret = drawstr
        if ival > 0 and ival <= 10:
            ret = (
                '\u00a0' +  # Hack: nbsp to get full line height
                chr(0x245f + ival))  # CP U+2460 "Circled digit"
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
        if place in omap:
            ret = place + omap[place]
        elif len(place) > 1 and place[-2:] in omap:
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
    with suppress(ValueError, TypeError):
        ret = int(rank.replace('.', ''))
    return ret


def mark2int(handicap):
    """Convert a handicap string into an integer number of metres."""
    handicap = handicap.strip().lower()
    ret = None  # not recognised as handicap
    if handicap != '':
        if handicap[0:3] == 'scr':  # 'scr{atch}'
            ret = 0
        else:  # try [number]m form
            with suppress(ValueError, TypeError):
                handicap = handicap.translate(INTEGER_UTRANS).strip()
                ret = int(handicap)
    return ret


def truncpad(srcline, width, align='l', ellipsis=True):
    """Return srcline truncated and padded to width aligned graphemes"""
    curlen = grapheme.length(srcline)
    if curlen > width:
        # truncation
        if ellipsis and width > 4:
            ret = grapheme.slice(srcline, end=width - 1) + '\u2026'
        else:
            ret = grapheme.slice(srcline, end=width)
    elif curlen < width:
        # padding
        residual = width - curlen
        if align == 'r':
            ret = ' ' * residual + srcline
        elif align == 'c':
            prelen = residual // 2
            postlen = residual - prelen
            ret = ' ' * prelen + srcline + ' ' * postlen
        else:
            ret = srcline + ' ' * residual
    else:
        ret = srcline
    return ret


def resname_bib(bib, first, last, club, series=''):
    """Return rider name formatted for results with bib."""
    bibstr = bibser2bibstr(bib, series)
    ret = [bibstr, ' ', fitname(first, last, 48)]
    if club is not None and club != '':
        if len(club) < 4:
            club = club.upper()
        ret.extend([' (', club, ')'])
    return ''.join(ret)


def resname(first, last=None, club=None):
    """Return rider name formatted for results."""
    ret = fitname(first, last, 48)
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
    # otherwise, filter dead heats
    placestr = placestr.translate(PLACESERLIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)  # remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)  # combine dupes
    return ' '.join(placestr.strip('-').split())


def reformat_biblist(bibstr):
    """Filter and return a canonically formatted start list."""
    return ' '.join(bibstr.translate(BIBLIST_UTRANS).split())


def riderlist_split(riderstr, rdb=None, series=''):
    """Filter, search and return a list of matching riders for entry."""
    riderstr = riderstr.upper()
    dstlist = []

    # extract categories and 'all' from riderstr
    if rdb is not None:
        srclist = []
        catnames = rdb.listcats(series)
        for r in riderstr.split():
            if r == 'ALL':
                for rid in rdb.biblistfromseries(series):
                    bib, ser = bibstr2bibser(rid)
                    if ser == series:
                        dstlist.append(bib)
            elif r in catnames:
                for rid in rdb.biblistfromcat(r, series):
                    bib, ser = bibstr2bibser(rid)
                    if ser == series:
                        dstlist.append(bib)
            else:
                srclist.append(r)
        riderstr = ' '.join(srclist)

    # expand ranges in riderstr
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
                                dstlist.append(str(c))
                                c += 1
                        else:
                            dstlist.append(l)
                    else:
                        # one or both not ints
                        dstlist.append(l)
                else:
                    pass
                l = r
            if l is not None:  # catch final value
                dstlist.append(l)
        else:
            dstlist.append(nr)

    ret = []
    rset = set()
    for r in dstlist:
        r = r.upper()
        if r not in rset:
            ret.append(r)
            rset.add(r)
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
    placestr = placestr.translate(PLACELIST_UTRANS).strip()
    placestr = re.sub(r'\s*\-\s*', r'-', placestr)  # remove surrounds
    placestr = re.sub(r'\-+', r'-', placestr)  # combine dupes
    return ' '.join(placestr.strip('-').split())


def confopt_bool(confstr):
    """Check and return a boolean option from config."""
    if isinstance(confstr, str):
        if confstr.lower() in (
                'yes',
                'true',
                '1',
        ):
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
    with suppress(ValueError, TypeError):
        ret = float(confstr)
    return ret


def confopt_posfloat(confstr, default=None):
    """Check and return a positive floating point number."""
    ret = default
    with suppress(ValueError, TypeError):
        nv = float(confstr)
        if nv > 0:
            ret = nv
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
    with suppress(ValueError, TypeError):
        ret = int(confstr)
    return ret


def confopt_posint(confstr, default=None):
    """Check and return a valid positive integer."""
    ret = default
    with suppress(ValueError, TypeError):
        ret = int(confstr)
        if ret < 0:
            ret = default
    return ret


def confopt_dist(confstr, default=None):
    """Check and return a valid distance unit."""
    return confopt_posint(confstr, default)


def chan2id(chanstr='0'):
    """Return a channel ID for the provided string, without fail."""
    ret = CHAN_UNKNOWN
    with suppress(ValueError, TypeError):
        if isinstance(chanstr, str):
            chanstr = chanstr.upper().rstrip('M').lstrip('C')
            if chanstr.isdigit():
                ret = int(chanstr)
        else:
            ret = int(chanstr)
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


def bibstr(bib=''):
    """Reformat and return competitor id"""
    return bibser2bibstr(*bibstr2bibser(bib))


def bibstr2bibser(bibstr=''):
    """Split a bib.series string and return bib and series."""
    a = bibstr.strip().split('.')
    ret_bib = ''
    ret_ser = ''
    if len(a) > 0:
        ret_bib = a[0].upper()
    if len(a) > 1:
        ret_ser = a[1].lower()
    return (ret_bib, ret_ser)


def bibser2bibstr(bib='', ser=''):
    """Return a competitor bib.series string."""
    ret = bib.upper()
    if ser != '':
        ret += '.' + ser.lower()
    return ret


def lapstring(lapcount=None):
    lapstr = ''
    if lapcount:
        lapstr = '%d\u2006Lap%s' % (
            lapcount,
            plural(lapcount),
        )
    return lapstr


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
