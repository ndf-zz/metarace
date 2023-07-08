# SPDX-License-Identifier: MIT
"""JSON Configuration module.

  Provides a thin wrapper on a dictionary-based configuration
  with JSON export and import. The structure for a configuration
  is a dictionary of sections, each of which contains a dictionary
  of key/value pairs, where the key is a unicode string and the
  value may be any base type supported by python & JSON.

  Config sections have support for schema-based descriptions with
  the following keys:

  attr : (str) config attribute in object
  type : (str) value type, one of:
		'str', 'tod', 'int', 'float', 'chan', 'bool'
  prompt : (str) Text prompt for option
  subtext : (str) Supplementary text for option
  hint : (str) Tooltip, additional info for option
  places : (int) Decimal places for float and tod types
  defer : (bool) Defer writing changes to object
  readonly : (bool) Control should not allow editing value
  options : (dict) Map of option keys to displayed values
  default : (misc) Default value for option
  control: (str) edit control type, one of:
		'none' : no control should be displayed
		'section' : no value is associated with the option
		'text' : single line text entry
		'short' : short text entry with supplemental text
		'check' : yes/no checkbox
		'choice' : select box choice of options

"""

import json
import os
import logging
from metarace.tod import tod, fromobj, mktod

_log = logging.getLogger('metarace.jsonconfig')
_log.setLevel(logging.DEBUG)


def _config_object(obj):
    """De-serialise tod objects from config."""
    if '__tod__' in obj:
        return fromobj(obj)
    elif '__agg__' in obj:
        return tod(obj['timeval'])
    return obj


class _configEncoder(json.JSONEncoder):
    """Serialise tod objects to config."""

    def default(self, obj):
        print('serialising obj: %r', obj)
        if isinstance(obj, tod):
            return obj.serialize()
        return json.JSONEncoder.default(self, obj)


class config:

    def __init__(self, default={}):
        """Create config object with a deep copy of the provided default."""
        self.__store = {}
        self.__schema = {}
        for section in default:
            self.__store[section] = {}
            for key in default[section]:
                self.__store[section][key] = default[section][key]

    def __str__(self):
        return json.dumps(self.__store, cls=_configEncoder)

    def __unicode__(self):
        return str(self.__str__())

    def __repr__(self):
        return 'config({})'.format(repr(self.__store))

    def add_section(self, section, schema=None):
        if isinstance(section, str):
            if section not in self.__store:
                self.__store[section] = dict()
            if schema is not None:
                self.__schema[section] = schema
            else:
                if section in self.__schema:
                    del self.__schema[section]
            return self.__store[section]
        else:
            raise TypeError('Invalid section key: ' + repr(section))

    def has_section(self, section):
        return section in self.__store

    def has_option(self, section, key):
        return section in self.__store and key in self.__store[section]

    def sections(self):
        for sec in self.__store:
            yield sec

    def options(self, section):
        for opt in self.__store[section]:
            yield opt

    def get(self, section, key):
        return self.__store[section][key]

    def set(self, section, key, value):
        if isinstance(key, str):
            self.__store[section][key] = value
        else:
            raise TypeError('Invalid option key: ' + repr(key))

    def get_float(self, section, key, default=None):
        ret = default
        try:
            ret = float(self.get(section, key))
        except Exception:
            pass
        return ret

    def get_posint(self, section, key, default=None):
        ret = default
        try:
            ret = int(self.get(section, key))
            if ret < 0:
                ret = default
        except Exception:
            pass
        return ret

    def get_int(self, section, key, default=None):
        ret = default
        try:
            ret = int(self.get(section, key))
        except Exception:
            pass
        return ret

    def get_str(self, section, key, default=None):
        ret = self.get(section, key)
        if not isinstance(ret, str):
            ret = default
        return ret

    def get_bool(self, section, key, default=False):
        ret = default
        temp = self.get(section, key)
        if isinstance(temp, str):
            if default:
                if temp.lower() in ['no', 'false', '0']:
                    ret = False
            else:
                if temp.lower() in ['yes', 'true', '1']:
                    ret = True
        else:
            ret = bool(temp)
        return ret

    def get_tod(self, section, key, default=None):
        ret = default
        nt = mktod(self.get(section, key))
        if nt is not None:
            ret = nt
        return ret

    def write(self, file):
        json.dump(self.__store, file, indent=1, cls=_configEncoder)

    def dumps(self):
        return json.dumps(self.__store, indent=1, cls=_configEncoder)

    def dictcopy(self):
        """Return a copy of the configuration as a dictionary object."""
        return dict(self.__store)

    def merge(self, otherconfig, section=None, key=None):
        """Merge values from otherconfig into self."""
        if not isinstance(otherconfig, config):
            raise TypeError('Merge expects jsonconfig object.')
        if key is not None and section is not None:  # single value import
            if otherconfig.has_option(section, key):
                self.set(section, key, otherconfig.get(section, key))
        elif section is not None:
            self.add_section(section)  # force even if not already loaded
            if otherconfig.has_section(section):
                for opt in otherconfig.options(section):
                    self.set(section, opt, otherconfig.get(section, opt))
        else:
            for sec in otherconfig.sections():
                if self.has_section(sec):
                    # in this case, only add sections already defined
                    for opt in otherconfig.options(sec):
                        self.set(sec, opt, otherconfig.get(sec, opt))

    def reads(self, s):
        """Read config from a JSON-encoded string"""
        self.addconf(json.loads(s, object_hook=_config_object))

    def read(self, file):
        """Read config from open file-like"""
        self.addconf(json.load(file, object_hook=_config_object))

    def addconf(self, obj):
        """Add all sections and values from obj to self"""
        if not isinstance(obj, dict):
            raise TypeError('Configuration file is not dict: ' +
                            obj.__class__.__name__)
        for sec in obj:
            thesec = obj[sec]
            if not isinstance(thesec, dict):
                raise TypeError('Configuration section is not dict: ' +
                                thesec.__type__.__name__)
            self.add_section(sec)
            for k in thesec:
                self.set(sec, k, thesec[k])

    def load(self, filename):
        """Load the configuration from filename, return True/False"""
        ret = True
        if os.path.exists(filename):
            try:
                with open(filename, mode='rb') as f:
                    self.read(f)
                _log.debug('Loaded from %r', filename)
            except Exception as e:
                _log.error('%s loading config: %s', e.__class__.__name__, e)
                ret = False
        else:
            _log.debug('Load file %r not found', filename)
            ret = False
        return ret
