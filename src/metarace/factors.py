# SPDX-License-Identifier: MIT
"""Factors for combined categories"""
import logging
import requests
import decimal
import os
import csv
from contextlib import suppress
from metarace import sysconf, default_file, savefile
from metarace import tod
from tempfile import NamedTemporaryFile

# Configuration defaults
_MINFACTOR = decimal.Decimal('0.01')  # minimum allowed factor
_MAXFACTOR = decimal.Decimal(1)  # maximum allowed factor
_QUANT = decimal.Decimal('0.00001')  # desired factor precsion
_DIVISOR = 100000
_PLACES = 5
_ROUND = decimal.ROUND_HALF_EVEN
_FILENAME = 'factors'
_DEFAULT_FILE = _FILENAME + '.csv'
_DEFAULT_URL = None
_TIMEOUT = 10
_MISSING_FACTOR = _MAXFACTOR  # TBC
_CATEGORIES = {
    'PF': 'Para-cycling Factored',
    'OF': 'Open Factored',
    'MOF': 'Men Open Factored',
    'WOF': 'Women Open Factored',
    'AF': 'Age-Based Factored',
    'MAF': 'Men Age-Based Factored',
    'WAF': 'Women Age-Based Factored',
}

# Logging
_log = logging.getLogger('factors')
_log.setLevel(logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.ERROR)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Time Factors',
        'control': 'section',
    },
    'updateurl': {
        'prompt': 'Source:',
        'attr': 'updateurl',
        'hint': 'Filename or URL to update factors',
        'default': _DEFAULT_URL,
    },
}


def readFactor(factor, label, default=None, strict=True):
    """Check a provided factor and return Decimal value."""
    # Note: Also accepts float input, but will complain about quantisation
    ret = default
    try:
        mult = _DIVISOR
        floatval = float(factor)
        if floatval < _MINFACTOR:
            raise ValueError('%s=%s less than minimum %s' %
                             (label, factor, _MINFACTOR))
        if floatval > _MAXFACTOR:
            _log.info('%s=%s assumed percentage', label, factor)
            mult = 1000
        idv = round(mult * floatval)
        dcv = (decimal.Decimal(idv) / _DIVISOR).quantize(_QUANT,
                                                         rounding=_ROUND)
        if dcv > _MAXFACTOR:
            raise ValueError('%s=%s (%s) greater than maximum %s' %
                             (label, factor, dcv, _MAXFACTOR))
        dstr = str(dcv)
        if dstr != factor:
            if strict:
                if (dcv * _DIVISOR) == int(round(mult * floatval, 5)):
                    _log.info('%s=%s -> %s', label, factor, dstr)
                else:  # value has been rounded
                    raise ValueError('%s=%s -> %s' % (label, factor, dcv))
            else:  # only warn
                _log.warning('%s=%s -> %s', label, factor, dstr)
        ret = dcv
    except Exception as e:
        _log.warning('%s: %s', e.__class__.__name__, e)
    return ret


def _cleankey(keystr):
    if keystr:
        keystr = keystr.split(maxsplit=1)[0].upper()
    return keystr


