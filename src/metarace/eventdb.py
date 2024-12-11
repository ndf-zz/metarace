# SPDX-License-Identifier: MIT
"""CSV Event Listing."""

import logging
import os
import csv

import metarace
from metarace import strops

_log = logging.getLogger('eventdb')
_log.setLevel(logging.DEBUG)

# Note: These are for the trackmeet module, roadmeet re-defines race types
defracetypes = [
    'sprint',
    'keirin',
    'flying 200',
    'flying lap',
    'indiv tt',
    'indiv pursuit',
    'pursuit race',
    'points',
    'madison',
    'omnium',
    'tempo',
    'classification',
    'hour',
    'competition',
    'break',
    'sprint round',
    'sprint final',
    'scratch',
    'motorpace',
    'handicap',
    'elimination',
    'race',
]

# default event values (if not empty string)
EVENT_DEFAULTS = {
    'evid': None,  # empty not allowed
    'resu': True,
    'inde': False,
    'prin': False,
    'dirt': False,
    'plac': None,
    'laps': None,
}

# event column heading and key mappings
EVENT_COLUMNS = {
    'evid': "EvID",
    'refe': "Reference Number",
    'pref': "Prefix",
    'info': "Information",
    'seri': "Series",
    'type': "Type Handler",
    'star': "Starters",
    'depe': "Depends On Events",
    'resu': "Result Include?",
    'inde': "Index Include?",
    'prin': "Printed Program Include?",
    'plac': "Placeholder Count",
    'sess': "Session",
    'laps': "Laps Count",
    'dist': "Distance String",
    'prog': "Progression Rules String",
    'reco': "Record String",
    'dirt': "Dirty?",
    'evov': "EVOverride"
}

# for any non-strings, types as listed
EVENT_COLUMN_CONVERTERS = {
    'resu': strops.confopt_bool,
    'inde': strops.confopt_bool,
    'prin': strops.confopt_bool,
    'dirt': strops.confopt_bool,
    'plac': strops.confopt_posint,
    'laps': strops.confopt_posint,
}

DEFAULT_COLUMN_ORDER = [
    'evid', 'refe', 'pref', 'info', 'seri', 'type', 'star', 'depe', 'resu',
    'inde', 'prin', 'plac', 'sess', 'laps', 'dist', 'prog', 'evov', 'reco',
    'dirt'
]


def colkey(colstr=''):
    """Convert a coumn header string to a colkey."""
    return colstr[0:4].lower()


def get_header(cols=DEFAULT_COLUMN_ORDER):
    """Return a row of header strings for the provided cols."""
    return [EVENT_COLUMNS[c] for c in cols]


class event:
    """CSV-backed event listing."""

    def get_row(self, coldump=DEFAULT_COLUMN_ORDER):
        """Return a row ready to export."""
        return [str(self[c]) for c in coldump]

    def event_info(self):
        """Return a concatenated and stripped event information string."""
        return ' '.join([self['pref'], self['info']]).strip()

    def event_type(self):
        """Return event type string."""
        return self['type'].capitalize()

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
        self.__notify(self.__store['evid'])

    def __init__(self, evid=None, notify=None, cols={}):
        self.__store = dict(cols)
        self.__notify = self.__def_notify
        if 'evid' not in self.__store:
            self.__store['evid'] = evid
        if notify is not None:
            self.__notify = notify

    def __len__(self):
        return len(self.__store)

    def __getitem__(self, key):
        """Use a default value id, but don't save it."""
        key = colkey(key)
        if key in self.__store:
            return self.__store[key]
        elif key in EVENT_DEFAULTS:
            return EVENT_DEFAULTS[key]
        else:
            return ''

    def __setitem__(self, key, value):
        key = colkey(key)
        self.__store[key] = value
        self.__notify(self.__store['evid'])

    def __delitem__(self, key):
        key = colkey(key)
        del (self.__store[key])
        self.__notify(self.__store['evid'])

    def __iter__(self):
        return iter(self.__store.keys())

    def iterkeys(self):
        return iter(self.__store.keys())

    def __contains__(self, item):
        key = colkey(item)
        return key in self.__store

    def __def_notify(self, data=None):
        pass


