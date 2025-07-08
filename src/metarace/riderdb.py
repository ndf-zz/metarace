# SPDX-License-Identifier: MIT
"""CSV-backed Competitor and Category Data"""

import logging
import os
import csv
from unicodedata import normalize
import grapheme

import metarace
from metarace import strops

_log = logging.getLogger('riderdb')
_log.setLevel(logging.DEBUG)

# default values when columns omitted
_RIDER_DEFAULTS = {}

# Internal rider column keys
_RIDER_COLUMNS = {
    'no': 'Rider No',
    'series': 'Series',
    'first': 'First Name',
    'last': 'Last Name',
    'org': 'Organisation',
    'cat': 'Categories',
    'nat': 'Nationality',
    'ref': 'Transponder',
    'uci': 'UCI ID',
    'dob': 'DoB',
    'sex': 'Sex',
    'note': 'Notes',
    'seed': 'Seeding',
    'data': 'Data Reference',
}

# Column strings lookup
_ALT_COLUMNS = {
    'id': 'no',
    'ride': 'no',
    'numb': 'no',
    'cid': 'no',
    'code': 'no',
    'bib': 'no',
    'inde': 'no',
    'no.': 'no',
    'seri': 'series',
    'type': 'series',
    'firs': 'first',
    'name': 'first',
    'titl': 'first',
    'last': 'last',
    'subt': 'last',
    'surn': 'last',
    'orga': 'org',
    'club': 'org',
    'team': 'org',
    'laps': 'org',
    'lap': 'org',
    'cats': 'cat',
    'cate': 'cat',
    'targ': 'cat',
    'lice': 'uci',
    'star': 'uci',
    'ucii': 'uci',
    'refi': 'ref',
    'rfid': 'ref',
    'tran': 'ref',
    'dist': 'ref',
    'disp': 'ref',
    'gend': 'sex',
    'nati': 'nat',
    'note': 'note',
    'foot': 'note',
    'memb': 'note',
    'rank': 'seed',
    'data': 'data',
    'date': 'dob',
}

# Category columns
_CATEGORY_COLUMNS = {
    'no': 'ID',
    'series': 'Series',
    'first': 'Title',
    'last': 'Subtitle',
    'note': 'Footer',
    'org': 'Lap Prefix',
    'ref': 'Distance',
    'cat': 'Target Laps',
    'uci': 'Start Offset',
    'nat': 'Nationality',
    'dob': 'DoB',
    'sex': 'Sex',
    'seed': 'Seeding',
    'data': 'Data Reference',
}

_TEAM_COLUMNS = {
    'no': 'Code',
    'series': 'Series',
    'first': 'Name',
    'last': 'Short Name',
    'org': 'Organisation',
    'cat': 'Categories',
    'nat': 'Nationality',
    'ref': 'Start Time',
    'uci': 'UCI ID',
    'dob': 'DoB',
    'sex': 'Division',
    'note': 'Members',
    'seed': 'Seeding',
    'data': 'Data Reference',
}

