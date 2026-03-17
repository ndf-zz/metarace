# SPDX-License-Identifier: MIT
"""Read weather data from Comet device or AC Weather API"""
import logging
import requests
import threading
import json
import os
import math
from random import random
from contextlib import suppress
from time import sleep, time
from datetime import datetime
from metarace import sysconf, savefile, default_file
from metarace.tod import mkagg, mktod
from urllib3.util import Url
from uuid import UUID, uuid4 as random_uuid
from queue import SimpleQueue, Empty

# Configuration defaults - via AC Weather API
_SOURCE = 'ac'
_HOSTNAME = 'weather.auscycling.org.au'
_PORT = 443
_USETLS = True
_LOCATION_ENDPOINT = '/api/locations'
_DATA_ENDPOINT = '/api/data'
_ADJUST_ENDPOINT = '/api/corrections'
_ADJUST_LIFETIME = 120
_POLLTIME = 59
_TIMEOUT = 10  # request timeout
_LOCATIONSCACHE = 'locations.json'
_ACSTALE = 900  # ~15 minutes validity

# Logging
_log = logging.getLogger('weather')
_log.setLevel(logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.ERROR)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Weather Data',
        'control': 'section',
    },
    'source': {
        'attr': 'source',
        'prompt': 'Source:',
        'control': 'choice',
        'hint': 'Data source',
        'defer': True,
        'conflicts': {
            'locationep': {
                'enable': 'ac',
                'disable': 'comet',
            },
            'usetls': {
                'enable': 'comet',
                'disable': 'ac',
            },
        },
        'options': {
            'ac': 'AusCycling Weather API',
            'comet': 'Comet Weather Station',
        },
        'default': 'ac',
    },
    'facility': {
        'prompt': 'Facility:',
        'attr': 'facility',
        'hint': 'Default facility code',
        'control': 'short',
        'default': None,
        'defer': True,
    },
    'dataep': {
        'prompt': 'Data:',
        'attr': 'dataep',
        'hint': 'Endpoint for weather data readings',
        'default': _DATA_ENDPOINT,
        'defer': True,
    },
    'locationep': {
        'prompt': 'Locations:',
        'attr': 'locationep',
        'hint': 'Endpoint for location IDs',
        'default': _LOCATION_ENDPOINT,
        'defer': True,
    },
    'adjustep': {
        'prompt': 'Adjustments:',
        'attr': 'adjustep',
        'hint': 'Endpoint for adjustment lookups',
        'default': _ADJUST_ENDPOINT,
        'defer': True,
    },
    'hostname': {
        'prompt': 'Hostname:',
        'attr': 'hostname',
        'hint': 'Hostname of weather service',
        'default': _HOSTNAME,
        'defer': True,
    },
    'port': {
        'prompt': 'Port:',
        'attr': 'port',
        'control': 'short',
        'hint': 'TCP port number',
        'type': 'int',
        'default': _PORT,
        'defer': True,
    },
    'usetls': {
        'prompt': 'Security:',
        'attr': 'usetls',
        'subtext': 'Use TLS?',
        'type': 'bool',
        'control': 'check',
        'hint': 'Connect using TLS',
        'default': _USETLS,
        'defer': True,
    },
    'polltime': {
        'prompt': 'Interval:',
        'attr': 'polltime',
        'control': 'short',
        'subext': 'seconds',
        'hint': 'Delay in seconds between readings',
        'type': 'int',
        'default': _POLLTIME,
        'defer': True,
    },
    'timeout': {
        'prompt': 'Timeout:',
        'attr': 'timeout',
        'control': 'short',
        'subext': 'seconds',
        'hint': 'Request timeout in seconds',
        'type': 'int',
        'default': _TIMEOUT,
        'defer': True,
    },
}


def _estimateDensity(t, h, p):
    """Return estimated density for given temperature, humidity and pressure."""
    return None


def _getFloatKey(data, key, default=None, min=0, max=1):
    ret = default
    if key in data and isinstance(data[key], float):
        ret = data[key]
        if ret is not None and ret < min:
            ret = None
        if ret is not None and ret > max:
            ret = None
    return ret


def _readAcWeather(data):
    """Read temperature, pressure and humidity from AC Weather record"""
    ret = None
    t = None
    h = None
    p = None
    d = None
    if isinstance(data, dict):
        lr = _getFloatKey(data,
                          'lastUpdated',
                          default=_ACSTALE,
                          min=0,
                          max=86400)
        t = _getFloatKey(data, 'temperature', min=-30, max=50)
        h = _getFloatKey(data, 'humidity', min=0, max=120)
        p = _getFloatKey(data, 'pressure', min=500, max=1100)
        d = _getFloatKey(data, 'rho', min=0.5, max=1.4)
    if t is not None and h is not None and p is not None and lr is not None:
        if lr < _ACSTALE:
            ret = (t, h, p, d)
        else:
            lt = mkagg(str(lr))
            _log.info(
                'AC Weather stale %s: %0.1f\u00B0C, %0.1fhPa, %0.1f%%, ~%0.4fkg/m^3',
                lt.rawtime(0), t, p, h, d)
    else:
        _log.info('AC Weather invalid: %r, %r, %r, %r, %r', t, p, h, d, lr)
    return ret