class Factors:
    """Provide time factors from published source."""

    def __init__(self):
        self._valid = False
        self._store = {}
        for cat in _CATEGORIES:
            self._store[cat] = {}

    def is_valid(self):
        """Return True if currently loaded factors are valid."""
        return self._valid

    def factor_time(self, cat, sportclass, time, places=2, rounding=_ROUND):
        """Return a factored version of tod time."""
        ret = time
        try:
            factor = self.get_factor(cat, sportclass)
            nt = +time  # create local copy of time
            nt.timeval *= factor
            ret = nt.places(places, rounding, flag='FCTRD')
            ret.source = factor
            _log.debug('%s.%s: %s * %s -> %s', cat, sportclass, time.timeval,
                       factor, nt.timeval)
        except Exception as e:
            _log.warning('%s %s.%s: %s', e.__class__.__name__, cat, sportclass,
                         e)
        return ret

    def set_factor(self, cat, sportclass, factor):
        """Update a factor with the provided value."""
        cat = _cleankey(cat)
        sportclass = _cleankey(sportclass)
        label = '.'.join((cat, sportclass))
        fv = readFactor(factor, label)
        if fv is None:
            _log.warning('%s.%s invalid factor %s ignored', cat, sportclass,
                         factor)
            return False
        if cat not in self._store:
            _log.warning('%s invalid cat', cat)
            return False

        self._store[cat][sportclass] = fv
        self._valid = True
        _log.info('%s.%s updated factor %s', cat, sportclass, fv)
        return True

    def get_factor(self, cat, sportclass):
        """Return a factor for the named cat and sport class."""
        ret = _MISSING_FACTOR
        if self._valid:
            if cat in self._store:
                if sportclass in self._store[cat]:
                    ret = self._store[cat][sportclass]
                else:
                    _log.warning('%s.%s not found returning default', cat,
                                 sportclass)
            else:
                _log.warning('%s invalid cat, returning default', cat)
        else:
            _log.warning('Time Factors not valid')
        return ret

    def update(self, filename=None):
        """Fetch published factors, overwriting current values if valid."""
        if filename is None:
            filename = _DEFAULT_FILE
        sysconf.add_section('factors', _CONFIG_SCHEMA)
        url = sysconf.get_value('factors', 'updateurl')
        if not url:
            _log.error('Update URL not set, factors not updated')
            return self._valid
        try:
            _log.debug('Fetching updated factors from %s', url)
            with requests.Session() as s:
                r = s.get(url, timeout=_TIMEOUT)
                if r.status_code == 200:
                    # write data to temp file
                    with NamedTemporaryFile(mode='wb') as f:
                        f.write(r.content)
                        f.flush()
                        _log.debug('Temp factors saved to: %s', f.name)
                        with open(f.name) as g:
                            self.read(g)
                        if self._valid:
                            self.save(filename)
                else:
                    _log.error('Invalid read response: %d', r.status_code)
        except Exception as e:
            if self._valid:
                _log.warning('%s updating factors, values retained: %s',
                             e.__class__.__name__, e)
            else:
                _log.error('%s updating factors: %s', e.__class__.__name__, e)
        return self._valid

    def write(self, file):
        """Write factors to CSV file."""
        hdr = ('Category', 'Sport Class', 'Factor')
        cw = csv.DictWriter(file, fieldnames=hdr, quoting=csv.QUOTE_ALL)
        cw.writeheader()
        for cat, factors in self._store.items():
            _log.debug('Dumping %d factors for cat=%s', len(factors), cat)
            for sportclass, factor in factors.items():
                cw.writerow({
                    'Category': cat,
                    'Sport Class': sportclass,
                    'Factor': str(factor)
                })

    def save(self, filename=None):
        """Save current factors to filename if valid."""
        if not self.is_valid():
            _log.error('Factors not valid, not saved.')
            return self._valid
        if filename is None:
            filename = _DEFAULT_FILE
        try:
            with savefile(filename) as f:
                self.write(f)
        except Exception as e:
            _log.warning('%s save: %s', e.__class__.__name__, e)

    def read(self, file):
        count = 0
        cr = csv.DictReader(file)
        for r in cr:
            if r['Category'] and r['Sport Class'] and r['Factor']:
                cat = _cleankey(r['Category'])
                if cat != r['Category']:
                    _log.warning('Skipped malformed cat %s', r['Category'])
                    continue
                if cat not in self._store:
                    _log.info('Skipped unknown cat %s', cat)
                    continue
                sportclass = _cleankey(r['Sport Class'])
                if sportclass != r['Sport Class']:
                    _log.warning('Skipped malformed sport class %s',
                                 r['Sport Class'])
                    continue
                flbl = '.'.join((cat, sportclass))
                factor = readFactor(r['Factor'], label=flbl)
                if factor is not None:
                    _log.debug('%s add factor %s', flbl, factor)
                    self._store[cat][sportclass] = factor
                    count += 1
        if count:
            _log.debug('Loaded %d factors', count)
            self._valid = True
        else:
            _log.debug('No valid factors loaded')
            self._valid = False

    def load(self, filename=None):
        """Load time factors from filename."""
        if filename is None:
            filename = _DEFAULT_FILE
        srcfile = default_file(filename)
        if not os.path.exists(srcfile):
            _log.warning('Source file not found')
            return self._valid
        try:
            with open(srcfile) as f:
                self.read(f)
        except Exception as e:
            _log.warning('%s load: %s', e.__class__.__name__, e)
        return self._valid
