# SPDX-License-Identifier: MIT
"""JSON Configuration module.

  Provides a thin wrapper on a dictionary-based configuration
  with JSON export and import. The structure for a configuration
  is a dictionary of sections, each of which contains a dictionary
  of key/value pairs, where the key is a unicode string and the
  value may be any base type supported by python & JSON.
"""

import json


class config(object):

    def __init__(self, default={}):
        """Create config object with a deep copy of the provided default."""
        self.__store = {}
        for section in default:
            self.__store[section] = {}
            for key in default[section]:
                self.__store[section][key] = default[section][key]

    def __str__(self):
        return json.dumps(self.__store)

    def __unicode__(self):
        return str(self.__str__())

    def __repr__(self):
        return 'config({})'.format(repr(self.__store))

    def add_section(self, section):
        if isinstance(section, str):
            if section not in self.__store:
                self.__store[section] = dict()
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

    def get_bool(self, section, key):
        temp = self.get(section, key)
        if isinstance(temp, str):
            if temp.lower() in ['yes', 'true', '1']:
                return True
            else:
                return False
        else:
            return bool(temp)

    def write(self, file):
        json.dump(self.__store, file, indent=1)

    def dumps(self):
        return json.dumps(self.__store, indent=1)

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

    def read(self, file):
        addconf = json.load(file)
        if not isinstance(addconf, dict):
            raise TypeError('Configuration file is not dict: ' +
                            addconf.__class__.__name__)
        for sec in addconf:
            thesec = addconf[sec]
            if not isinstance(thesec, dict):
                raise TypeError('Configuration section is not dict: ' +
                                thesec.__type__.__name__)
            self.add_section(sec)
            for k in thesec:
                self.set(sec, k, thesec[k])