def _readComet(channels):
    """Read temperature, pressure and humidity from comet json channels"""
    # Assumes channel setup:
    #       1: Temperature (degrees C)
    #       2: Relative Humidity (%RH)
    #       5: Barometric Pressure (hPa)
    ret = None
    t = None
    h = None
    p = None
    d = None
    if isinstance(channels, list):
        with suppress(TypeError, ValueError):
            for channel in channels:
                if channel['name'] == 'Temperature':
                    t = float(channel['value'])
                elif channel['name'] == 'Relative humidity':
                    h = float(channel['value'])
                elif channel['name'] == 'Barometric pressure':
                    p = float(channel['value'])
    if t is not None and h is not None and p is not None:
        d = _estimateDensity(t, h, p)
        ret = (t, h, p, d)
    return ret


def Weather(facility=None):
    """Return a weather object based on configured source"""
    sysconf.add_section('weather', _CONFIG_SCHEMA)
    if sysconf.get_value('weather', 'source') == 'ac':
        return ACWeather(facility)
    else:
        if facility is None:
            facility = 'comet'
        return Comet(facility)


class BaseWeather(threading.Thread):
    """Base class for weather observations."""

    def __init__(self, facility=None):
        """Construct weather thread object."""
        threading.Thread.__init__(self, daemon=True)
        self._q = SimpleQueue()
        self.t = 0.0
        self.h = 0.0
        self.p = 0.0
        self.d = 0.0
        self._lt = None
        self._running = None
        self._s = None
        self._adjust = {}

        sysconf.add_section('weather', _CONFIG_SCHEMA)
        self._locationid = None
        self._facility = facility
        if self._facility is None:
            self._facility = sysconf.get_value('weather', 'facility')
        self._hostname = sysconf.get_value('weather', 'hostname')
        self._port = sysconf.get_value('weather', 'port')
        self._usetls = sysconf.get_value('weather', 'usetls')
        self._polltime = sysconf.get_value('weather', 'polltime')
        self._timeout = sysconf.get_value('weather', 'timeout')
        self._dataep = sysconf.get_value('weather', 'dataep')
        self._locationep = sysconf.get_value('weather', 'locationep')
        self._adjustep = sysconf.get_value('weather', 'adjustep')
        # todo: strip relative path from front of endpoints
        self._scheme = 'https' if self._usetls else 'http'

        # sanity check params before spinning up
        if not self._facility or not self._hostname:
            _log.debug('Weather service not configured')

    def valid(self):
        """Return true if current measurements are valid."""
        age = None
        if self._lt is not None:
            # compare with now and return age
            age = time() - self._lt
        return age is not None and age < 2 * self._polltime

    def exit(self):
        """Request thread termination."""
        self._running = False
        self._q.put(None)

    def _read(self):
        """Update weather readings"""
        pass

    def _req_adjust(self, reqid):
        """Request weather adjustments for a queued detail object."""
        if reqid in self._adjust:
            adjust = self._adjust[reqid]
            adjust['status'] = 'not implemented'
            _log.debug('%s[%s] Adjustment %r not implemented', self._facility,
                       self.native_id, reqid)
        else:
            _log.debug('%s[%s] Adjustment %r not found', self._facility,
                       self.native_id, reqid)

    def _del_adjust(self, reqid):
        """Remove a previously requested adjustment."""
        if reqid in self._adjust:
            _log.debug('%s[%s] Adjustment %r removed', self._facility,
                       self.native_id, reqid)
            del (self._adjust[reqid])

    def _prune_adjust(self):
        """Remove any stale adjustments."""
        dels = set()
        nowtime = time()
        for reqid, adjust in self._adjust.items():
            elap = nowtime - adjust['time']
            if elap > _ADJUST_LIFETIME:
                dels.add(reqid)
        for reqid in dels:
            self._del_adjust(reqid)

    def trigger(self):
        """Force a re-reading of API."""
        self._q.put(('trigger', ))

    def del_adjust(self, reqid):
        """Request removal of previously requested adjustment."""
        self._q.put(('del-adjust', reqid))

    def adjust_info(self, reqid):
        """Return information string for specified request."""
        ret = None
        if reqid in self._adjust:
            url = self._adjust[reqid]['url']
            if url is not None:
                ds = datetime.fromtimestamp(
                    self._adjust[reqid]['time']).astimezone()
                ret = 'Adjustments from %s %s' % (
                    url, ds.isoformat(timespec='seconds'))
        return ret

    def check_adjust(self, reqid):
        """Request status of previously requested adjustment.

        Return value is one of:

            None: Unknown reqid
            'requested': Request had been queued, but not processed
            'busy': Request is being processed
            'complete': Request was completed successfully, detail updated
            'error': One or more errors were encountered processing detail
            'not implemented': Weather object does not support adjustments
        """
        ret = None
        if reqid in self._adjust:
            ret = self._adjust[reqid]['status']
        return ret

    def req_adjust(self, detail, lap1id=None):
        """Request weather-adjusted values for provided detail object.

        Returns a key that can be used to query status of request.

        If lap1id is provided, use that split for the end of lap 1,
        otherwise a flying start is assumed.
        """
        reqid = str(random_uuid())
        self._adjust[reqid] = {
            'detail': detail,
            'status': 'requested',
            'time': time(),
            'lap1id': lap1id,
            'url': None,
        }
        self._q.put(('req-adjust', reqid))
        return reqid

    def run(self):
        """Called via Thread.start()."""
        _log.debug('Starting %s[%s]', self._facility, self.native_id)
        if self._running is None:
            # may be set False before run is called
            self._running = True
        with requests.Session() as self._s:
            ltime = 0
            while self._running:
                # fetch next weather observation
                try:
                    nowtime = time()
                    elap = nowtime - ltime
                    if elap > self._polltime:
                        if self._facility:
                            self._read()
                        if self._adjust:
                            self._prune_adjust()
                        ltime = nowtime
                        elap = 0
                    ndelay = max(
                        1, self._polltime + 0.10 * self._polltime * random() -
                        elap)
                    command = self._q.get(timeout=ndelay)
                    if command is not None:
                        _log.debug('%s[%s] command: %r', self._facility,
                                   self.native_id, command)
                        if command[0] == 'req-adjust':
                            self._req_adjust(command[1])
                        elif command[0] == 'del-adjust':
                            self._del_adjust(command[1])
                        elif command[0] == 'trigger':
                            ltime = 0
                        else:
                            _log.debug('%s[%s] unknown command %r',
                                       self._facility, self.native_id,
                                       command[0])
                except Empty:
                    pass
                except Exception as e:
                    _log.warning('%s[%s] %s: %s', self._facility,
                                 self.native_id, e.__class__.__name__, e)
                    sleep(10)
        _log.debug('Exit %s[%s]', self._facility, self.native_id)

    def adjust(self, detail):
        """Update the provided detail object with weather-adjusted times."""
        pass

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.exit()
        if exc_type is not None:
            return False  # raise exception
        self.join()
        return True