# Config schema for a rider
_RIDER_SCHEMA = {
    'rtype': {
        'prompt': 'Rider',
        'control': 'section',
    },
    'no': {
        'prompt': 'Rider No:',
        'control': 'short',
        'attr': 'no',
        'defer': True,
        'default': '',
    },
    'series': {
        'prompt': 'Series:',
        'control': 'short',
        'attr': 'series',
        'defer': True,
        'default': '',
    },
    'first': {
        'prompt': 'First Name:',
        'attr': 'first',
        'defer': True,
        'default': '',
    },
    'last': {
        'prompt': 'Last Name:',
        'attr': 'last',
        'defer': True,
        'default': '',
    },
    'org': {
        'prompt': 'Organisation:',
        'attr': 'org',
        'defer': True,
        'hint': 'Club or team affiliation',
        'default': '',
    },
    'cat': {
        'prompt': 'Categories:',
        'attr': 'cat',
        'defer': True,
        'hint': 'Space separated list of categories',
        'default': '',
    },
    'nat': {
        'prompt': 'Nationality:',
        'attr': 'nat',
        'defer': True,
        'hint': '3 letter IOC country code eg: AUS, GBR, JPN',
        'control': 'short',
        'default': '',
    },
    'ref': {
        'prompt': 'Transponder:',
        'attr': 'ref',
        'defer': True,
        'control': 'short',
        'default': '',
    },
    'uci': {
        'prompt': 'UCI ID:',
        'attr': 'uci',
        'defer': True,
        'control': 'short',
        'hint': '11 digit UCI ID',
        'default': '',
    },
    'dob': {
        'prompt': 'Date of Birth:',
        'attr': 'dob',
        'control': 'short',
        'defer': True,
        'subtext': '(YYYY-MM-DD)',
        'hint': 'ISO8601 Date of birth eg: 2012-01-25',
        'default': '',
    },
    'sex': {
        'prompt': 'Sex:',
        'control': 'short',
        'subtext': '(Male|Female)',
        'defer': True,
        'hint': 'Sex of participant',
        'attr': 'sex',
        'default': '',
    },
    'seed': {
        'prompt': 'Seeding:',
        'control': 'short',
        'defer': True,
        'hint': 'Seeding, start time or ranking of rider',
        'attr': 'seed',
        'default': '',
    },
    'data': {
        'prompt': 'Data Ref:',
        'attr': 'data',
        'defer': True,
        'hint': 'Data source, or supplemental ID',
        'default': '',
    },
    'note': {
        'prompt': 'Notes:',
        'attr': 'note',
        'defer': True,
        'hint': 'Supplementary rider notes',
        'default': '',
    },
}

# Config schema for rider series
_SERIES_SCHEMA = {
    'rtype': {
        'prompt': 'Series',
        'control': 'section',
    },
    'no': {
        'prompt': 'ID:',
        'control': 'short',
        'attr': 'no',
        'hint': 'Series ID',
        'defer': True,
        'default': '',
    },
    'series': {
        'prompt': 'Series:',
        'control': 'short',
        'readonly': True,
        'attr': 'series',
        'defer': True,
        'default': '',
    },
    'first': {
        'prompt': 'Title:',
        'attr': 'first',
        'hint': 'Series title',
        'defer': True,
        'default': '',
    },
    'last': {
        'prompt': 'Subtitle:',
        'attr': 'last',
        'hint': 'Series subtitle',
        'defer': True,
        'default': '',
    },
    'note': {
        'prompt': 'Footer:',
        'attr': 'note',
        'defer': True,
        'hint': 'Supplementary footer text for reports',
        'default': '',
    }
}

# Config schema for a category
_CATEGORY_SCHEMA = {
    'rtype': {
        'prompt': 'Category',
        'control': 'section',
    },
    'no': {
        'prompt': 'ID:',
        'control': 'short',
        'attr': 'no',
        'hint': 'Category ID or handicap group',
        'defer': True,
        'default': '',
    },
    'series': {
        'prompt': 'Series:',
        'control': 'short',
        'readonly': True,
        'attr': 'series',
        'defer': True,
        'default': '',
    },
    'first': {
        'prompt': 'Title:',
        'attr': 'first',
        'hint': 'Category title',
        'defer': True,
        'default': '',
    },
    'last': {
        'prompt': 'Subtitle:',
        'attr': 'last',
        'hint': 'Category subtitle',
        'defer': True,
        'default': '',
    },
    'note': {
        'prompt': 'Footer:',
        'attr': 'note',
        'defer': True,
        'hint': 'Supplementary footer text for reports',
        'default': '',
    },
    'uci': {
        'prompt': 'Start Offset:',
        'attr': 'uci',
        'defer': True,
        'control': 'short',
        'hint': 'Start time offset from event start',
        'default': '',
    },
    'cat': {
        'prompt': 'Target:',
        'attr': 'cat',
        'control': 'short',
        'subtext': 'laps',
        'defer': True,
        'hint': 'Target number of laps for this category',
        'default': '',
    },
    'ref': {
        'prompt': 'Distance:',
        'attr': 'ref',
        'defer': True,
        'control': 'short',
        'subtext': 'km',
        'hint': 'Category distance override',
        'default': '',
    },
    'org': {
        'prompt': 'Lap Prefix:',
        'attr': 'org',
        'control': 'short',
        'defer': True,
        'hint': 'Optional category lap prefix',
        'default': '',
    },
}

