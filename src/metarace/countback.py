# SPDX-License-Identifier: MIT
"""Countback support."""


class countback(object):
    """Wrapper for countback store/compare."""
    __hash__ = None

    def __init__(self, cbstr=None):
        self.__store = {}
        if cbstr is not None:
            self.fromstring(cbstr)

    def maxplace(self):
        """Return maximum non-zero place."""
        ret = 0
        if len(self.__store) > 0:
            ret = max(self.__store.keys())
        return ret

    def fromstring(self, cbstr):
        propmap = {}
        cbvec = cbstr.split(',')
        if len(cbvec) > 0:
            for i in range(0, len(cbvec)):
                if cbvec[i].isdigit():
                    propmap[i] = int(cbvec[i])
        self.__store = {}
        for k in propmap:
            self.__store[k] = propmap[k]

    def __repr__(self):
        return 'countback({})'.format(repr(self.__unicode__()))

    def __str__(self):
        return str(self.__unicode__())

    def __unicode__(self):
        ret = []
        for i in range(0, self.maxplace() + 1):
            if i in self.__store and self.__store[i] != 0:
                ret.append(str(self.__store[i]))
            else:
                ret.append('-')
        return ','.join(ret)

    def __len__(self):
        return len(self.__store.len)

    def __getitem__(self, key):
        if key in self.__store:
            return self.__store[key]
        else:
            return 0

    def __setitem__(self, key, value):
        if isinstance(key, int):
            self.__store[key] = value
        else:
            raise AttributeError('Countback keys must be integer')

    def __delitem__(self, key):
        del (self.__store[key])

    def __iter__(self):
        return iter(self.__store.keys())

    def iterkeys(self):
        return iter(self.__store.keys())

    def __contains__(self, item):
        return item in self.__store

    def __lt__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False  # assume all same
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a < b
                break
        return ret

    def __le__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True  # assume all same
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a < b
                break
        return ret

    def __eq__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            if self[i] != other[i]:
                ret = False
                break
        return ret

    def __ne__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            if self[i] != other[i]:
                ret = True
                break
        return ret

    def __gt__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = False  # assume all same
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a > b
                break
        return ret

    def __ge__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = True  # assume all same
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            a = self[i]
            b = other[i]
            if a != b:
                ret = a > b
                break
        return ret

    def __add__(self, other):
        """Add two countbacks together and return a new cb>=self >=other."""
        if not isinstance(other, countback):
            return NotImplemented
        ret = countback(str(self))
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            ret[i] += other[i]
        return ret
