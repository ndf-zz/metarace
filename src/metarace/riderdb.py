# SPDX-License-Identifier: MIT
"""CSV-backed Competitor and Category Data"""

import logging
import os
import csv
from unicodedata import normalize
import grapheme

import metarace
from metarace import strops

_log = logging.getLogger('metarace.riderdb')
_log.setLevel(logging.DEBUG)

# default values when columns omitted
_RIDER_DEFAULTS = {}

# Rider column headings
_RIDER_COLUMNS = {
    'no': 'Rider No',
    'series': 'Series',
    'first': 'First Name',
    'last': 'Last Name',
    'org': 'Organisation',
    'cat': 'Categories',
    'nat': 'Nationality',
    'ref': 'Refid/Transponder',
    'uci': 'UCI ID',
    'dob': 'DoB',
    'sex': 'Sex',
    'note': 'Notes',
}

# Category column headings
_CATEGORY_COLUMNS = {
    'no': 'ID',
    'series': 'Series',
    'first': 'Title',
    'last': 'Subtitle',
    'org': 'Lap Prefix',
    'cat': 'Target Laps',
    'nat': 'Nationality',
    'uci': 'Start Offset',
    'ref': 'Distance',
    'note': 'Footer',
    'dob': 'DoB',
    'sex': 'Sex',
}

# legacy csv file ordering
_DEFAULT_COLUMN_ORDER = [
    'no', 'first', 'last', 'org', 'cat', 'series', 'ref', 'uci', 'dob', 'nat',
    'sex', 'note'
]

# Alternative column header strings lookup
_ALT_COLUMNS = {
    'id': 'no',
    'rid': 'no',
    'num': 'no',
    'cid': 'no',
    'cod': 'no',
    'bib': 'no',
    'ind': 'no',
    'no.': 'no',
    'ser': 'series',
    'typ': 'series',
    'fir': 'first',
    'nam': 'first',
    'tit': 'first',
    'las': 'last',
    'sub': 'last',
    'sur': 'last',
    'clu': 'org',
    'tea': 'org',
    'lap': 'org',
    'tar': 'cat',
    'lic': 'uci',
    'sta': 'uci',
    'rfi': 'ref',
    'tra': 'ref',
    'dis': 'ref',
    'gen': 'sex',
    'dat': 'dob',
    'not': 'note',
    'foo': 'note',
}


def colkey(colstr=''):
    """Convert a column header string to a colkey."""
    col = colstr[0:3].lower()
    if col in _ALT_COLUMNS:
        col = _ALT_COLUMNS[col]
    return col


def get_header(cols=_DEFAULT_COLUMN_ORDER, hdrs=_RIDER_COLUMNS):
    """Return a row of header strings for the provided cols."""
    return (hdrs[colkey(c)] for c in cols)


def cellnorm(unistr):
    """Normalise supplied string, then return a version with printing chars."""
    return normalize('NFC', unistr).translate(strops.PRINT_UTRANS)


