# SPDX-License-Identifier: MIT
"""JSON Configuration module.

Sectioned configuration with JSON export and import,
implemented as a dictionary of sections. Each section
contains a dictionary of key/value pairs,
where the key is a unicode string and the value may be any
base type supported by python & JSON, as well as the
metarace.tod types: tod and agg.

Config sections have support for schema-based descriptions
with the following keys:

    attr : (str) config attribute in object
    type : (str) value type, one of:
		'none', 'str', 'tod', 'int', 'float', 'chan', 'bool'
    prompt : (str) Text prompt for option
    subtext : (str) Supplementary text for option
    hint : (str) Tooltip, additional info for option
    places : (int) Decimal places for decimal, float and tod types
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
import csv
import logging
from decimal import Decimal
from metarace.tod import tod, fromobj, mktod
from metarace.strops import confopt_chan, CHAN_UNKNOWN

_log = logging.getLogger('jsonconfig')
_log.setLevel(logging.DEBUG)


def _config_object(obj):
    """De-serialise tod and Decimal objects from config."""
    if '__tod__' in obj or '__agg__' in obj:
        return fromobj(obj)
    elif '__dec__' in obj:
        return Decimal(obj['value'])
    return obj


class _configEncoder(json.JSONEncoder):
    """Serialise tod and Decimal objects to config."""

    def default(self, obj):
        if isinstance(obj, tod):
            return obj.serialize()
        elif isinstance(obj, Decimal):
            return {'__dec__': 1, 'value': str(obj)}
        return json.JSONEncoder.default(self, obj)


class config:

    def __init__(self, default={}):
        """Create config object with deep copy of the provided default."""
        self.__store = {}
        self.__schema = {}
        for section in default:
            self.__store[section] = {}
            for key in default[section]:
                self.__store[section][key] = default[section][key]

    def __str__(self):
        return json.dumps(self.__store, cls=_configEncoder)

    def __repr__(self):
        return 'config({})'.format(repr(self.__store))

    def add_section(self, section, schema=None):
        """Add section to config, optionally overwriting schema.

        Args:
            section (str): Section identifier.
            schema (dict, optional): Config schema dict.

        Returns:
            dict: Handle to config section dictionary.

        Raises:
            TypeError: If section key is not string.

        """
        if isinstance(section, str):
            if section not in self.__store:
                self.__store[section] = dict()
            if schema is not None:
                self.__schema[section] = schema
            return self.__store[section]
        else:
            raise TypeError('Invalid section key: ' + repr(section))

    def has_section(self, section):
        """Return True if section in config."""
        return section in self.__store

    def has_option(self, section, key):
        """Return True if section and key in config."""
        return section in self.__store and key in self.__store[section]

    def has_value(self, section, key):
        """Return True if section:key in config and value is not None."""
        return self.has_option(section,
                               key) and self.__store[section][key] is not None

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

    def get_decimal(self, section, key, default=None):
        ret = default
        try:
            ret = Decimal(self.get(section, key))
        except Exception:
            pass
        return ret

    def get_float(self, section, key, default=None):
        ret = default
        try:
            ret = float(self.get(section, key))
        except Exception:
            pass
        return ret

    def get_chan(self, section, key, default=None):
        ret = default
        try:
            rv = self.get(section, key)
            if rv is None or rv == '':
                ret = None
            else:
                nv = confopt_chan(rv)
                if nv != CHAN_UNKNOWN:
                    ret = nv
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
        nv = self.get(section, key)
        if isinstance(nv, tod):
            ret = nv
        else:
            nv = mktod(nv)
            if nv is not None:
                ret = nv
        return ret

    def get_value(self, section, key):
        """Return config value according to schema."""
        ret = None
        schema = {}
        if section in self.__schema:
            schema = self.__schema[section]
        if key in schema:
            option = schema[key]
            if 'default' in option:
                ret = option['default']
            # does the schema require a value?
            otype = 'str'
            if 'type' in option:
                otype = option['type']
            ctrl = 'text'
            if 'control' in option:
                ctrl = option['control']
            if otype != 'none' and ctrl != 'section':
                # schema expects a value
                if self.has_option(section, key):
                    if otype == 'tod':
                        ret = self.get_tod(section, key, ret)
                    elif otype == 'int':
                        ret = self.get_int(section, key, ret)
                    elif otype == 'chan':
                        ret = self.get_chan(section, key, ret)
                    elif otype == 'bool':
                        ret = self.get_bool(section, key, ret)
                    elif otype == 'float':
                        ret = self.get_float(section, key, ret)
                    else:
                        # assume str
                        ret = self.get_str(section, key, ret)
                else:
                    pass
                    #_log.debug('Default used for %r:%r', section, key)
            else:
                pass
                #_log.debug('No value assigned for option %r:%r', section,key)
        else:
            _log.debug('Requested value %r:%r not in schema', section, key)
            if self.has_option(section, key):
                ret = self.get(section, key)
        return ret

    def export_section(self, section, obj):
        """Copy values from section to obj according to schema."""
        if section not in self.__schema:
            _log.error('No schema for section export %r', section)
            return False
        for option in self.__schema[section]:
            schema = self.__schema[section][option]
            otype = 'txt'
            if 'type' in schema:
                otype = schema['type']
            if otype != 'none':
                if 'attr' in schema and hasattr(obj, schema['attr']):
                    attr = schema['attr']
                    val = self.get_value(section, option)
                    setattr(obj, attr, val)
                    #_log.debug('Export option:%r, attr:%r, val:%r', option,
                    #           attr, val)
                else:
                    pass
                    #_log.debug('Skip option: %r', option)
            else:
                pass
                #_log.debug('Option: %r type none', option)

    def export_dict(self, section):
        """Return section as dict according to schema."""
        ret = {}
        if section not in self.__schema:
            _log.error('No schema for section export %r', section)
            return None
        for option in self.__schema[section]:
            schema = self.__schema[section][option]
            otype = 'txt'
            if 'type' in schema:
                otype = schema['type']
            if otype != 'none':
                val = self.get_value(section, option)
                ret[option] = val
            else:
                pass
        return ret

    def import_csv(self, filename, defaults=None):
        """Import values from csv into self according to schema."""
        with open(filename, encoding='utf-8') as f:
            section = None
            cr = csv.reader(f)
            for r in cr:
                if len(r) > 1 and r[0]:
                    key = r[0].strip()
                    val = r[1].strip()
                    if key.lower() == 'section':
                        section = val
                        self.add_section(section)
                        _log.debug('CSV import set section to %r', section)
                        if defaults is not None:
                            self.merge(defaults, section)
                    elif section is not None:
                        self.set(section, key, val)
                        nv = self.get_value(section, key)
                        _log.debug('CSV Import key %r: %r => (%s) %r', key,
                                   val, nv.__class__.__name__, nv)
                        # Write back schema-adjusted value
                        self.set(section, key, nv)
                    else:
                        _log.debug('CSV import key %r ignored, no section',
                                   key)

    def import_section(self, section, obj):
        """Copy values from obj into section according to schema."""
        if section not in self.__schema:
            _log.error('No schema for section import %r', section)
            return False
        for option in self.__schema[section]:
            schema = self.__schema[section][option]
            otype = 'txt'
            if 'type' in schema:
                otype = schema['type']
            if otype != 'none':
                if 'attr' in schema and hasattr(obj, schema['attr']):
                    attr = schema['attr']
                    val = getattr(obj, attr)
                    self.set(section, option, val)
                    #_log.debug('Import option:%r, attr:%r, val:%r', option,
                    #attr, val)
                else:
                    pass
                    #_log.debug('Skip option: %r', option)
            else:
                pass
                #_log.debug('Option: %r type none', option)

    def write(self, file):
        """Write config to file."""
        json.dump(self.__store, file, indent=1, cls=_configEncoder)

    def dumps(self):
        """Dump config as JSON string."""
        return json.dumps(self.__store, indent=1, cls=_configEncoder)

    def dictcopy(self):
        """Return a copy of the configuration as a dictionary object."""
        return dict(self.__store)

    def merge(self, otherconfig, section=None, key=None):
        """Merge values from otherconfig into self."""
        if not isinstance(otherconfig, config):
            raise TypeError('Merge expects jsonconfig object.')
        if key is not None and section is not None:
            if otherconfig.has_option(section, key):
                self.set(section, key, otherconfig.get(section, key))
        elif section is not None:
            self.add_section(section)
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
        """Read config from a JSON-encoded string."""
        self.addconf(json.loads(s, object_hook=_config_object))

    def read(self, file):
        """Read config from file."""
        self.addconf(json.load(file, object_hook=_config_object))

    def addconf(self, obj):
        """Add all sections and values from obj to self."""
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
        """Load the configuration from filename, return True/False."""
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