# Config schema for a series
_CATEGORY_SERIES = {
    'rtype': {
        'prompt': 'Series',
        'control': 'section',
    },
    'no': {
        'prompt': 'ID:',
        'control': 'short',
        'attr': 'no',
        'hint': 'Series ID',
        'defer': True,
        'default': '',
    },
    'series': {
        'prompt': 'Series:',
        'control': 'short',
        'readonly': True,
        'attr': 'series',
        'defer': True,
        'default': '',
    },
    'first': {
        'prompt': 'Title:',
        'attr': 'first',
        'hint': 'Series title',
        'defer': True,
        'default': '',
    },
    'last': {
        'prompt': 'Subtitle:',
        'attr': 'last',
        'hint': 'Series subtitle',
        'defer': True,
        'default': '',
    },
    'note': {
        'prompt': 'Footer:',
        'attr': 'note',
        'defer': True,
        'hint': 'Supplementary footer text for reports',
        'default': '',
    },
}

# Config schema for a team
_TEAM_SCHEMA = {
    'rtype': {
        'prompt': 'Team',
        'control': 'section',
    },
    'no': {
        'prompt': 'Team Code:',
        'control': 'short',
        'attr': 'no',
        'defer': True,
        'default': '',
    },
    'series': {
        'prompt': 'Series:',
        'control': 'short',
        'attr': 'series',
        'defer': True,
        'default': '',
    },
    'first': {
        'prompt': 'Name:',
        'attr': 'first',
        'hint': 'Team name',
        'defer': True,
        'default': '',
    },
    'last': {
        'prompt': 'Short Name:',
        'attr': 'last',
        'control': 'short',
        'subtext': '(~12 characters)',
        'hint': 'Abbreviated team name for reports',
        'defer': True,
        'default': '',
    },
    'org': {
        'prompt': 'Organisation:',
        'attr': 'org',
        'defer': True,
        'hint': 'Club or team affiliation',
        'default': '',
    },
    'nat': {
        'prompt': 'Nationality:',
        'attr': 'nat',
        'defer': True,
        'hint': '3 letter IOC country code eg: AUS, GBR, JPN',
        'control': 'short',
        'default': '',
    },
    'uci': {
        'prompt': 'UCI ID:',
        'attr': 'uci',
        'defer': True,
        'control': 'short',
        'hint': 'Team UCI ID',
        'default': '',
    },
    'sex': {
        'prompt': 'Division:',
        'control': 'short',
        'subtext': '',
        'defer': True,
        'hint': 'UCI division of team eg: WTT WTW PRT',
        'attr': 'sex',
        'default': '',
    },
    'ref': {
        'prompt': 'Start Time:',
        'attr': 'ref',
        'defer': True,
        'control': 'short',
        'subtext': '(Team TT)',
        'hint': 'Team TT Start Time',
        'default': '',
    },
    'note': {
        'prompt': 'Members:',
        'attr': 'note',
        'defer': True,
        'hint': 'List of member riders in BIB.series format',
        'default': '',
    },
}

# reserved series
_RESERVED_SERIES = ('spare', 'cat', 'team', 'ds', 'series')

# legacy csv file ordering
_DEFAULT_COLUMN_ORDER = ('no', 'first', 'last', 'org', 'cat', 'series', 'ref',
                         'uci', 'dob', 'nat', 'sex', 'note', 'seed', 'data')


def primary_cat(catstr=''):
    """Return the primary cat from a catlist (legacy support)."""
    ret = ''
    cv = catstr.split()
    if cv:
        ret = cv[0].upper()
    return ret


def colkey(colstr=''):
    """Convert a column header string to a colkey."""
    col = colstr[0:4].strip().lower()
    if col in _ALT_COLUMNS:
        col = _ALT_COLUMNS[col]
    return col


def get_header(cols=_DEFAULT_COLUMN_ORDER, hdrs=_RIDER_COLUMNS):
    """Return a row of header strings for the provided cols."""
    return (hdrs[colkey(c)] for c in cols)


def cellnorm(unistr):
    """Normalise supplied string, then return only printing chars."""
    return normalize('NFC', unistr.strip()).translate(strops.PRINT_UTRANS)