class rider():
    """Rider handle."""

    def get_id(self):
        """Return this rider's unique id"""
        return (self.__store['no'].lower(), self.__store['series'].lower())

    def get_key(self):
        """Return a sorting key for this rider number"""
        return strops.bibstr_key(self.__store['no'])

    def primary_cat(self):
        """Return rider's primary category"""
        ret = ''
        cv = self['cat'].split()
        if cv:
            ret = cv[0].upper()
        return ret

    def get_cats(self):
        """Return a list of categories for this rider"""
        return (c.upper() for c in self['cat'].split())

    def get_row(self, coldump=_DEFAULT_COLUMN_ORDER):
        """Return a row ready to export."""
        return (str(self[c]) for c in coldump)

    def set_notify(self, callback=None):
        """Set or clear the notify callback for the event."""
        if callback is not None:
            self.__notify = callback
        else:
            self.__notify = self.__def_notify

    def get_value(self, key):
        """Alternate value fetch."""
        return self.__getitem__(key)

    def set_value(self, key, value):
        """Update a value without triggering notify."""
        key = colkey(key)
        self.__store[key] = value

    def notify(self):
        """Forced notify."""
        self.__notify(self.get_id())

    def __init__(self, cols={}, no='', series='', notify=None):
        self.__strcache = {}
        self.__store = dict(cols)
        self.__notify = self.__def_notify
        if 'no' not in self.__store:
            self.__store['no'] = no
        if 'series' not in self.__store:
            self.__store['series'] = series
        if notify is not None:
            self.__notify = notify

    def fitname(self, width, trunc=False):
        """Return a truncated name string of width or less graphemes"""
        ret = None
        nkey = ('fn', width, trunc)
        if nkey not in self.__strcache:
            fn = self['first'].strip().title()
            fl = grapheme.length(fn)
            ln = self['last'].strip().upper()
            ll = grapheme.length(ln)
            if fl + ll >= width:
                lshrt = ln.split('-')[-1].strip()
                lsl = grapheme.length(lshrt)
                ln = lshrt
                if fl + lsl >= width:
                    if fl > 2:
                        fn = grapheme.slice(fn, end=1) + '.'
            ret = ' '.join((fn, ln))
            if trunc and grapheme.length(ret) > width:
                if width > 4:
                    ret = grapheme.slice(ret, end=width - 1) + '\u2026'
                else:
                    ret = grapheme.slice(ret, end=width)
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def __str__(self):
        return '{} {} {} ({})'.format(
            strops.bibser2bibstr(self.__store['no'], self.__store['series']),
            self['first'].title(), self['last'].upper(), self['org'].upper())

    def __repr__(self):
        return 'rider({})'.format(self.__store)

    def __len__(self):
        return len(self.__store)

    def __getitem__(self, key):
        """Use a default value id, but don't save it."""
        key = colkey(key)
        if key in self.__store:
            return self.__store[key]
        elif key in _RIDER_DEFAULTS:
            return _RIDER_DEFAULTS[key]
        else:
            return ''

    def __setitem__(self, key, value):
        key = colkey(key)
        self.__store[key] = value
        if key in ['first', 'last', 'org']:
            self.__strcache = {}
        self.__notify(self.get_id())

    def __delitem__(self, key):
        key = colkey(key)
        del (self.__store[key])
        if key in ['fir', 'las', 'org']:
            self.__strcache = {}
        self.__notify(self.get_id())

    def __iter__(self):
        return iter(self.__store.keys())

    def iterkeys(self):
        return iter(self.__store.keys())

    def __contains__(self, item):
        key = colkey(item)
        return key in self.__store

    def __def_notify(self, data=None):
        pass


