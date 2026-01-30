# SPDX-License-Identifier: MIT
"""Externally managed standards, time factors, categories."""
import logging
import decimal
import os
import csv
from contextlib import suppress
from metarace import sysconf, default_file, savefile
from metarace import tod
from metarace import strops
from tempfile import NamedTemporaryFile

# Configuration defaults
_MINFACTOR = decimal.Decimal('0.01')  # minimum allowed factor
_MAXFACTOR = decimal.Decimal(1)  # maximum allowed factor
_QUANT = decimal.Decimal('0.00001')  # desired factor precsion
_DIVISOR = 100000
_PLACES = 5
_ROUND = decimal.ROUND_HALF_EVEN
_FACTORFILENAME = 'factors'
_DEFAULT_FACTORFILE = _FACTORFILENAME + '.csv'
_CATFILENAME = 'categories'
_DEFAULT_CATFILE = _CATFILENAME + '.csv'
_DEFAULT_FACTORURL = None
_DEFAULT_CATURL = None
_TIMEOUT = 10
_MISSING_FACTOR = _MAXFACTOR  # TBC
_FACTORCATEGORIES = {
    'PF': 'Para-cycling Factored',
    'OF': 'Open Factored',
    'MOF': 'Men Open Factored',
    'WOF': 'Women Open Factored',
    'AF': 'Age-Based Factored',
    'MAF': 'Men Age-Based Factored',
    'WAF': 'Women Age-Based Factored',
}

# Logging
_log = logging.getLogger('standards')
_log.setLevel(logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.ERROR)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Time Factors',
        'control': 'section',
    },
    'factorupdateurl': {
        'prompt': 'Source:',
        'attr': 'factorupdateurl',
        'hint': 'Filename or URL to update factors',
        'default': _DEFAULT_FACTORURL,
    },
    'ctype': {
        'prompt': 'Category Info',
        'control': 'section',
    },
    'catupdateurl': {
        'prompt': 'Source:',
        'attr': 'catupdateurl',
        'hint': 'Filename or URL to update category info',
        'default': _DEFAULT_CATURL,
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


class CategoryInfo:
    """Provide external information on competitor categories."""

    def __init__(self):
        self._valid = False
        self._store = {}

    def get_cat(self, cat):
        ret = None
        if cat in self._store:
            ret = self._store[cat]
        return ret

    def is_valid(self):
        """Return True if some onfo loaded."""
        return self._valid

    def update(self, filename=None):
        """Fetch published categories, overwriting current values if valid."""
        if filename is None:
            filename = _DEFAULT_CATFILE
        sysconf.add_section('standards', _CONFIG_SCHEMA)
        url = sysconf.get_value('standards', 'catupdateurl')
        if not url:
            _log.error('Category update URL not set, factors not updated')
            return self._valid
        try:
            _log.debug('Fetching updated categories from %s', url)
            from requests import Session
            with Session() as s:
                r = s.get(url, timeout=_TIMEOUT)
                if r.status_code == 200:
                    # write data to temp file
                    with NamedTemporaryFile(mode='wb') as f:
                        f.write(r.content)
                        f.flush()
                        _log.debug('Temp categories saved to: %s', f.name)
                        with open(f.name) as g:
                            self.read(g)
                        if self._valid:
                            self.save(filename)
                else:
                    _log.error('Invalid cat read response: %d', r.status_code)
        except Exception as e:
            if self._valid:
                _log.warning('%s updating categories, values retained: %s',
                             e.__class__.__name__, e)
            else:
                _log.error('%s updating categories: %s', e.__class__.__name__,
                           e)
        return self._valid

    def write(self, file):
        """Write categories to CSV file."""
        hdr = (
            'ID',
            'Title',
            'Min Age',
            'Max Age',
            'Type',
            'Sex',
            'Sport Class',
            'Discipline',
            'Time Trial',
            'Pursuit',
            'Scratch',
            'Points',
            'Madison',
        )

        cw = csv.DictWriter(file, fieldnames=hdr, quoting=csv.QUOTE_ALL)
        cw.writeheader()
        for cat, category in self._store.items():
            orec = {'ID': cat}
            for key, val in category.items():
                if val:
                    orec[key] = str(val)
                else:
                    orec[key] = ''
            cw.writerow(orec)

    def save(self, filename=None):
        """Save current factors to filename if valid."""
        if not self.is_valid():
            _log.error('Categories not valid, not saved.')
            return self._valid
        if filename is None:
            filename = _DEFAULT_CATFILE
        try:
            with savefile(filename) as f:
                self.write(f)
        except Exception as e:
            _log.warning('%s cat save: %s', e.__class__.__name__, e)

    def read(self, file):
        count = 0
        cr = csv.DictReader(file)
        for r in cr:
            if r['ID'] and r['Title']:
                cat = None
                catinfo = {}
                for key, val in r.items():
                    val = val.strip()
                    if key == 'ID':
                        cat = _cleankey(r['ID'])
                    elif key in ('Min Age', 'Max Age', 'Time Trial', 'Pursuit',
                                 'Scratch', 'Points', 'Madison'):
                        catinfo[key] = strops.confopt_posint(val)
                    elif key == 'Sex':
                        ckval = val.upper()[0:1]
                        if ckval not in ('M', 'W'):
                            ckval = None
                        catinfo[key] = ckval
                    elif key == 'Discipline':
                        ckval = val.lower()
                        if ckval not in ('all', 'road', 'track', 'mtb'):
                            ckval = None
                        catinfo[key] = ckval
                    else:
                        if val:
                            catinfo[key] = val
                        else:
                            catinfo[key] = None
                self._store[cat] = catinfo
                count += 1
        if count:
            _log.debug('Loaded %d categories', count)
            self._valid = True
        else:
            _log.debug('No valid categories loaded')
            self._valid = False

    def load(self, filename=None):
        """Load categories from filename."""
        if filename is None:
            filename = _DEFAULT_CATFILE
        srcfile = default_file(filename)
        if not os.path.exists(srcfile):
            _log.warning('Source file not found')
            return self._valid
        try:
            with open(srcfile) as f:
                self.read(f)
        except Exception as e:
            _log.warning('%s cat load: %s', e.__class__.__name__, e)
        return self._valid


class Factors:
    """Provide time factors from published source."""

    def __init__(self):
        self._valid = False
        self._store = {}
        for cat in _FACTORCATEGORIES:
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
            filename = _DEFAULT_FACTORFILE
        sysconf.add_section('standards', _CONFIG_SCHEMA)
        url = sysconf.get_value('standards', 'factorupdateurl')
        if not url:
            _log.error('Factor update URL not set, factors not updated')
            return self._valid
        try:
            _log.debug('Fetching updated factors from %s', url)
            from requests import Session
            with Session() as s:
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
            filename = _DEFAULT_FACTORFILE
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
            filename = _DEFAULT_FACTORFILE
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