class eventdb:
    """Event database."""

    def add_empty(self, evno=None):
        """Add a new empty row to the event model."""
        if evno is None:
            evno = self.nextevno()
        nev = event(evid=evno, notify=self.__notify)
        self.__store[evno] = nev
        self.__index.append(evno)
        self.__notify(None)
        _log.debug('Added empty event %r', evno)
        return nev

    def clear(self):
        """Clear event model."""
        self.__index = []
        self.__store = {}
        self.__notify(None)
        _log.debug('Event model cleared')

    def change_evno(self, oldevent, newevent):
        """Attempt to change the event id."""
        if oldevent not in self:
            _log.error('Change event %r not found', oldevent)
            return False

        if newevent in self:
            _log.error('New event %r already exists', newevent)
            return False

        oktochg = True
        if self.__evno_change_cb is not None:
            oktochg = self.__evno_change_cb(oldevent, newevent)
        if oktochg:
            ref = self.__store[oldevent]
            ref.set_value('evid', newevent)
            cnt = 0
            for j in self.__index:
                if j == oldevent:
                    break
                cnt += 1
            if cnt < len(self.__index):
                self.__index[cnt] = newevent
            del (self.__store[oldevent])
            self.__store[newevent] = ref
            _log.info('Updated event %r to %r', oldevent, newevent)
            return True
        return False

    def add_event(self, newevent):
        """Append newevent to model."""
        eid = newevent['evid']
        if eid is None:
            eid = self.nextevno()
        elif not isinstance(eid, str):
            _log.debug('Converted %r to event id: %r', eid, str(eid))
            eid = str(eid)
        evno = eid
        while evno in self.__index:
            evno = u'-'.join((eid, strops.randstr()))
            _log.info('Duplicate evid %r changed to %r', eid, evno)
        newevent['evid'] = evno
        _log.debug('Add new event with id=%r', evno)
        newevent.set_notify(self.__notify)
        self.__store[evno] = newevent
        self.__index.append(evno)

    def __loadrow(self, r, colspec):
        nev = event()
        for i in range(0, len(colspec)):
            if len(r) > i:  # column data in row
                val = r[i].translate(strops.PRINT_UTRANS)
                key = colspec[i]
                if key in EVENT_COLUMN_CONVERTERS:
                    val = EVENT_COLUMN_CONVERTERS[key](val)
                nev[key] = val
        if not nev['evid']:
            evno = self.nextevno()
            _log.info('Event without id assigned %r', evno)
            nev['evid'] = evno
        self.add_event(nev)

    def load(self, csvfile=None):
        """Load events from supplied CSV file."""
        if not os.path.isfile(csvfile):
            _log.debug('Events file %r not found', csvfile)
            return
        _log.debug('Loading events from %r', csvfile)
        with open(csvfile, encoding='utf-8', errors='replace') as f:
            cr = csv.reader(f)
            incols = None  # no header
            for r in cr:
                if len(r) > 0:  # got a data row
                    if incols is not None:  # already got col header
                        self.__loadrow(r, incols)
                    else:
                        # determine input column structure
                        if colkey(r[0]) in EVENT_COLUMNS:
                            incols = []
                            for col in r:
                                incols.append(colkey(col))
                        else:
                            incols = DEFAULT_COLUMN_ORDER  # assume full
                            self.__loadrow(r, incols)
        self.__notify(None)

    def save(self, csvfile=None):
        """Save current model content to CSV file."""
        if len(self.__index) != len(self.__store):
            _log.error('Index out of sync with model, dumping whole model')
            self.__index = [a for a in self.__store]

        _log.debug('Saving events to %r', csvfile)
        with metarace.savefile(csvfile) as f:
            cr = csv.writer(f, quoting=csv.QUOTE_ALL)
            cr.writerow(get_header(self.include_cols))
            for r in self:
                cr.writerow(r.get_row())

    def nextevno(self):
        """Try and return a new event number string."""
        lmax = 1
        for r in self.__index:
            if r.isdigit() and int(r) >= lmax:
                lmax = int(r) + 1
        return str(lmax)

    def set_evno_change_cb(self, cb, data=None):
        """Set the event no change callback."""
        self.__evno_change_cb = cb

    def getfirst(self):
        """Return the first event in the db."""
        ret = None
        if len(self.__index) > 0:
            ret = self[self.__index[0]]
        return ret

    def getnextrow(self, ref, scroll=True):
        """Return reference to the row one after current selection."""
        ret = None
        if ref is not None:
            path = self.__index.index(ref['evid']) + 1
            if path >= 0 and path < len(self.__index):
                ret = self[self.__index[path]]  # check reference
        return ret

    def getprevrow(self, ref, scroll=True):
        """Return reference to the row one after current selection."""
        ret = None
        if ref is not None:
            path = self.__index.index(ref['evid']) - 1
            if path >= 0 and path < len(self.__index):
                ret = self[self.__index[path]]  # check reference
        return ret

    def __len__(self):
        return len(self.__store)

    def __getitem__(self, key):
        return self.__store[key]

    def __setitem__(self, key, value):
        self.__store[key] = value  # no change to key
        self.__notify(key)

    def __delitem__(self, key):
        self.__index.remove(key)
        del (self.__store[key])

    def __iter__(self):
        for r in self.__index:
            yield self.__store[r]

    def iterkeys(self):
        return self.__index.__iter__()

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
        pass

    def __init__(self, racetypes=None):
        """Constructor for the event db."""
        self.__index = []
        self.__store = {}
        self.__notify = self.__def_notify
        self.__evno_change_cb = None

        self.include_cols = DEFAULT_COLUMN_ORDER
        if racetypes is not None:
            self.racetypes = racetypes
        else:
            self.racetypes = defracetypes
