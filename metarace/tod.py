
import decimal
import re		# used to scan ToD string: HH:MM:SS.dcmz 
import time

QUANT_5PLACES = decimal.Decimal('0.00001') # does not work with Timy printer
QUANT_4PLACES = decimal.Decimal('0.0001')
QUANT_3PLACES = decimal.Decimal('0.001')
QUANT_2PLACES = decimal.Decimal('0.01')
QUANT_1PLACE = decimal.Decimal('0.1')
QUANT_0PLACES = decimal.Decimal('1')
QUANT = [QUANT_0PLACES, QUANT_1PLACE, QUANT_2PLACES,
         QUANT_3PLACES, QUANT_4PLACES, QUANT_5PLACES]
QUANT_FW = [2, 4, 5, 6, 7, 8]
QUANT_TWID = [8, 10, 11, 12, 13, 14]
QUANT_PAD = ['     ', '   ', '  ', ' ', '', '']
QUANT_OPAD = ['    ', '  ', ' ', '', '', '']

def str2agg(timeval=''):
    """Return agg for given string without fail."""
    ret = None
    if timeval is not None and timeval != '':
        try:
            ret = agg(timeval)
        except:
            pass
    return ret

def str2tod(timeval=''):
    """Return tod for given string without fail."""
    ret = None
    if timeval is not None and timeval != '':
        try:
            ret = tod(timeval)
        except:
            pass
    return ret

