# SPDX-License-Identifier: MIT
"""Time of Day types and functions.

Time of Day (tod) records are used to compute net times,
and to communicate context of timing events. Each tod object
includes the following properties:

	timeval	decimal number of seconds, to 6 places
	index	optional serial number or marker (from timing device)
	chan	optional timing channel number or indicator
	refid	optional transponder id or rider identifier
	source	optional source id of timing device that generated the tod

Two specific types are provided:

	tod	Time of Day, strictly >= 0 and less than 24 hours,
		arithmetic is mod 24 hours.
	agg	Aggregate time, may be greater than 24 hours,
		negative values permitted.

Supported arithmetic operations:

		Y:	tod	agg	int	decimal
	tod - Y		yes	no	no	no	*
	tod + Y		yes	no	no	no	*
	agg - Y		yes	yes	yes	yes
	agg + Y		yes	yes	yes	yes

	* Result is mod 24 hours

"""

import decimal
import re
import logging
from datetime import datetime, time
from dateutil.parser import isoparse, parse as dateparse
from bisect import bisect_left as _bisect

# module log object
_log = logging.getLogger('tod')
_log.setLevel(logging.DEBUG)

# Formatting and truncation constants
QUANT_6PLACES = decimal.Decimal('0.000001')
QUANT_5PLACES = decimal.Decimal('0.00001')
QUANT_4PLACES = decimal.Decimal('0.0001')
QUANT_3PLACES = decimal.Decimal('0.001')
QUANT_2PLACES = decimal.Decimal('0.01')
QUANT_1PLACE = decimal.Decimal('0.1')
QUANT_0PLACES = decimal.Decimal('1')
QUANT = [
    QUANT_0PLACES, QUANT_1PLACE, QUANT_2PLACES, QUANT_3PLACES, QUANT_4PLACES,
    QUANT_5PLACES, QUANT_6PLACES
]
QUANT_FW = [2, 4, 5, 6, 7, 8, 9]
QUANT_TWID = [8, 10, 11, 12, 13, 14, 15]
QUANT_PAD = ['     ', '   ', '  ', ' ', '', '', '']
QUANT_OPAD = ['    ', '  ', ' ', '', '', '', '']
MILL = decimal.Decimal(1000000)

# default rounding is toward zero
ROUNDING = decimal.ROUND_DOWN
TRUNCATE = decimal.ROUND_DOWN
ROUND = decimal.ROUND_HALF_EVEN


def now(index='', chan='CLK', refid='', source=''):
    """Return a tod set to the current local time."""
    return tod(_now2dec(), index, chan, refid, source)


def fromobj(obj):
    """Create tod from serialized object"""
    ret = None
    try:
        timeval = obj['timeval']
        if '__agg__' in obj:
            ret = agg(timeval)
        else:
            ret = tod(timeval)
        for attr in ('index', 'chan', 'refid', 'source'):
            if attr in obj:
                setattr(ret, attr, obj[attr])
    except Exception as e:
        _log.warning('%s deserializing tod: %s', e.__class__.__name__, e)
    return ret


def fromdate(timestr=''):
    """Try to parse the provided str as a local datetime"""
    rd = None
    rt = None
    try:
        # retrieve date and time for the current timezone
        d = dateparse(timestr).astimezone()
        rd = d.date().isoformat()
        tv = 3600 * d.hour + 60 * d.minute + d.second + d.microsecond / MILL
        rt = mktod(tv)
        rt.source = timestr
    except Exception as e:
        _log.debug('fromdate() %s: %s', e.__class__.__name__, e)
    return (rd, rt)


def mergedate(ltime=None, date=None, micros=False):
    """Merge localtime in ltime with date, return an aware datetime"""
    if ltime is None:
        ltime = now()
    places = 0
    if micros:
        places = 6
    lt = time.fromisoformat(
        ltime.rawtime(places=places, hoursep=':', zeros=True))
    if date is None:
        date = datetime.now().astimezone()
    ld = date.replace(hour=lt.hour,
                      minute=lt.minute,
                      second=lt.second,
                      microsecond=lt.microsecond)
    return ld


