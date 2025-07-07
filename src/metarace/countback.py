# SPDX-License-Identifier: MIT
"""Countback

Track a countback of places for ordering points tallies.
The zeroth place is reserved for stage races where 1st
place on the stage finish is considered more significant
than 1st place in intermediates.

Example:

    >>> a = countback()
    >>> a[2] = 1  # 1 2nd place
    >>> a[3] += 3  # 3 3rd places
    >>> str(a)
    '-,-,1,3'
    >>> b = countback('-,1,-,1')
    >>> b > a
    True

To sort a tally with countback, negate the countback
and points:

    st = []
    for rno, pts, cb in something:
        st.append((-pts, -cb, strops.bibstr_key(rno)))
    st.sort()


"""


class countback:
    """Dict wrapper for countback load/store/compare."""
    __hash__ = None

    def maxplace(self):
        """Return maximum place with non-zero count."""
        ret = 0
        if len(self.__store) > 0:
            for k, v in self.__store.items():
                if v != 0 and k > ret:
                    ret = k
        return ret

    def __init__(self, cbstr=None):
        self.__store = {}
        if cbstr is not None:
            self._fromstring(cbstr)

    def _fromstring(self, cbstr):
        """Re-populate store with counts from provided cb string."""
        propmap = {}
        cbvec = cbstr.split(',')
        if len(cbvec) > 0:
            for i, v in enumerate(cbvec):
                v = v.strip()
                if v and v != '-':
                    propmap[i] = int(v)
        # update store after entire string has been processed
        self.__store = {}
        for k, v in propmap.items():
            self.__store[k] = v

    def items(self):
        return self.__store.items()

    def keys(self):
        return self.__store.keys()

    def __repr__(self):
        return 'countback({})'.format(repr(str(self)))

    def __str__(self):
        ret = []
        for i in range(0, self.maxplace() + 1):
            v = self[i]
            if v != 0:
                ret.append(str(v))
            else:
                ret.append('-')
        return ','.join(ret)

    def __getitem__(self, key):
        # Note: unlike defaultdict, a missing key should not be
        #       added to store until it has a non-default value
        if key in self.__store:
            return self.__store[key]
        else:
            return 0

    def __setitem__(self, key, value):
        if isinstance(key, int) and key >= 0:
            self.__store[key] = value
        else:
            raise AttributeError('Countback keys must be integer >= 0')

    def __delitem__(self, key):
        del (self.__store[key])

    def __iter__(self):
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
        if not isinstance(other, countback):
            return NotImplemented
        ret = countback()
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            v = self[i] + other[i]
            if v != 0:
                ret[i] = v
        return ret

    def __sub__(self, other):
        if not isinstance(other, countback):
            return NotImplemented
        ret = countback()
        for i in range(0, max(self.maxplace(), other.maxplace()) + 1):
            v = self[i] - other[i]
            if v != 0:
                ret[i] = v
        return ret

    def __neg__(self):
        ret = countback()
        for i in range(0, self.maxplace() + 1):
            v = self[i]
            if v != 0:
                ret[i] = -v
        return ret