class rider():
    """Rider handle."""

    def copy(self):
        """Return copy of this rider"""
        nr = rider()
        for k, v in self.__store.items():
            nr.__store[k] = v
        nr.__notify = self.__notify
        return nr

    def get_id(self):
        """Return this rider's unique id"""
        return (self.__store['no'].upper(), self.__store['series'].lower())

    def get_schema(self):
        """Return a schema for this rider object"""
        ret = _RIDER_SCHEMA
        if self.__store['series'] == 'cat':
            ret = _CATEGORY_SCHEMA
        elif self.__store['series'].startswith('t'):
            ret = _TEAM_SCHEMA
        elif self.__store['series'] == 'series':
            ret = _SERIES_SCHEMA
        return ret

    def rename(self, listname, notify=True):
        """Replace first, last and organisation from provided listname

        Rider: 			Firstname LAST NAME (Organisation)
        Team/Cat/Series:	First Name (Organisation)

        """
        first = []
        last = []
        org = []
        inorg = False
        label = self.get_label()
        dolast = not (self.__store['series'].startswith('t')
                      or self.__store['series'] in ('series', 'cat'))
        for namebit in listname.split():
            if namebit.startswith('('):
                inorg = True
            if inorg:
                org.append(namebit.replace('(', '').replace(')', ''))
                if namebit.endswith(')'):
                    inorg = False
            elif first and dolast:
                last.append(namebit)
            else:
                first.append(namebit)
        donotify = False
        newfirst = ' '.join(first)
        if newfirst != self.get_value('firsname'):
            self.set_value('firsname', newfirst)
            donotify = True
        neworg = ' '.join(org)
        if neworg != self.get_value('organisation'):
            self.set_value('organisation', neworg)
            donotify = True
        if dolast:
            newlast = ' '.join(last)
            if newlast != self.get_value('lastname'):
                self.set_value('lastname', newlast)
                donotify = True
        if notify and donotify:
            self.__notify(self.get_id())

    def get_label(self):
        """Return a type label for this object"""
        ret = 'Rider'
        series = self.__store['series'].lower()
        if series == 'cat':
            ret = 'Category'
        elif series.startswith('t'):
            ret = 'Team'
        elif series == 'series':
            ret = 'Number Series'
        elif series == 'ds':
            ret = 'DS'
        elif series == 'spare':
            ret = 'Spare Bike'
        return ret

    def get_bibstr(self):
        """Return the bib.series string"""
        ret = None
        nkey = 'bs'
        if nkey not in self.__strcache:
            ret = strops.bibser2bibstr(self.__store['no'],
                                       self.__store['series'])
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def get_key(self):
        """Return sorting key 'ssssss:nnnn' for this rider"""
        ret = None
        nkey = 'sk'
        if nkey not in self.__strcache:
            ret = '% 6s:% 4s' % (
                self.__store['series'].lower(),
                self.__store['no'].upper(),
            )
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def primary_cat(self):
        """Return rider's primary category"""
        ret = ''
        cv = self['cat'].split()
        if cv:
            ret = cv[0].upper()
        return ret

    def set_primary_cat(self, cat):
        """Set the rider's primary category"""
        new_primary = cat.upper()
        if new_primary:
            cmap = {new_primary: True}
            old_primary = None
            member = False
            for c in self['cat'].split():
                rcat = c.upper()
                if old_primary is None:
                    old_primary = rcat
                if c == new_primary:
                    member = True
                cmap[rcat] = True
            if not member:
                # replace old_primary, rider was not already a member
                if old_primary is not None and old_primary in cmap:
                    del cmap[old_primary]
            self['cat'] = ' '.join(cmap)
        else:
            _log.warning('Cleared %s %s categories', self.get_label(),
                         self.get_bibstr())
            self['cat'] = ''

    def in_series(self, series=None):
        """Return True if rider is in the nominated number series

        If series is None, return True if the rider entry is in a
        non-reserved series
        """
        if series is None and self['series'] not in _RESERVED_SERIES:
            return True
        elif self['series'] == series:
            return True
        return False

    def in_cat(self, cat):
        """Return True if rider is in the nominated category"""
        return cat.upper() in self['cat'].upper().split()

    def get_cats(self):
        """Return a list of categories for this rider"""
        return (c.upper() for c in self['cat'].split())

    def add_cat(self, cat):
        """Append cat to rider"""
        cmap = {}
        for c in self['cat'].split():
            cmap[c.upper()] = True
        cmap[cat.upper()] = True
        self['cat'] = ' '.join((c for c in cmap))

    def del_cat(self, cat):
        """Remove cat from rider"""
        cmap = {}
        for c in self['cat'].split():
            cmap[c.upper()] = True
        rem = cat.upper()
        if rem in cmap:
            del cmap[rem]
            self['cat'] = ' '.join(cmap)

    def get_row(self, coldump=_DEFAULT_COLUMN_ORDER):
        """Return a row ready to export."""
        return (str(self[c]) for c in coldump)

    def set_notify(self, callback=None):
        """Set or clear the notify callback."""
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
        if key in ['no', 'series', 'first', 'last', 'org']:
            self.__strcache = {}

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

    def summary(self):
        """Return a summary string for the rider."""
        ret = None
        iv = [
            ' '.join((
                self.get_label(),
                repr(self.get_bibstr()),
                self.listname(16),
            ))
        ]

        colset = _RIDER_COLUMNS
        series = self.__store['series']
        if series in ('cat', 'series'):
            colset = _CATEGORY_COLUMNS
        elif series.startswith('t'):
            colset = _TEAM_COLUMNS

        for k in colset:
            if k not in ('no', 'series', 'first', 'last', 'org'):
                if self[k]:
                    iv.append('%s: %s' % (colset[k], self[k]))

        ret = ', '.join(iv)
        return ret

    def name_bib(self):
        """Return rider name with bib and without org."""
        ret = None
        nkey = 'nb'
        if nkey not in self.__strcache:
            ret = self.__store['no'] + ' ' + self.fitname(48)
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def resname_bib(self, series=False):
        """Return rider name formatted for results with bib."""
        ret = None
        nkey = ('rnb', series)
        if nkey not in self.__strcache:
            if series:
                ret = self.get_bibstr() + ' ' + self.listname(48)
            else:
                ret = self.__store['no'] + ' ' + self.listname(48)
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def resname(self):
        """Return the name for results"""
        return self.listname(48)

    def listname(self, namelen=32):
        """Return a standard rider name summary field for non-edit lists."""
        ret = None
        nkey = ('ln', namelen)
        if nkey not in self.__strcache:
            ret = self.fitname(namelen)
            if self['org']:
                org = self['org']
                if grapheme.length(org) < 4:
                    org = org.upper()
                ret += ' (' + org + ')'
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def fitname(self, width, trunc=False):
        """Return a truncated name string of width or less graphemes"""
        ret = None
        nkey = ('fn', width, trunc)
        if nkey not in self.__strcache:
            if self['series'].startswith('t'):
                ret = self['first']
                if trunc and grapheme.length(ret) > width:
                    if width > 4:
                        ret = grapheme.slice(ret, end=width - 1) + '\u2026'
                    else:
                        ret = grapheme.slice(ret, end=width)
            else:
                fn = self['first'].strip().title()
                fl = grapheme.length(fn)
                ln = self['last'].strip().upper()
                ll = grapheme.length(ln)
                flen = fl + ll
                if fl and ll:
                    flen += 1
                if flen > width:
                    lshrt = ln.split('-')[-1].strip()
                    lsl = grapheme.length(lshrt)
                    flen = fl + lsl
                    if fl and lsl:
                        flen += 1
                    if flen > width and ln:
                        if fl > 2:
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
            self.__strcache[nkey] = ret
        else:
            ret = self.__strcache[nkey]
        return ret

    def __str__(self):
        return self.resname_bib(series=True)

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
        if key in ['no', 'series', 'first', 'last', 'org']:
            self.__strcache = {}
        self.__notify(self.get_id())

    def __delitem__(self, key):
        key = colkey(key)
        del (self.__store[key])
        if key in ['no', 'series', 'first', 'last', 'org']:
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

    def clear(self, notify=True):
        """Clear rider model."""
        self.__store = {}
        _log.debug('Rider model cleared')
        if notify:
            self.__notify(None)

    def del_rider(self, key, notify=True):
        """Remove rider entry from model with optional notify."""
        del (self.__store[key])
        if notify:
            self.__notify(None)

    def add_rider(self, newrider, notify=True, overwrite=False):
        """Append newrider to model with optional notify."""
        rid = newrider.get_id()
        if rid in self.__store:
            if overwrite:
                olr = self.__store[rid]
                _log.info('Overwriting %s %s', olr.get_label(),
                          olr.resname_bib())
            else:
                _log.info('Duplicate %s %s', newrider.get_label(),
                          newrider.resname_bib())
                rid = (newrider['no'].upper(), '-'.join(
                    ('dupe', strops.randstr())))
        newrider.set_notify(self.__notify)
        self.__store[rid] = newrider
        if notify:
            self.__notify(rid)
        return rid

    def __loadrow(self, r, colspec):
        nr = rider()
        for i in range(0, len(colspec)):
            if len(r) > i:  # column data in row
                key = colspec[i]
                val = cellnorm(r[i])
                if key == 'series':
                    val = val.lower()
                nr[key] = val
        if nr['no']:
            if colkey(nr['no']) in _RIDER_COLUMNS:
                _log.debug('Column header: %r', r)
                return None
        else:
            if nr['series'] != 'series':
                _log.warning('%s without number: %s %s', nr.get_label(),
                             nr.get_bibstr(), nr.resname())
        return nr

    def load(self, csvfile=None, overwrite=False):
        """Load riders from supplied CSV file."""
        if not os.path.isfile(csvfile):
            _log.debug('Riderdb file %r not found', csvfile)
            return 0
        _log.debug('Loading from %r', csvfile)
        count = 0
        with open(csvfile, 'r', encoding='utf-8', errors='replace') as f:
            cr = csv.reader(f)
            incols = None  # no header
            for r in cr:
                nr = None
                if len(r) > 0:  # got a data row
                    if incols is not None:  # already got col header
                        nr = self.__loadrow(r, incols)
                    else:
                        # determine input column structure
                        if colkey(r[0]) in _RIDER_COLUMNS:
                            incols = []
                            for col in r:
                                incols.append(colkey(col))
                        else:
                            incols = _DEFAULT_COLUMN_ORDER  # assume full
                            nr = self.__loadrow(r, incols)
                if nr is not None:
                    self.add_rider(nr, notify=False, overwrite=overwrite)
                    count += 1
        if count > 0:
            self.__notify(None)
        return count

    def listcats(self, series=None):
        """Return a set of categories assigned to riders in the riderdb"""
        if series is not None:
            series = series.lower()
        cats = set()
        for r in self.__store.values():
            if r.in_series(series):
                cats.update(r.get_cats())
        return cats

    def listseries(self):
        """Return an ordered list of series ids in the riderdb"""
        seen = set()
        defined = []
        anonymous = []
        for r in self.__store.values():
            rser = r['series']
            if rser == 'series':
                defined.append(r['no'])
                seen.add(r['no'])
            elif rser not in (
                    'cat',
                    'spare',
                    'ds',
                    'team',
            ):
                if rser not in seen:
                    anonymous.append(rser)
                    seen.add(rser)
        for s in anonymous:
            if s not in defined:
                defined.append(s)
        _log.debug('Returning rider series list: %r', defined)
        return defined

    def biblistfromcat(self, cat, series=None):
        """Return a list of rider ids in the supplied category"""
        if series is not None:
            series = series.lower()
        ret = set()
        label = ''
        for r in self.__store.values():
            if (series is not None
                    and r['series'] == series) or (r['series']
                                                   not in _RESERVED_SERIES):
                if r.in_cat(cat):
                    if not label:
                        label = r.get_label()
                    ret.add(r.get_bibstr())
        _log.debug('Found %d %s in cat %r, series %r', len(ret), label, cat,
                   series)
        return ret

    def biblistfromseries(self, series):
        """Return a list of rider ids in the supplied series"""
        if series is not None:
            series = series.lower()
        ret = set()
        label = ''
        for r in self.__store.values():
            if r['series'] == series:
                if not label:
                    label = r.get_label()
                ret.add(r.get_bibstr())
        _log.debug('Found %d %s in series %r', len(ret), label, series)
        return ret

    def save(self, csvfile=None, columns=None):
        """Save current model content to CSV file."""
        _log.debug('Saving to %r', csvfile)
        cats = []
        if columns is None:
            columns = self.include_cols
        with metarace.savefile(csvfile) as f:
            cr = csv.writer(f, quoting=csv.QUOTE_ALL)
            cr.writerow(get_header(columns))
            for r in self.__store.values():
                if r['series'] in (
                        'cat',
                        'series',
                ):
                    cats.append(r)
                else:
                    cr.writerow(r.get_row(columns))

            if cats:
                cr.writerow(get_header(columns, _CATEGORY_COLUMNS))
                for r in cats:
                    cr.writerow(r.get_row(columns))

    def load_chipfile(self, csvfile=None):
        """Load refids into model from CSV file"""
        _log.debug('Loading refids from %r', csvfile)
        count = 0
        with open(csvfile, 'r', encoding='utf-8', errors='replace') as f:
            cr = csv.reader(f)
            incols = None  # no header
            for r in cr:
                nr = None
                if len(r) > 0:  # got a data row
                    if incols is not None:  # already got col header
                        nr = self.__loadrow(r, incols)
                    else:
                        # determine input column structure
                        if colkey(r[0]) in _RIDER_COLUMNS:
                            incols = []
                            for col in r:
                                incols.append(colkey(col))
                        else:
                            incols = _DEFAULT_COLUMN_ORDER  # assume full
                            nr = self.__loadrow(r, incols)
                if nr is not None:
                    if nr['refid'] and nr['series'] not in _RESERVED_SERIES:
                        lr = self.get_rider(nr['no'], nr['series'])
                        if lr is not None:
                            if nr['refid'] != lr['refid']:
                                lr['refid'] = nr['refid']
                                count += 1
        if count > 0:
            self.__notify(None)
        return count

    def save_chipfile(self, csvfile=None):
        """Save all known refids from model to CSV file"""
        _log.debug('Export chipfile to %r', csvfile)
        columns = ('refid', 'no', 'series', 'first', 'last', 'cat')
        count = 0
        with metarace.savefile(csvfile) as f:
            cr = csv.writer(f, quoting=csv.QUOTE_ALL)
            cr.writerow(get_header(columns))
            for r in self.__store.values():
                if r['series'] not in _RESERVED_SERIES:
                    if r['refid']:
                        cr.writerow(r.get_row(columns))
                        count += 1
        return count

    def update_cats(self, oldcat, newcat, notify=True):
        """Update all instances of oldcat to newcat in each of the riders"""
        for r in self.__store.values():
            if r['series'] != 'cat':
                oldcat = oldcat.upper()
                newcat = newcat.upper()
                rcv = r['cat'].upper().split()
                if oldcat in rcv:
                    oft = rcv.index(oldcat)
                    rcv.insert(oft, newcat)
                    del (rcv[oft + 1])
                    r.set_value('cat', ' '.join(rcv))
                    if notify:
                        r.notify()

    def items(self):
        return self.__store.items()

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
        if series is not None:
            series = series.lower()
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
        if series is not None:
            series = series.lower()
        ret = None
        if series is None:
            riderno, series = strops.bibstr2bibser(riderno)
        nr = rider(no=riderno, series=series)
        return self.add_rider(nr)

    def get_rider(self, riderno, series=None):
        """If rider exists, return handle else return None"""
        if series is not None:
            series = series.lower()
        ret = None
        rkey = self.get_id(riderno, series)
        if rkey in self.__store:
            ret = self.__store[rkey]
        return ret

    def fetch_bibstr(self, bibstr, create=True):
        """Return a rider handle for the bibstr, adding empty as required"""
        ret = None
        rId = strops.bibstr2bibser(bibstr)
        if rId in self.__store:
            return self.__store[rId]
        else:
            if create:
                nr = self.add_empty(rId[0], rId[1])
                ret = self.__store[nr]
        return ret

    def sort(self, notify=True):
        """Re-order by (series, no), preserving order of duplicate entries"""
        aux = [(r[1].get_key(), i, r[0], r[1])
               for i, r in enumerate(self.__store.items())]
        aux.sort()
        self.__store.clear()
        for r in aux:
            self.__store[r[2]] = r[3]
        if notify:
            self.__notify(None)

    def get_id(self, riderno, series=None):
        """If rider exists, return id else return None"""
        ret = None
        if series is not None:
            series = series.lower()
        else:
            riderno, series = strops.bibstr2bibser(riderno)
        rkey = (riderno, series)
        if rkey in self.__store:
            ret = rkey
        return ret

    def iterkeys(self):
        return self.__store.iterkeys()

    def __contains__(self, item):
        return item in self.__store

    def notify(self, data=None):
        """Trigger a manual notify call"""
        self.__notify(data)

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
