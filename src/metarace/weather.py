# SPDX-License-Identifier: MIT
"""Read weather data from Comet device or AC Weather API"""
import logging
import requests
import threading
import json
import os
from random import random
from contextlib import suppress
from time import sleep, time
from metarace import sysconf, savefile, default_file
from metarace.tod import mkagg
from urllib3.util import Url
from uuid import UUID

# Configuration defaults - via AC Weather API
_SOURCE = 'ac'
_HOSTNAME = 'weather.auscycling.org.au'
_PORT = 443
_USETLS = True
_LOCATION_ENDPOINT = '/api/locations'
_DATA_ENDPOINT = '/api/data'
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
    if isinstance(data, dict):
        lr = _getFloatKey(data,
                          'lastUpdated',
                          default=_ACSTALE,
                          min=0,
                          max=86400)
        t = _getFloatKey(data, 'temperature', min=-30, max=50)
        h = _getFloatKey(data, 'humidity', min=0, max=120)
        p = _getFloatKey(data, 'pressure', min=500, max=1100)
    if t is not None and h is not None and p is not None and lr is not None:
        if lr < _ACSTALE:
            ret = (t, h, p)
        else:
            lt = mkagg(str(lr))
            _log.info('AC Weather stale %s: %0.1f\u00B0C, %0.1f%%, %0.1fhPa',
                      lt.rawtime(0), t, h, p)
    else:
        _log.info('AC Weather invalid: %r, %r, %r, %r', t, h, p, lr)
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
        ret = (t, h, p)
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
        self.t = 0.0
        self.h = 0.0
        self.p = 0.0
        self._lt = None
        self._running = None
        self._s = None

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
        # todo: strip relative path from front of endpoints
        self._scheme = 'https' if self._usetls else 'http'

        # sanity check params before spinning up
        if not self._facility or not self._hostname:
            _log.debug('Weather service not configured')
            self._running = False

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

    def _read(self):
        """Update weather readings"""
        pass

    def run(self):
        """Called via Thread.start()."""
        _log.debug('Starting %s[%s]', self._facility, self.native_id)
        if self._running is None:
            # may be set False before run is called
            self._running = True
        with requests.Session() as self._s:
            while self._running:
                try:
                    self._read()
                except Exception as e:
                    _log.warning('%s[%s] %s: %s', self._facility,
                                 self.native_id, e.__class__.__name__, e)
                sleep(self._polltime + 0.25 * self._polltime * random())
        _log.debug('Exit %s[%s]', self._facility, self.native_id)

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
            self._running = False
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
                    _log.debug('%s: %0.1f\u00B0C, %0.1f%%, %0.1fhPa',
                               self._facility, self.t, self.h, self.p)
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
                        _log.debug('%s: %0.1f\u00B0C, %0.1f%%, %0.1fhPa',
                                   self._facility, self.t, self.h, self.p)
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