class riderdb():
    """Rider database."""

    def clear(self):
        """Clear rider model."""
        self.__store = {}
        _log.debug('Rider model cleared')
        self.__notify(None)

    def add_rider(self, newrider, notify=True):
        """Append newrider to model."""
        rid = newrider.get_id()
        if rid in self.__store:
            _log.warning('Duplicate rider entry: %r', rid)
            rid = (newrider['no'], '-'.join(('dupe', strops.randstr())))
        newrider.set_notify(self.__notify)
        self.__store[rid] = newrider
        if notify:
            self.__notify(rid)
        return rid

    def __loadrow(self, r, colspec):
        nr = rider()
        for i in range(0, len(colspec)):
            if len(r) > i:  # column data in row
                val = cellnorm(r[i])
                key = colspec[i]
                nr[key] = val
        if nr['no']:
            if colkey(nr['no']) in _RIDER_COLUMNS:
                _log.debug('Ignore column header: %r', r)
                return
        else:
            _log.warning('Rider without number: %r', nr)
        self.add_rider(nr, notify=False)

    def load(self, csvfile=None):
        """Load riders from supplied CSV file."""
        if not os.path.isfile(csvfile):
            _log.debug('Riders file %r not found', csvfile)
            return
        _log.debug('Loading riders from %r', csvfile)
        with open(csvfile, 'r', encoding='utf-8') as f:
            cr = csv.reader(f)
            incols = None  # no header
            for r in cr:
                if len(r) > 0:  # got a data row
                    if incols is not None:  # already got col header
                        self.__loadrow(r, incols)
                    else:
                        # determine input column structure
                        if colkey(r[0]) in _RIDER_COLUMNS:
                            incols = []
                            for col in r:
                                incols.append(colkey(col))
                        else:
                            incols = _DEFAULT_COLUMN_ORDER  # assume full
                            self.__loadrow(r, incols)
        self.__notify(None)

    def save(self, csvfile=None, columns=None):
        """Save current model content to CSV file."""
        _log.debug('Saving riders to %r', csvfile)
        cats = []
        if columns is None:
            columns = self.include_cols
        with metarace.savefile(csvfile) as f:
            cr = csv.writer(f, quoting=csv.QUOTE_ALL)
            cr.writerow(get_header(columns))
            for r in self.__store.values():
                if r['series'] == 'cat':
                    cats.append(r)
                else:
                    cr.writerow(r.get_row(columns))

            if cats:
                cr.writerow(get_header(columns, _CATEGORY_COLUMNS))
                for r in cats:
                    cr.writerow(r.get_row(columns))

    def __len__(self):
        return len(self.__store)

    def __getitem__(self, key):
        return self.__store[key]

    def __setitem__(self, key, value):
        self.__store[key] = value  # no change to key
        self.__notify(key)

    def __delitem__(self, key):
        del (self.__store[key])
        self.__notify(None)

    def __iter__(self):
        return self.__store.__iter__()

    def get_cat(self, catid):
        """Return a handle to a category entry, or None"""
        return self.get_rider(catid, 'cat')

    def next_rider(self, riderno, series=None):
        """Try to return next rider from series"""
        ret = None
        curid = self.get_id(riderno, series)
        if curid is not None:
            curSeries = curid[1]
            aux = []
            count = 0
            for r in self.__store:
                if curSeries == r[1]:
                    aux.append((strops.bibstr_key(r[0]), count, r))
                    count += 1
            aux.sort()
            i = 0
            rv = None
            while i < len(aux) - 1:
                if aux[i][2] == curid:
                    rv = i + 1
                    break
                i += 1
            if rv is not None:
                ret = aux[rv][2]
        return ret

    def add_empty(self, riderno, series=None):
        """Add a new entry for this rider and series"""
        ret = None
        if series is None:
            riderno, series = strops.bibstr2bibser(riderno)
        nr = rider(no=riderno, series=series)
        return self.add_rider(nr)

    def get_rider(self, riderno, series=None):
        """If rider exists, return handle else return None"""
        ret = None
        rkey = self.get_id(riderno, series)
        if rkey in self.__store:
            ret = self.__store[rkey]
        return ret

    def get_id(self, riderno, series=None):
        """If rider exists, return id else return None"""
        ret = None
        if series is None:
            riderno, series = strops.bibstr2bibser(riderno)
        rkey = (riderno.lower(), series.lower())
        if rkey in self.__store:
            ret = rkey
        return ret

    def iterkeys(self):
        return self.__store.iterkeys()

    def __contains__(self, item):
        return item in self.__store

    def set_notify(self, cb=None):
        """Set the data change notification callback."""
        if cb is None:
            cb = self.__defnotify
        self.__notify = cb
        for ev in self:
            ev.set_notify(cb)

    def __def_notify(self, data=None):
        """Handle changes in db."""
        _log.debug('Notify: %r', data)

    def __init__(self, racetypes=None):
        """Constructor for the event db."""
        self.__store = {}
        self.__notify = self.__def_notify
        self.include_cols = _DEFAULT_COLUMN_ORDER