class ACWeather(BaseWeather):
    """AC Weather API object class."""

    def set_facility(facility):
        """Update the facility code."""
        self._lt = None
        self._locationid = None
        self._facility = facility

    def _req_adjust(self, reqid):
        """Request weather adjustments for a queued detail object."""
        if reqid in self._adjust:
            adjust = self._adjust[reqid]
            self._fetch_adjustments(adjust)
        else:
            _log.debug('%s[%s] Adjustment %r not found', self._facility,
                       self.native_id, reqid)

    def _fetch_adjustments(self, adjust):
        """Fetch adjusted times, update detail and return status."""
        adjust['status'] = 'busy'
        try:
            detail = adjust['detail']
            lap1id = adjust['lap1id']
            if detail and isinstance(detail, dict):
                request = []
                count = 0
                for rider, data in detail.items():
                    lap1 = None
                    lap1val = None
                    weather = data['weather']
                    if weather is not None:
                        for sid, split in data['splits'].items():
                            stime = mktod(split['elapsed'])
                            if stime is not None:
                                if lap1id:
                                    # standing start
                                    if lap1 is None:
                                        lap1val = float(stime.timeval)
                                    if sid == lap1id:
                                        lap1 = sid
                                req = {
                                    'Temp': weather['t'],
                                    'Press': weather['p'],
                                    'Hum': weather['h'],
                                    'TotalTime': float(stime.timeval),
                                    'Lap1': lap1val,
                                }
                                request.append((req, rider, sid, split))
                if request:
                    # send request to ACweather
                    url = Url(scheme=self._scheme,
                              host=self._hostname,
                              port=self._port,
                              path=self._adjustep).url
                    adjust['url'] = self._hostname
                    reqlist = [r[0] for r in request]
                    _log.debug('%s[%s] Request(%d): %r', self._facility,
                               self.native_id, len(reqlist), reqlist)
                    r = self._s.post(url, json=reqlist, timeout=self._timeout)
                    if r.status_code == 200:
                        response = r.json()
                        _log.debug('%s[%s] Response(%d): %r', self._facility,
                                   self.native_id, len(response), response)
                        for idx, adjustment in enumerate(response):
                            adjtime = mktod('%0.3f' % (adjustment, ))
                            split = request[idx][3]
                            split['adjusted'] = adjtime
                        adjust['status'] = 'complete'
                    else:
                        _log.debug('%s[%s] Invalid adjustment response %r',
                                   self._facility, self.native_id,
                                   r.status_code)
                        adjust['status'] = 'error'
                else:
                    _log.debug('%s[%s] Empty adjustment request',
                               self._facility, self.native_id)
                    adjust['status'] = 'error'
            else:
                _log.debug('%s[%s] Invalid adjustment request', self._facility,
                           self.native_id)
                adjust['status'] = 'error'
        except Exception as e:
            _log.debug('%s[%s] Adjustment error: %s', self._facility,
                       self.native_id, e)
            adjust['status'] = 'error'

    def _updatelocations(self):
        """Fetch the locations data from AC Weather."""
        try:
            url = Url(scheme=self._scheme,
                      host=self._hostname,
                      port=self._port,
                      path=self._locationep).url
            r = self._s.get(url, timeout=self._timeout)
            if r.status_code == 200:
                jd = r.json()
                with savefile(_LOCATIONSCACHE) as f:
                    json.dump(jd, f, indent=1)
                _log.debug('Loaded %d AC Weather locations from %s', len(jd),
                           url)
            else:
                _log.debug('Invalid location response: %d', r.status_code)
        except Exception as e:
            _log.debug('%s loading AC Weather locations: %s',
                       e.__class__.__name__, e)

    def _getlocation(self):
        """Fetch the location id for the configured facility code."""
        if self._locationid is not None:
            return self._locationid
        lcache = default_file(_LOCATIONSCACHE)
        if not os.path.exists(lcache):
            self._updatelocations()
        if os.path.exists(lcache):
            with open(lcache) as f:
                for v in json.load(f):
                    if 'venueCode' in v and v['venueCode'] == self._facility:
                        if 'id' in v and v['id']:
                            self._locationid = str(UUID(v['id']))
                            break
                        else:
                            _log.debug('AC Weather invalid location')
                else:
                    _log.debug('AC Weather facility %s not found',
                               self._facility)
        else:
            _log.debug('AC Weather locations cache file missing')
        return self._locationid

    def _read(self):
        """Update weather readings."""
        if self._getlocation() is None:
            _log.warning('Location ID for %s not found, weather disabled',
                         self._facility)
            self._facility = None
            return
        try:
            url = Url(scheme=self._scheme,
                      host=self._hostname,
                      port=self._port,
                      path=self._dataep).url
            r = self._s.get(url,
                            params={'locationId': self._locationid},
                            timeout=self._timeout)
            if r.status_code == 200:
                nv = _readAcWeather(r.json())
                if nv is not None:
                    self._lt = time()
                    self.t = nv[0]
                    self.h = nv[1]
                    self.p = nv[2]
                    self.d = nv[3]
                    _log.debug(
                        '%s: %0.1f\u00B0C, %0.1fhPa, %0.1f%%, ~%0.4fkg/m^3',
                        self._facility, self.t, self.p, self.h, self.d)
                else:
                    _log.info('Error reading %s data from %s', self._facility,
                              self._hostname)
            else:
                _log.info('Invalid response for %s: %d', self._facility,
                          r.status_code)
        except Exception as e:
            _log.warning('%s reading %s weather from %s: %s',
                         e.__class__.__name__, self._facility, self._hostname,
                         e)


class Comet(BaseWeather):
    """Comet device object class."""

    def _read(self):
        """Fetch values from comet and update internal state"""
        try:
            url = Url(scheme=self._scheme,
                      host=self._hostname,
                      port=self._port,
                      path=self._dataep).url
            r = self._s.get(url, timeout=self._timeout)
            if r.status_code == 200:
                jd = r.json()
                if 'ch' in jd:
                    nv = _readComet(jd['ch'])
                    if nv is not None:
                        self._lt = time()  # use current host time
                        self.t = nv[0]
                        self.h = nv[1]
                        self.p = nv[2]
                        self.d = nv[3]
                        _log.debug(
                            '%s: %0.1f\u00B0C, %0.1fhPa, %0.1f%%, ~%0.4kg/m^3',
                            self._facility, self.t, self.p, self.h, self.d)
                    else:
                        _log.info('Error reading %s data from %s',
                                  self._facility, self._hostname)
                else:
                    _log.info('Invalid %s data from %s', self._facility,
                              self._hostname)
            else:
                _log.info('Invalid response for %s: %d', self._facility,
                          r.status_code)
        except Exception as e:
            _log.warning('%s reading %s weather from %s: %s',
                         e.__class__.__name__, self._facility, self._hostname,
                         e)