def fromiso(timestr=''):
    """Retrieve date and TOD from 8601 date and time of day string"""
    rd = None
    rt = None
    try:
        # retrieve date and time for the current timezone
        d = isoparse(timestr).astimezone()
        rd = d.date().isoformat()
        tv = 3600 * d.hour + 60 * d.minute + d.second + d.microsecond / MILL
        rt = mktod(tv)
        rt.source = timestr
    except Exception as e:
        _log.debug('fromiso() %s: %s', e.__class__.__name__, e)
    return (rd, rt)


def fromqc(timestr=''):
    """Retrieve date and TOS from Queclink datestamp"""
    rd = None
    rt = None
    if isinstance(timestr, str) and len(timestr) == 14 and timestr.isdigit():
        stamp = '{}T{}Z'.format(timestr[0:8], timestr[8:14])
        (rd, rt) = fromiso(stamp)
    else:
        _log.debug('fromqc(): Invalid datestamp %r', timestr)
    return (rd, rt)


def mkagg(timeval=''):
    """Return agg for given timeval or None."""
    ret = None
    if timeval is not None and timeval != '':
        try:
            ret = agg(timeval)
        except Exception as e:
            _log.debug('mkagg() %s: %s', e.__class__.__name__, e)
    return ret


def mktod(timeval=''):
    """Return tod for given timeval or None."""
    ret = None
    if timeval is not None and timeval != '':
        try:
            ret = tod(timeval)
        except Exception as e:
            _log.debug('mktod() %s: %s', e.__class__.__name__, e)
    return ret


def _now2dec():
    """Create a decimal timevalue for the current local time."""
    dv = datetime.now()
    ret = (dv.microsecond / MILL).quantize(QUANT_4PLACES)
    ret += 3600 * dv.hour + 60 * dv.minute + dv.second
    return ret


