# SPDX-License-Identifier: MIT
"""Read weather data from Comet device via http value fetch"""
import logging
import requests
import threading
from random import random
from contextlib import suppress
from time import sleep, time
from metarace import sysconf

# Configuration defaults
_HOSTNAME = 'localhost'
_PORT = 80
_USETLS = False
_POLLTIME = 29
_FILENAME = 'values.json'
_TIMEOUT = 5  # HTTP request timeout

# Logging
_log = logging.getLogger('comet')
_log.setLevel(logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.ERROR)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Comet Weather Station',
        'control': 'section',
    },
    'hostname': {
        'prompt': 'Hostname:',
        'attr': 'hostname',
        'hint': 'Hostname or IP of weather station device',
        'default': _HOSTNAME,
    },
    'port': {
        'prompt': 'Port:',
        'attr': 'port',
        'control': 'short',
        'hint': 'TCP port number',
        'type': 'int',
        'default': _PORT,
    },
    'usetls': {
        'prompt': 'Security:',
        'attr': 'usetls',
        'subtext': 'Use TLS?',
        'type': 'bool',
        'control': 'check',
        'hint': 'Connect to weather station using TLS',
        'default': _USETLS,
    },
    'polltime': {
        'prompt': 'Interval:',
        'attr': 'polltime',
        'control': 'short',
        'subext': 'seconds',
        'hint': 'Delay in seconds between readings',
        'type': 'int',
        'default': _POLLTIME,
    },
    'filename': {
        'prompt': 'Filename:',
        'attr': 'filename',
        'hint': 'Data filename on weather station',
        'default': _FILENAME,
    },
}


def _readValues(channels):
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


class Comet(threading.Thread):
    """Timy thread object class."""

    def __init__(self):
        """Construct comet thread object."""
        threading.Thread.__init__(self, daemon=True)
        self.t = 0.0
        self.h = 0.0
        self.p = 0.0
        self._lt = None
        self.__running = None
        self.__s = None

        sysconf.add_section('comet', _CONFIG_SCHEMA)
        self._hostname = sysconf.get_value('comet', 'hostname')
        self._port = sysconf.get_value('comet', 'port')
        self._usetls = sysconf.get_value('comet', 'usetls')
        self._polltime = sysconf.get_value('comet', 'polltime')
        self._filename = sysconf.get_value('comet', 'filename')

    def valid(self):
        """Return true if current measurements are valid."""
        age = None
        if self._lt is not None:
            # compare with now and return age
            age = time() - self._lt
        return age is not None and age < 2 * self._polltime

    def exit(self):
        """Request thread termination."""
        _log.debug('request to exit')
        self.__running = False

    def __read(self):
        url = 'http%s://%s:%d/%s' % ('s' if self._usetls else '',
                                     self._hostname, self._port,
                                     self._filename)
        r = self.__s.get(url, timeout=_TIMEOUT)
        if r.status_code == 200:
            jd = r.json()
            if 'ch' in jd:
                nv = _readValues(jd['ch'])
                if nv is not None:
                    self._lt = time()
                    self.t = nv[0]
                    self.h = nv[1]
                    self.p = nv[2]
                else:
                    _log.debug('Error reading channels from %s',
                               self._hostname)
            else:
                _log.debug('Invalid weather data from %s', self._hostname)
        else:
            _log.error('Invalid read response: %d', r.status_code)

    def run(self):
        """Called via Thread.start()."""
        _log.debug('Starting')
        if self.__running is None:
            # exit may set this to False before run is called
            self.__running = True
        with requests.Session() as self.__s:
            while self.__running:
                try:
                    self.__read()
                except Exception as e:
                    _log.error('%s: %s', e.__class__.__name__, e)
                sleep(self._polltime + 0.25 * self._polltime * random())
        _log.debug('exiting')

    def __enter__(self):
        _log.debug('enter context')
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _log.debug('exit context exc_type=%r', exc_type)
        self.exit()
        if exc_type is not None:
            return False  # raise exception
        self.join()
        return True
