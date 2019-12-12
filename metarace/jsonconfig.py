import json

class config(object):
    def __init__(self, default={}):
        self.__store = dict(default)
  
    def add_section(self, section):
        if not isinstance(section, str):
            raise TypeError('Section key must be str: ' + repr(section))
        if section not in self.__store:
            self.__store[section] = dict()

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
        if not isinstance(key, str):
            raise TypeError('Option key must be str: '
                             + repr(section)+ ':' + repr(key))
        self.__store[section][key] = value

    def write(self, file):
        json.dump(self.__store, file, indent=2, sort_keys=True)

    def dumps(self):
        return json.dumps(self.__store)

    def dictcopy(self):
        """Return a copy of the configuration as a dictionary object."""
        return dict(self.__store)

    def merge(self, otherconfig, section=None, key=None):
        """Merge values from otherconfig into self."""
        if not isinstance(otherconfig, config):
            raise TypeError('Merge expects jsonconfig object.')
        if key is not None and section is not None:     # single value import
            if otherconfig.has_option(section, key):
                self.set(section, key, otherconfig.get(section, key))
        elif section is not None:
            self.add_section(section)   # force even if not already loaded
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
            raise TypeError('Configuration file is not dict')
        for sec in addconf:
            thesec = addconf[sec]
            if not isinstance(thesec, dict):
                raise TypeError('Configuration section is not dict')
            self.add_section(sec)
            for k in thesec:
                self.set(sec, k, thesec[k])