def _dec2hm(dectod=None):
    """Return truncated time string in hours and minutes."""
    strtod = None
    if dectod is not None:
        if dectod >= 3600:  # 'HH:MM'
            strtod = '{0}:{1:02}'.format(
                int(dectod) // 3600, (int(dectod) % 3600) // 60)
        else:  # 'M'
            strtod = '{0}'.format(int(dectod) // 60)
    return strtod


def _dec2ms(dectod=None, places=0, minsep=':'):
    """Return stopwatch type string M:SS[.dcmz]."""
    strtod = None
    if dectod is not None:
        sign = ''
        dv = dectod.quantize(QUANT[places], rounding=ROUNDING)
        if dv.is_signed():
            dv = dv.copy_negate()
            sign = '-'
        # '-M:SS.dcmz'
        strtod = '{0}{1}{2}{3:0{4}}'.format(sign,
                                            int(dv) // 60, minsep, dv % 60,
                                            QUANT_FW[places])
    return strtod


def _dec2str(dectod=None, places=4, zeros=False, hoursep='h', minsep=':'):
    """Return formatted string for given tod decimal value.

    Optional argument 'zeros' will use leading zero chars
    up to 24 hours. eg:

             '00h00:01.2345'   zeros=True
                    '1.2345'   zeros=False
    """
    strtod = None
    if dectod is not None:
        sign = ''
        dv = dectod.quantize(QUANT[places], rounding=ROUNDING)
        if dv.is_signed():
            dv = dv.copy_negate()
            sign = '-'
        if zeros or dv >= 3600:  # '-HhMM:SS.dcmz'
            fmt = '{0}{1}{2}{3:02}{4}{5:0{6}}'
            if zeros:  # '-00h00:0S.dcmz'
                fmt = '{0}{1:02}{2}{3:02}{4}{5:0{6}}'
            strtod = fmt.format(sign,
                                int(dv) // 3600, hoursep,
                                (int(dv) % 3600) // 60, minsep, dv % 60,
                                QUANT_FW[places])
        elif dv >= 60:  # '-M:SS.dcmz'
            strtod = '{0}{1}{2}{3:0{4}}'.format(sign,
                                                int(dv) // 60, minsep, dv % 60,
                                                QUANT_FW[places])
        else:  # '-S.dcmz'
            strtod = '{0}{1}'.format(sign, dv)
    return strtod


def _str2dec(timestr=''):
    """Return decimal for given string.

    Attempt to match against patterns:
    	-HhMM:SS.dcmz		Canonical
    	-H:MM:SS.dcmz		Omega
    	-H:MM'SS"dcmz		Chronelec
    	-H-MM-SS.dcmz		Keypad entry
        PThHmMs.dcmzS		ISO8601 Interval
    """
    dectod = None
    timestr = timestr.strip()  # assumes string
    if timestr == 'now':
        dectod = _now2dec()
    elif timestr.startswith('PT'):
        # interpret as ISO8601 Interval (4.4.1b), but only time flags
        m = re.match(
            r'^PT((\d+([\.\,]\d+)?)H)?((\d+([\.\,]\d+)?)M)?((\d+([\.\,]\d+)?)S)?',
            timestr)
        if m is not None:
            dectod = 0
            if m.group(2):
                dectod += 3600 * decimal.Decimal(m.group(2).replace(',', '.'))
            if m.group(5):
                dectod += 60 * decimal.Decimal(m.group(5).replace(',', '.'))
            if m.group(8):
                dectod += decimal.Decimal(m.group(8).replace(',', '.'))
        else:
            _log.info('_str2dec() Invalid 8601 interval: %r', timestr)
    else:
        m = re.match(
            r'^(-?)(?:(?:(\d+)[h:-])?(\d{1,2})[:\'-])?(\d{1,2}(?:[\.\"]\d+)?)$',
            timestr)
        if m is not None:
            dectod = decimal.Decimal(m.group(4).replace('"', '.'))
            dectod += decimal.Decimal(m.group(3) or 0) * 60
            dectod += decimal.Decimal(m.group(2) or 0) * 3600
            if m.group(1):  # negative sign
                dectod = dectod.copy_negate()
        else:
            dectod = decimal.Decimal(timestr)
            #_log.debug('_str2dec() Decimal conversion %s => %s', timestr,
            #dectod)
    return dectod


def _tv2dec(timeval):
    """Convert the provided value into a decimal timeval for tod/agg."""
    ret = 0
    if isinstance(timeval, decimal.Decimal):
        ret = timeval
    elif isinstance(timeval, str):
        ret = _str2dec(timeval)
    elif isinstance(timeval, tod):
        # Discard context on supplied tod and copy decimal obj
        ret = timeval.timeval
    elif isinstance(timeval, float):
        # Round off float to max tod precision
        ret = decimal.Decimal('{0:0.6f}'.format(timeval))
    else:
        ret = decimal.Decimal(timeval)
    return ret


class tod:
    """A class for representing time of day, net time and RFID events."""

    def __init__(self, timeval=0, index='', chan='', refid='', source=''):
        self.index = index
        self.chan = chan
        self.refid = refid
        self.source = source
        self.timeval = _tv2dec(timeval)
        if self.timeval < 0 or self.timeval >= 86400:
            raise ValueError('Time of day value not in range [0, 86400)')

    def __str__(self):
        """Return a normalised tod string."""
        return str(self.__unicode__())

    def __unicode__(self):
        """Return a normalised tod string."""
        return '{0: >5} {1: <3} {2} {3} {4}'.format(self.index, self.chan,
                                                    self.timestr(4),
                                                    self.refid, self.source)

    def __repr__(self):
        """Return object representation string."""
        return "{5}({0}, {1}, {2}, {3}, {4})".format(repr(self.timeval),
                                                     repr(self.index),
                                                     repr(self.chan),
                                                     repr(self.refid),
                                                     repr(self.source),
                                                     self.__class__.__name__)

    def serialize(self):
        """Return serialized object for JSON export"""
        obj = {'__tod__': 1, 'timeval': str(self.timeval)}
        for attr in ('index', 'chan', 'refid', 'source'):
            val = getattr(self, attr)
            if val:
                obj[attr] = val
        return obj

    def round(self, places=4):
        """Return a new rounded time value."""
        return self.places(places, ROUND, 'ROUND')

    def truncate(self, places=4):
        """Return a new truncated time value."""
        return self.places(places, TRUNCATE, 'TRUNC')

    def places(self, places=4, rounding=ROUNDING, flag='PLACES'):
        return self.__class__(timeval=self.timeval.quantize(QUANT[places],
                                                            rounding=rounding),
                              chan=flag)

    def as_hours(self, places=0):
        """Return decimal value in hours, truncated to the desired places."""
        return (self.timeval / 3600).quantize(QUANT[places], rounding=ROUNDING)

    def as_minutes(self, places=0):
        """Return decimal value in minutes, truncated to the desired places."""
        return (self.timeval / 60).quantize(QUANT[places], rounding=ROUNDING)

    def as_seconds(self, places=0):
        """Return decimal value in seconds, truncated to the desired places."""
        return self.timeval.quantize(QUANT[places], rounding=ROUNDING)

    def timestr(self, places=4, zeros=False, hoursep='h', minsep=':'):
        """Return time string component of the tod, whitespace padded."""
        return '{0: >{1}}{2}'.format(
            _dec2str(self.timeval, places, zeros, hoursep, minsep),
            QUANT_TWID[places], QUANT_PAD[places])

    def omstr(self, places=3, zeros=False, hoursep=':', minsep=':'):
        """Return a 12 digit 'omega' style time string."""
        if places > 3:
            places = 3  # Hack to clamp to 12 dig
        return '{0: >{1}}{2}'.format(
            _dec2str(self.timeval, places, zeros, hoursep, minsep),
            QUANT_TWID[places], QUANT_OPAD[places])

    def minsec(self, places=0, minsep=':'):
        """Return a stopwatch type string m:ss.[dcmz]."""
        return _dec2ms(self.timeval, places, minsep)

    def meridiem(self, mstr=None, secs=True):
        """Return a 12hour time of day string with meridiem."""
        ret = None
        med = '\u2006am'
        tv = self.timeval
        # unwrap timeval into a single 24hr period
        if tv >= 86400:
            tv = tv % 86400
        elif tv < 0:
            tv = 86400 - (tv.copy_abs() % 86400)

        # determine meridiem and adjust for display
        if tv >= 43200:
            med = '\u2006pm'
        if mstr is not None:
            med = mstr
        tv = tv % 43200
        if tv < 3600:  # 12am/12pm
            tv += 43200
        if secs:
            ret = _dec2str(tv, 0, hoursep=':', minsep=':') + med
        else:
            ret = _dec2hm(tv) + med
        return ret

    def isosecs(self, places=4):
        """Return ISO8601(4.4.1b) Refer : 4.4.3.2 Format with designators."""
        return "PT{}S".format(
            self.timeval.quantize(QUANT[places], rounding=ROUNDING))

    def isostr(self, places=4):
        """Return ISO8601(4.4.1b) Time interval string"""
        return "PT{}S".format(
            _dec2str(self.timeval, places, hoursep='H', minsep='M'))

    def rawtime(self, places=4, zeros=False, hoursep='h', minsep=':'):
        """Return time string of tod as string, without padding."""
        return _dec2str(self.timeval, places, zeros, hoursep, minsep)

    def speedstr(self, dist=200):
        """Return average speed estimate string for the provided distance."""
        if self.timeval == 0:
            return '---.-\u2006km/h'
        return '{0:5.1f}\u2006km/h'.format(3.6 * float(dist) /
                                           float(self.timeval))

    def rawspeed(self, dist=200):
        """Return an average speed estimate string without unit."""
        if self.timeval == 0:
            return '-.-'
        return '{0:0.1f}'.format(3.6 * float(dist) / float(self.timeval))

    def __lt__(self, other):
        if isinstance(other, tod):
            return self.timeval < other.timeval
        else:
            return self.timeval < other

    def __le__(self, other):
        if isinstance(other, tod):
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
        """Compute time of day subtraction and return a NET tod object."""
        if type(other) is not tod:  # Subclass must override this method
            return NotImplemented
        if self.timeval >= other.timeval:
            oft = self.timeval - other.timeval
        else:
            oft = 86400 - other.timeval + self.timeval
        return tod(timeval=oft, chan='NET')

    def __add__(self, other):
        """Compute time of day addition and return a new tod object."""
        if type(other) is not tod:  # Subclass must override this method
            return NotImplemented
        return tod(timeval=(self.timeval + other.timeval) % 86400, chan='SUM')

    def __pos__(self):
        """Unary + operation."""
        return self.__class__(self.timeval, chan='POS')

    def __abs__(self):
        """Unary absolute value."""
        return self.__class__(self.timeval.copy_abs(), chan='ABS')


class agg(tod):
    """Aggregate time type."""

    def __init__(self, timeval=0, index='', chan='', refid='', source=''):
        self.index = index
        self.chan = chan
        self.refid = refid
        self.source = source
        self.timeval = _tv2dec(timeval)

    def serialize(self):
        """Return serialized object for JSON export"""
        obj = {'__agg__': 1, 'timeval': str(self.timeval)}
        for attr in ('index', 'chan', 'refid', 'source'):
            val = getattr(self, attr)
            if val:
                obj[attr] = val
        return obj

    def __add__(self, other):
        """Compute addition and return aggregate."""
        if isinstance(other, tod):
            return agg(timeval=self.timeval + other.timeval, chan='AGG')
        elif isinstance(other, (int, decimal.Decimal)):
            return agg(timeval=self.timeval + other, chan='AGG')
        else:
            return NotImplemented

    def __sub__(self, other):
        """Compute subtraction and return aggregate."""
        if isinstance(other, tod):
            return agg(timeval=self.timeval - other.timeval, chan='AGG')
        elif isinstance(other, (int, decimal.Decimal)):
            return agg(timeval=self.timeval - other, chan='AGG')
        else:
            return NotImplemented

    def __neg__(self):
        """Unary - operation."""
        return self.__class__(self.timeval.copy_negate(), chan='AGG')


# TOD 'constants'
ZERO = tod()
ONE = tod(1)
MINUTE = tod('1:00')
MAX = tod('23h59:59.999980')  # largest val possible for tod
MAXELAP = tod('23h30:00')  # max displayed elapsed time

# Fake times for special cases
# these are unused tods that sort correctly when compared
FAKETIMES = {
    'catch': tod(ZERO, chan='catch'),
    'win': tod(ZERO, chan='catch'),
    'w/o': tod(ZERO, chan='w/o'),
    'max': tod(MAX, chan='max'),
    'caught': tod(MAX, chan='caught'),
    'lose': tod(MAX, chan='caught'),
    'rel': tod(MAX, chan='rel'),
    'otl': tod(MAX, chan='otl'),
    'abd': tod(MAX, chan='abd'),
    'dsq': tod(MAX, chan='dsq'),
    'dnf': tod(MAX, chan='dnf'),
    'dns': tod(MAX, chan='dns'),
}
extra = decimal.Decimal('0.000001')
cof = decimal.Decimal('0.000001')
for t in FAKETIMES.values():
    t.timeval += cof
    cof += extra


class todlist:
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

    def changeno(self, oldno, newno, oldseries='', newseries=''):
        """Update NO.series in result if it exists."""
        for lt in self.__store:
            if lt[0].refid == oldno and lt[0].index == oldseries:
                lt[0].refid = newno
                lt[0].index = newseries

    def rank(self, bib, series=''):
        """Return current 0-based rank for given bib."""
        ret = None
        count = 0
        i = 0
        lpri = None
        lsec = None
        for lt in self.__store:
            # scan times for updating ranks
            if lpri is not None:
                if lt[0] != lpri or lt[1] != lsec:
                    i = count
            # if rider matches, break
            if lt[0].refid == bib and lt[0].index == series:
                ret = i
                break
            lpri = lt[0]
            lsec = lt[1]
            count += 1
        return ret

    def clear(self):
        """Clear list"""
        self.__store = []
        return 0

    def remove(self, bib, series='', once=False):
        i = 0
        while i < len(self.__store):
            if (self.__store[i][0].refid == bib
                    and self.__store[i][0].index == series):
                del self.__store[i]
                if once:
                    break
            else:
                i += 1
        return i

    def insert(self, pri=None, sec=None, bib=None, series=''):
        """Insert primary tod and secondary tod into ordered list."""
        ret = None
        if isinstance(pri, str) and pri in FAKETIMES:
            pri = FAKETIMES[pri]

        if isinstance(pri, tod):
            if bib is None:
                bib = pri.index
            if sec is None:
                sec = ZERO
            rt0 = tod(pri, chan=self.__label, refid=bib, index=series)
            rt1 = tod(sec, chan=self.__label, refid=bib, index=series)
            ret = _bisect(self.__store, (rt0, rt1))
            self.__store.insert(ret, (rt0, rt1))
        return ret