def dec2hm(dectod=None):
    """Return hours and minutes only."""
    strtod = None
    if dectod is not None: 		# conditional here?
        if dectod >= 3600:	# NOTE: equal compares fine w/decimal
            fmt = '{0}:{1:02}' # 'HH:MM'
            strtod = fmt.format(int(dectod)//3600,
                (int(dectod)%3600)//60)
        elif dectod >= 60:	# weird.. minutes only
            strtod = '{0}'.format(int(dectod)//60)
        else:
            strtod = ''	# No minutes to convert?
    return strtod


def dec2str(dectod=None, places=4, zeros=False, hoursep='h', minsep=':'):
    """Return formatted string for given tod decimal value.

    Convert the decimal number dectod to a time string with the
    supplied number of decimal places. 

    Note: negative timevals match case one or three depending on
          value of zeros flag, and are truncated toward zero.
          Oversized timevals will grow in width

          optional argument 'zeros' will use leading zero chars. eg:

             '00h00:01.2345'   zeros=True
                    '1.2345'   zeros=False

    """
    strtod = None
    
    if dectod is not None: 		# conditional here?
        if zeros or dectod >= 3600:	# NOTE: equal compares fine w/decimal
            fmt = '{0}'+hoursep+'{1:02}'+minsep+'{2:0{3}}' # 'HHhMM:SS.dcmz'
            if zeros:
                fmt = '{0:02}'+hoursep+'{1:02}'+minsep+'{2:0{3}}'# '00h00:0S.dcmz' (specialcase)
            strtod = fmt.format(int(dectod)//3600,
                (int(dectod)%3600)//60,
                dectod.quantize(QUANT[places],
                rounding=decimal.ROUND_FLOOR)%60,
                QUANT_FW[places])
        elif dectod >= 60:	# MM:SS.dcmz
            strtod = ('{0}'+minsep+'{1:0{2}}').format(int(dectod)//60,
                dectod.quantize(QUANT[places],
                rounding=decimal.ROUND_FLOOR)%60,
                QUANT_FW[places])
        else: 			# SS.dcmz or -SSSSS.dcmz
            strtod = '{0}'.format(dectod.quantize(QUANT[places],
                rounding=decimal.ROUND_FLOOR))
    return strtod

def nowsecs():
    """Return a decimal number of seconds after midnight in local time."""
    rs = time.time()
    lt = time.localtime(rs)
    ret = decimal.Decimal("{0:0.5f}".format(
                           (rs+lt.tm_gmtoff)%86400))
    return ret

def str2dec(timestr=''):
    """Return decimal for given string.

    Convert the time of day value represented by the string supplied
    to a decimal number of seconds.

    Attempts to match against the common patterns:

    HHhMM:SS.dcmz		Canonical
    HH:MM:SS.dcmz		Display style
    HH:MM'SS"dcmz		Chronelec
    HH-MM-SS.dcmz		Keypad

    In optional groups as follows:

    [[HH:]MM:]SS[.dcmz]

    NOTE: Now truncates all incoming times to 4 places to avoid
          inconsistencies.

    """
    dectod=None
    timestr=timestr.strip()	# assumes string
    if timestr == 'now':
        dectod = nowsecs()
    else:
        m = re.match(r'^(?:(?:(\d{1,2})[h:-])?(\d{1,2})[:\'-])?(\d{1,2}(?:[\.\"]\d+)?)$',
                     timestr)
        if m is not None:
            dectod = decimal.Decimal(m.group(3).replace('"', '.'))
            dectod += int(m.group(2) or 0) * 60
            dectod += int(m.group(1) or 0) * 3600
        else:
            # last attempt - try and handle as raw decimal constructor
            dectod = decimal.Decimal(timestr)
    return dectod.quantize(QUANT[4], rounding=decimal.ROUND_FLOOR)

class tod(object):
    """A class for representing time of day and RFID events."""
    def __init__(self, timeval=0, index='', chan='', refid='', source=''):
        """Construct tod object.

        Keyword arguments:
        timeval -- time value to be represented (string/int/decimal/tod)
        index -- tod index identifier string
        chan -- channel string
        refid -- a reference identifier string
        source -- timer source identifier or u'' if not sourced
        ltime -- wall clock when received

        """

        self.index = index[0:4]	# numeric raises exception here
        self.chan = chan ## chan[0:3]
        self.refid = refid
        self.source = source
        self.ltime = None
        if isinstance(timeval, str):
            self.timeval = str2dec(timeval)%86400
        elif isinstance(timeval, tod):
            self.timeval = timeval.timeval%86400
        else:
            self.timeval = decimal.Decimal(timeval)%86400

    def __str__(self):
        """Return a normalised tod string."""
        return self.refstr()

    def __repr__(self):
        """Return object representation string."""
        return "tod({0}, {1}, {2}, {3}, {4})".format(repr(self.timeval),
                                repr(self.index), repr(self.chan),
                                repr(self.refid), repr(self.source))

    def refstr(self, places=4):
        """Return 'normalised' string form.

        'NNNN CCC HHhMM:SS.dcmz REFID'
        to the specified number of decimal places in the set
        [0, 1, 2, 3, 4]

        """
        return '{0: >4} {1: <3} {2} {3}'.format(self.index, self.chan,
                self.timestr(places), self.refid)

    def truncate(self, places=4):
        """Return a new ToD object with a truncated time value."""
        return tod(timeval=self.timeval.quantize(QUANT[places],
                rounding=decimal.ROUND_FLOOR), index='', chan='ToD', refid='')

    def as_hours(self, places=0):
        """Return the tod value in hours, truncated to the desired places."""
        return (self.timeval / 3600).quantize(QUANT[places],
                                            rounding=decimal.ROUND_FLOOR)

    def as_seconds(self, places=0):
        """Return the tod value in seconds, truncated to the desired places."""
        return self.timeval.quantize(QUANT[places],
                                     rounding=decimal.ROUND_FLOOR)

    def as_minutes(self, places=0):
        """Return the tod value in minutes, truncated to the desired places."""
        return (self.timeval / 60).quantize(QUANT[places],
                                            rounding=decimal.ROUND_FLOOR)

    def timestr(self, places=4, zeros=False, hoursep='h', minsep=':'):
        """Return time string component of the tod, whitespace padded."""
        return '{0: >{1}}{2}'.format(dec2str(self.timeval, places, zeros,
                                             hoursep, minsep),
            QUANT_TWID[places], QUANT_PAD[places])

    def omstr(self, places=3, zeros=False, hoursep=':', minsep=':'):
        """Return the 12 digit 'omega' style time string for gemini."""
        if places > 3:
            places = 3		# Hack to clamp to 12 dig
        return '{0: >{1}}{2}'.format(dec2str(self.timeval, places, zeros,
                                             hoursep, minsep),
            QUANT_TWID[places], QUANT_OPAD[places])

    def meridian(self, mstr=None, secs=True):
        """Return a 12hour time of day with meridian."""
        ret = None
        med = 'am'
        if self.timeval >= 43200:
            med = 'pm'
        if mstr is not None:
            med = mstr
        tv = self.timeval % 43200
        if tv < 3600:
            tv += 43200	# 12am/12pm 
        if secs:
            ret = dec2str(tv, 0, hoursep=':', minsep=':') + med
        else:
            ret = dec2hm(tv) + med
        return ret

    def rawtime(self, places=4, zeros=False, hoursep='h', minsep=':'):
        """Return time string component of the tod, without padding."""
        return dec2str(self.timeval, places, zeros, hoursep, minsep)

    def speedstr(self, dist=200):
        """Return an average speed estimate for the provided distance."""
        if self.timeval == 0:
            return '---.- km/h'
        return '{0:5.1f} km/h'.format(3.6 * float(dist) / float(self.timeval))

    def rawspeed(self, dist=200):
        """Return an average speed estimate without units."""
        if self.timeval == 0:
            return '-.-'
        return '{0:0.1f}'.format(3.6 * float(dist) / float(self.timeval))

    def copy(self):
        """Return a copy of the supplied tod."""
        return tod(self.timeval, self.index, self.chan, self.refid)

    def __lt__(self, other):
        if isinstance(other, tod):
            return self.timeval < other.timeval
        else:
            return self.timeval < other

    def __le__(self, other):
        if isinstace(other, tod):
            return self.timeval <= other.timeval
        else:
            return self.timeval <= other

    def __eq__(self, other):
        if isinstance(other, tod):
            return self.timeval == other.timeval
        else:
            return self.timeval == other

    def __ne__(self, other):
        if isinstance(other, tod):
            return self.timeval != other.timeval
        else:
            return self.timeval != other

    def __gt__(self, other):
        if isinstance(other, tod):
            return self.timeval > other.timeval
        else:
            return self.timeval > other

    def __ge__(self, other):
        if isinstance(other, tod):
            return self.timeval >= other.timeval
        else:
            return self.timeval >= other

    def __sub__(self, other):
        """Compute time of day subtraction and return a NET tod object.

        NOTE: 'other' always happens _before_ self, so a smaller value
              for self implies rollover of the clock. This mods all net
              times by 24Hrs.

        """
        ret = tod(index='', chan='NET', refid='')
        oval = other
        if isinstance(other, tod):
            oval = other.timeval
        if self.timeval >= oval:
            ret.timeval = self.timeval - oval
        else:
            ret.timeval = 86400 - oval + self.timeval
        return ret

    def __add__(self, other):
        """Compute time of day addition and return a new tod object.

        NOTE: 'other' is assumed to be a NET time interval. The returned
              tod will have a timeval mod 86400.

        """
        ret = tod(index='', chan='ToD', refid='')
        oval = other
        if isinstance(other, tod):
            oval = other.timeval
        ret.timeval = (self.timeval + oval) % 86400
        return ret

def now():
    """Return a now tod."""
    return tod('now')

class agg(tod):
    """A non-wrapped aggregate time.

       Promotion to aggregate time is 'sticky' and may be negative.

    """
    def __init__(self, timeval=0, index='', chan='', refid='', source=''):
        self.index = index[0:4]
        self.chan = chan ## chan[0:3]
        self.refid = refid
        self.source = source	# not really relevant in agg
        if isinstance(timeval, str):
            self.timeval = str2dec(timeval)
        elif isinstance(timeval, tod):
            self.timeval = timeval.timeval
        else:
            self.timeval = decimal.Decimal(timeval)

    def truncate(self, places=4):
        """Return a new ToD object with a truncated time value."""
        return agg(timeval=self.timeval.quantize(QUANT[places],
                rounding=decimal.ROUND_FLOOR), index='',
                                 chan='AGG', refid='')

    def __add__(self, other):
        """Compute addition and return aggregate."""
        ret = agg(index='', chan='AGG', refid='')
        oval = other
        if isinstance(other, tod):
            oval = other.timeval
        ret.timeval = self.timeval + oval
        return ret

    def __sub__(self, other):
        """Compute subtraction and return aggregate."""
        ret = agg(index='', chan='AGG', refid='')
        oval = other
        if isinstance(other, tod):
            oval = other.timeval
        ret.timeval = self.timeval - oval
        return ret

# ToD 'constants'
ZERO = tod()			# common cases
ONE = tod('1.0')
MINUTE = tod('1:00')
MAXELAP = tod('23h30:00')	# max displayed elapsed time
MAX = tod('23h59:59.9999')	# largest val possible

# Fake times for special cases
# these are impossible tods that still sort correctly
FAKETIMES = {
 'catch':ZERO,
 'w/o':ZERO,
 'max':MAX.copy(),
 'caught':MAX.copy(),
 'rel':MAX.copy(),	# last place -> checka
 'abort':MAX.copy(),	# similar to dnf?
 'otl':MAX.copy(),	# outside time limit / hd
 'dsq':MAX.copy(),	# disqualified
 'dnf':MAX.copy(),	# did not finish
 'dns':MAX.copy()}	# did not start
extra = decimal.Decimal('0.00001')
cof = decimal.Decimal('0.00001')
for c in ['caught', 'rel', 'abort', 'otl', 'dsq', 'dnf', 'dns']:
    FAKETIMES[c].timeval += cof
    cof += extra

## Convenience functions for speed conversions
def dr2t(dist, rate):
    """Convert distance (m) and rate (km/h) to time."""
    d = float(dist)
    r = float(rate)/3.6
    return tod(str(d/r))

class todlist():
    """ToD list helper class for managing splits and ranks."""
    def __init__(self, lbl=''):
        self.__label = lbl
        self.__store = []

    def __iter__(self):
        return self.__store.__iter__()

    def __len__(self):
        return len(self.__store)

    def __getitem__(self, key):
        return self.__store[key]

    def rank(self, bib, series=''):
        """Return current 0-based rank for given bib."""
        ret = None
        i = 0
        r = 0
        last = None
        for lt in self.__store:
            if last is not None:
                if lt != last:
                    r = i
            i += 1
            if lt.refid == bib and lt.index == series:
                ret = r
                break
            last = lt
        return ret

    def clear(self):
        self.__store = []

    def remove(self, bib, series=''):
        i = 0
        while i < len(self.__store):
            if self.__store[i].refid==bib and self.__store[i].index==series:
                del self.__store[i]
            else:
                i += 1

    def remove_first(self, bib, series=''):
        i = 0
        while i < len(self.__store):
            if self.__store[i].refid==bib and self.__store[i].index==series:
                del self.__store[i]
                break
            else:
                i += 1

    def insert(self, t, bib=None, series=''):
        """Insert t into ordered list."""
        ret = None
        if t in FAKETIMES: # re-assign a coded 'finish'
            t = FAKETIMES[t]

        if type(t) is tod:
            if bib is None:
                bib = t.index
            rt = tod(timeval=t.timeval, chan=self.__label,
                       refid=bib, index=series)
            last = None
            i = 0
            found = False
            for lt in self.__store:
                if rt < lt:
                    self.__store.insert(i, rt)
                    found = True
                    break
                i += 1
            if not found:
                self.__store.append(rt)

