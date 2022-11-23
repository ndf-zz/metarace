# SPDX-License-Identifier: MIT
"""Race Result USB Decoder interface."""

import threading
import queue
import decimal
import logging
import serial
from time import sleep

from . import (decoder, DECODER_LOG_LEVEL)
from metarace import tod
from metarace import sysconf
from metarace import strops

_log = logging.getLogger('metarace.decoder.rru')
_log.setLevel(logging.DEBUG)

_RRU_BAUD = 19200
_RRU_PASSLEN = 12
_RRU_BEACONLEN = 17
_RRU_LOWBATT = 2.1  # Warn if battery voltage is below this many volts
_RRU_REFCHECK = 1800  # check ref after this many timeouts
_RRU_REFTHRESH = 0x2a30000  # 2 x 86400 x 256
_RRU_ENCODING = 'iso8859-1'
_RRU_MARKER = '_____127'  # trigger marker
_RRU_EOL = '\n'
# Serial port I/O read timeout in seconds
_RRU_IOTIMEOUT = 1.0
# List of handled responses from decoder
_REPLIES = [
    'ASCII',
    'CONFSET',
    'CONFGET',
    'INFOGET',
    'SITESURVEY',
    'TIMESTAMPGET',
    'EPOCHREFGET',
    'EPOCHREFSET',
    'EPOCHREFADJ1D',
    'PASSINGGET',
    'PASSINGINFOGET',
    'BEACONGET',
    'PREWARN',
]
# Documented configuration parameter. If default is not None, the
# value will be set in _sane().
_CONFINFO = {
    '01': {
        'label': 'Push Pre-Warn',
        'default': None,
        '00': 'disabled',
        '01': 'enabled'
    },
    '02': {
        'label': 'Blink/beep on repeated passing',
        'default': None,
        '00': 'disabled',
        '01': 'enabled'
    },
    '03': {
        'label': 'Impulse input or beep output',
        'default': None,
        '00': 'impulse-in',
        '01': 'beep-out'
    },
    '04': {
        'label': 'Auto-shutdown on power loss',
        # force disabled since USB cable connection often fails
        'default': '00',
        '00': 'disabled',
        '01': 'enabled'
    },
    '05': {
        'label': 'Operation Mode',
        # assume usb-timing is required unless explicity configured otherwise
        'default': '06',
        '05': 'usb-kiosk',
        '06': 'usb-timing',
        '07': 'usb-store&copy'
    },
    '06': {
        'label': 'Channel ID',
        'default': None,
        '00': '1',
        '01': '2',
        '02': '3',
        '03': '4',
        '04': '5',
        '05': '6',
        '06': '7',
        '07': '8'
    },
    '07': {
        'label': 'Loop ID',
        'default': None,
        '00': '1',
        '01': '2',
        '02': '3',
        '03': '4',
        '04': '5',
        '05': '6',
        '06': '7',
        '07': '8'
    },
    '08': {
        'label': 'Loop Power',
        'default': None
    },
    '09': {
        'label': 'Blink dead-time',
        'default': None
    },
    '0a': {
        'label': 'Charging via USB',
        'default': None,
        '00': 'disabled',
        '01': 'enabled'
    },
    '0b': {
        'label': 'Use DTR',
        # always use DTR, unless configured otherwise
        'default': '01',
        '00': 'disabled',
        '01': 'enabled'
    },
    '0c': {
        'label': 'Alternate Channel Switching',
        'default': None,
        '00': 'disabled',
        '01': 'automatic',
        '02': 'force'
    },
    '0d': {
        'label': 'Box Mode',
        'default': None,
        '31': 'check',
        '32': 'deep-sleep',
        '33': 'health-check',
        '34': 'tracking',
        '41': 'usb-timing',
    },
    'a0': {
        'label': 'Tray Scan Power',
        'default': None,
    },
    'a1': {
        'label': 'Tray Scan interval',
        'default': None,
    },
    'a2': {
        'label': 'Tray Scan ramp up delay',
        'default': None,
    },
    'a3': {
        'label': 'Tray Scan row to column delay',
        'default': None,
    },
    'a4': {
        'label': 'Repeat Row and Column cycle for another N repetition',
        'default': None,
    },
    'b1': {
        'label': 'CheckSum',
        'default': None,
        '0': 'disabled',
        '1': 'enabled',
    },
    'b2': {
        'label': 'Push Passings',
        'default': None,
        '0': 'disabled',
        '1': 'enabled',
    }
}
# Labels for decoder information options
_INFOLBLS = {
    '01': 'Decoder ID',
    '02': 'Firmware Major Version',
    '03': 'Hardware Version',
    '04': 'Box Type',
    '05': 'Battery Voltage',
    '07': 'Battery State',
    '08': 'Battery Level',
    '09': 'Internal Temperature',
    '0a': 'Supply Voltage',
    '0b': 'Loop Status',
    '0c': 'Firmware Minor Version',
}
_BOX_TYPES = {
    '0a': 'active-ext',
    '1e': 'management-box',
    '28': 'usb-timing-box'
}
_BATTERY_STATES = {
    '00': 'Fault',
    '01': 'Charging',
    '02': 'Reduced Charging',
    '03': 'Discharging'
}
_LOOP_STATES = {
    '00': 'OK',
    '01': 'Fault',
    '02': 'Limit',
    '03': 'Overvoltage Error'
}


class rru(decoder):
    """Race Result USB Active Decoder"""

    def __init__(self):
        decoder.__init__(self)
        self._sitenoise = {
            1: 100,
            2: 100,
            3: 100,
            4: 100,
            5: 100,
            6: 100,
            7: 100,
            8: 100
        }
        self._config = {}
        self._boxname = None
        self._rrustamp = None
        self._rruht = None
        self._error = False
        self._io = None
        self._rdbuf = b''
        self._curreply = None  # current multi-line response mode
        self._lastpassing = 0
        self._lastrequest = None
        self._request_pending = False
        self._allowstored = False
        self._autochannelid = None
        self._refcount = 0

    # API overrides
    def status(self):
        """Request status info from decoder."""
        for c in sorted(_CONFINFO):
            self.write(''.join(['CONFGET;', c]))
        for c in sorted(_INFOLBLS):
            self.write(''.join(['INFOGET;', c]))
        self.write('BEACONGET')
        self.write('PASSINGINFOGET')
        self.write('TIMESTAMPGET')

    def connected(self):
        """Return true if decoder is connected"""
        return self._boxname is not None and self._io is not None

    # Device-specific functions
    def _close(self):
        self._boxname = None
        if self._io is not None:
            _log.debug('Close connection')
            cp = self._io
            self._io = None
            cp.close()

    def _port(self, port):
        """Re-establish connection to supplied device port."""
        self._request_pending = False
        self._rrustamp = None
        self._rruht = None
        self._close()
        self._rdbuf = b''
        _log.debug('Connecting to %r', port)
        s = serial.Serial(baudrate=_RRU_BAUD,
                          rtscts=False,
                          timeout=_RRU_IOTIMEOUT)
        s.dtr = 0  # This must be set _before_ open()
        s.port = port
        s.open()
        self._io = s
        self._sane()

    def _sane(self, data=None):
        """Load system config and then check decoder is properly configured"""
        setconfs = {}
        if sysconf.has_option('rru', 'allowstored'):
            self._allowstored = strops.confopt_bool(
                sysconf.get('rru', 'allowstored'))
            _log.info('Allow stored passings: %r', self._allowstored)
        if sysconf.has_option('rru', 'decoderconfig'):
            setconfs = sysconf.get('rru', 'decoderconfig')
            _log.debug('Loaded %r config options from sysconf', len(setconfs))
        self._config = {}
        for opt in _CONFINFO:
            ko = _CONFINFO[opt]
            kn = ko['label']
            if kn in setconfs and setconfs[kn] is not None:
                self._config[opt] = setconfs[kn]
                sv = setconfs[kn]
                if sv in ko:
                    sv = ko[sv]
                _log.debug('Set %s: %s', kn, sv)
            elif ko['default'] is not None:
                self._config[opt] = ko['default']

        # if channel id set already by site survey, keep it
        if self._autochannelid is not None:
            self._config['06'] = self._autochannelid

        # Set protocol
        self.write('ASCII')
        # Fetch decoder ID
        self.write('INFOGET;01')
        # Set options, ordering ensures Box mode is set before impulse in
        for opt in [
                '05', '01', '02', '04', '07', '08', '09', '0a', '0b', '0c',
                '0d', 'a0', 'a1', 'a2', 'a3', 'a4', 'b1', 'b2', '03'
        ]:
            if opt in self._config and self._config[opt] is not None:
                self.write(';'.join(['CONFSET', opt, self._config[opt]]))
        # Check if site survey is required
        if '06' in self._config and self._config['06'] is not None:
            if self._config['06'].lower() == 'auto':
                _log.info('Performing site survey to set Channel ID')
                self.write('SITESURVEY')
            else:
                self.write(';'.join(['CONFSET', '06', self._config['06']]))
        # Request current epoch ref setting
        self.write('EPOCHREFGET')
        # Request current number of ticks
        self.write('TIMESTAMPGET')
        # Request loop ID
        self.write('CONFGET;07')
        # Request current memory status
        self.write('PASSINGINFOGET')

    def _sync(self, data=None):
        _log.debug('Performing blocking DTR sync')
        # for the purpose of sync, the "epoch" is considered to be
        # midnight localtime of the current day
        self._rrustamp = None
        self._rruht = None
        # Determine the 'reference' epoch
        nt = tod.now()
        ntt = nt.truncate(0)
        ntd = (nt - ntt).timeval
        if ntd < 0.1 or ntd > 0.9:
            _log.debug('Sleeping 0.3s')
            sleep(0.3)
            nt = tod.now()
        ntt = nt.truncate(0)
        ett = ntt + tod.ONE
        _log.debug('Host reference time: %s', ett.rawtime())
        es = 'EPOCHREFSET;{0:08x}'.format(int(ett.timeval))
        self._write(es)
        _log.debug('Waiting for top of second')
        acceptval = tod.tod('0.001')
        diff = ett - nt
        while diff > acceptval and diff < tod.ONE:
            sleep(0.0005)
            nt = tod.now()
            diff = ett - nt
        _log.debug('Set DTR')
        self._io.dtr = 1
        sleep(0.2)
        _log.debug('Clear DTR')
        self._io.dtr = 0

    def _start_session(self, data=None):
        """Reset decoder to start a new session"""
        # On USB decoder, session is always active, this
        # method performs a hard reset/clear/sync
        self._clear(data)
        _log.info('Start session')

    def _stop_session(self, data=None):
        """Stop the current timing session"""
        # USB decoder will continue collecting passings, but
        # they are not received by handler - the passings can
        # be fetched by restarting connection without reset
        self._rrustamp = None
        _log.info('Stop session')

    def _clear(self, data=None):
        _log.debug('Performing box reset')
        self._boxname = None
        self._write('RESET')
        while True:
            m = self._readline()
            #_log.debug('RECV: %r', m)
            if m == 'AUTOBOOT':
                break
        self._rrustamp = None
        self._lastrequest = 0
        self._lastpassing = 0
        # Queue 'sane' config options before sync request
        self._sane()
        self.sync()

    def _write(self, msg):
        if self._io is not None:
            ob = (msg + _RRU_EOL)
            self._io.write(ob.encode(_RRU_ENCODING))
            #_log.debug('SEND: %r', ob)

    def _tstotod(self, ts):
        """Convert a race result timestamp to time of day."""
        ret = None
        try:
            ti = int(ts, 16) - self._rrustamp
            tsec = decimal.Decimal(ti // 256) + decimal.Decimal(ti % 256) / 256
            nsec = (self._rruht.timeval + tsec) % 86400
            if nsec < 0:
                _log.debug('Negative timestamp: %r', nsec)
                nsec = 86400 + nsec
            ret = tod.tod(nsec)
        except Exception as e:
            _log.error('%s converting timeval %r: %s', e.__class__.__name__,
                       ts, e)
        return ret

    def _confmsg(self, cid, val):
        """Handle config response."""
        lbl = cid
        vbl = val
        if cid in _CONFINFO:
            option = _CONFINFO[cid]
            if 'label' in option:
                lbl = option['label']
            if cid == '08':
                vbl = '{0:d}%'.format(int(val, 16))
            elif cid == '07':
                vbl = '{0:d}'.format(int(val, 16) + 1)
            else:
                if val in option:
                    vbl = option[val]
        if cid in self._config:
            # check decoder has the desired value
            if val != self._config[cid] and self._config[cid] != 'auto':
                if self._curreply == 'CONFSET':
                    _log.error('Error setting config %s, desired:%r actual:%r',
                               lbl, self._config[cid], val)
                else:
                    _log.info('Updating config %s: %s => %s', lbl, val,
                              self._config[cid])
                    self.write(';'.join(['CONFSET', cid, self._config[cid]]))
            else:
                _log.info('Config %s: %s', lbl, vbl)
        else:
            if cid in ['07', '08']:
                _log.info('Config %s: %s', lbl, vbl)
            else:
                _log.debug('Config %s: %s', lbl, vbl)

    def _infomsg(self, pid, val):
        """Show and save decoder info message."""
        lbl = pid
        vbl = val
        if pid in _INFOLBLS:
            lbl = _INFOLBLS[pid]
            if pid == '01':  # ID
                vbl = 'A-{0:d}'.format(int(val, 16))
                self._boxname = vbl
            elif pid == '02':  # Firmware
                vbl = 'v{0:0.1f}'.format(int(val, 16) / 10)
            elif pid == '03':  # Hardware
                vbl = 'v{0:0.1f}'.format(int(val, 16) / 10)
            elif pid == '04':  # Box Type
                if val in _BOX_TYPES:
                    vbl = _BOX_TYPES[val]
            elif pid == '05':  # Batt Voltage
                vbl = '{0:0.1f}V'.format(int(val, 16) / 10)
            elif pid == '07':  # Battery State
                if val in _BATTERY_STATES:
                    vbl = _BATTERY_STATES[val]
            elif pid == '08':  # Battery Level
                vbl = '{0:d}%'.format(int(val, 16))
            elif pid == '09':  # Int Temp
                vbl = '{0:d}\xb0C'.format(int(val, 16))
            elif pid == '0a':  # Supply Voltage
                vbl = '{0:0.1f}V'.format(int(val, 16) / 10)
            elif pid == '0b':  # Loop Status
                if val in _LOOP_STATES:
                    vbl = _LOOP_STATES[val]
            _log.info('Info %s: %s', lbl, vbl)
        else:
            _log.info('Info [undocumented] %s: %s', lbl, vbl)

    def _refgetmsg(self, epoch, stime):
        """Collect the epoch ref and system tick message."""
        self._rruht = tod.mkagg(int(epoch, 16))
        self._rrustamp = int(stime, 16)
        _log.debug('Reference ticks: %r @ %r', self._rrustamp,
                   self._rruht.rawtime())

    def _timestampchk(self, ticks):
        """Receive the number of ticks on the decoder."""
        tcnt = int(ticks, 16)
        _log.info('Box tick count: %r', tcnt)
        if tcnt > _RRU_REFTHRESH:
            _log.info('Tick threshold exceeded, adjusting ref')
            self.write('EPOCHREFADJ1D')

    def _passinginfomsg(self, mv):
        """Receive info about internal passing memory."""
        if len(mv) == 5:
            pcount = int(mv[0], 16)
            if pcount > 0:
                pfirst = int(mv[1], 16)
                pftime = self._tstotod(mv[2])
                plast = int(mv[3], 16)
                pltime = self._tstotod(mv[4])
                _log.info('Info %r Passings, %r@%s - %r@%s', pcount, pfirst,
                          pftime.rawtime(2), plast, pltime.rawtime(2))
                if plast + 1 < self._lastpassing:
                    _log.warning(
                        'Decoder memory/ID mismatch last=%r, req=%r, clear/sync required.',
                        plast, self._lastpassing)
                    self._lastpassing = plast + 1
            else:
                _log.info('Info No Passings')
        else:
            _log.debug('Non-passinginfo message: %r', mv)

    def _passingmsg(self, mv):
        """Receive a passing from the decoder."""
        if len(mv) == _RRU_PASSLEN:
            # USB decoder doesn't return passing ID, use internal count
            istr = str(self._lastpassing)
            tagid = mv[0]  # [TranspCode:string]
            wuc = mv[1]  # [WakeupCounter:4]
            timestr = mv[2]  # [Time:8]
            hits = mv[3]  # [Hits:2]
            rssi = mv[4]  # [RSSI:2]
            battery = mv[5]  # [Battery:2]
            loopid = mv[8]  # [LoopId:1]
            adata = mv[10]  # [InternalActiveData:2]

            # Check values
            if not loopid:
                loopid = 'C1'  # add faked id for passives
            else:
                loopid = strops.id2chan(int(loopid, 16) + 1)
            activestore = False
            if adata:
                aval = int(adata, 16)
                activestore = (int(adata, 16) & 0x40) == 0x40
            if tagid == _RRU_MARKER:
                tagid = ''

            if battery and tagid:
                try:
                    bv = int(battery, 16) / 10
                    if bv < _RRU_LOWBATT:
                        _log.warning('Low battery %s: %0.1fV', tagid, bv)
                except Exception as e:
                    _log.debug('%s reading battery voltage: %s',
                               e.__class__.__name__, e)

            if hits and rssi and tagid:
                try:
                    hitcount = int(hits, 16)
                    rssival = int(rssi, 16)
                    twofour = -90 + ((rssival & 0x70) >> 2)
                    lstrength = 1 + (rssival & 0x0f)
                    if lstrength < 5 or twofour < -82 or hitcount < 4:
                        _log.warning(
                            'Poor read %s: Hits:%d RSSI:%ddBm Loop:%ddB',
                            tagid, hitcount, twofour, lstrength)
                except Exception as e:
                    _log.debug('%s reading hits/RSSI: %s',
                               e.__class__.__name__, e)

            # emit a decoder log line TBD
            _log.log(DECODER_LOG_LEVEL, ';'.join(mv))

            # accept valid passings and trigger callback
            t = self._tstotod(timestr)
            if t is not None:
                t.index = istr
                t.chan = loopid
                t.refid = tagid
                t.source = self._boxname
                if not activestore or self._allowstored:
                    self._trig(t)
                else:
                    pass
            self._lastpassing += 1
        elif len(mv) == 2:
            resp = int(mv[0], 16)
            rcount = int(mv[1], 16)
            if resp != self._lastrequest:
                _log.error('Sequence mismatch request: %r, response: %r',
                           self._lastrequest, resp)
                self._lastpassing = 0
            elif rcount > 0:
                _log.debug('Receiving %r passings', rcount)
        else:
            _log.debug('Non-passing message: %r', mv)

    def _beaconmsg(self, mv):
        """Receive a beacon from the decoder."""
        if len(mv) == _RRU_BEACONLEN:
            # noise/transponder averages
            chid = int(mv[5], 16) + 1
            chnoise = 10.0 * int(mv[12], 16)
            tlqi = int(mv[13], 16) / 2.56
            trssi = -90 + int(mv[14], 16)
            _log.info('Info Ch {0} Noise: {1:0.0f}%'.format(chid, chnoise))
            _log.info('Info Avg LQI: {0:0.0f}%'.format(tlqi))
            _log.info('Info Avg RSSI: {}dBm'.format(trssi))
        elif len(mv) == 1:
            bcount = int(mv[0], 16)
            _log.debug('Receiving %r beacons', bcount)
        else:
            _log.debug('Non-beacon message: %r', mv)

    def _idupdate(self, reqid, minid):
        """Handle an empty PASSINGGET response."""
        resp = int(reqid, 16)
        newid = int(minid, 16)
        if resp != self._lastrequest:
            _log.error(
                'ID mismatch: request=%r, response=%r:%r, reset to first passing',
                self._lastrequest, resp, newid)
            self._lastpassing = newid
        else:
            if resp < newid:
                _log.warning('Data loss: %r passings not received',
                             newid - resp)
                self._lastpassing = newid
            # otherwise no missed passings, ignore error

    def _surveymsg(self, chan, noise):
        """Receive a site survey update."""
        channo = int(chan, 16) + 1
        if channo in self._sitenoise:
            self._sitenoise[channo] = 10 * int(noise, 16)
        else:
            _log.debug('Unknown channel in site survey: %r', channo)

    def _chansurf(self):
        """Examine survey for a better channel and hop if needed."""
        ch = None
        cv = 55  # don't accept any channel with noise over 50%
        lv = []
        for c in sorted(self._sitenoise, key=strops.rand_key):
            nv = self._sitenoise[c]
            lv.append('{}:{:d}%'.format(c, nv))
            if nv < cv:
                ch = c
                cv = nv
        _log.debug('Site survey: %s', ' '.join(lv))
        if ch is not None:
            _log.info('Selected channel %r (%d%%)', ch, cv)
            sv = '{0:02x}'.format(ch - 1)
            self._autochannelid = sv
            m = 'CONFSET;06;{}'.format(sv)
            self.write(m)
        else:
            _log.warning('Unable to find a suitable channel')

    def _handlereply(self, mv):
        """Process the body of a decoder response."""
        if self._curreply == 'PASSINGGET':
            self._passingmsg(mv)
        elif self._curreply == 'PASSINGINFOGET':
            self._passinginfomsg(mv)
        elif self._curreply == 'PASSINGIDERROR':
            if len(mv) == 2:
                self._idupdate(mv[0], mv[1])
        elif self._curreply == 'INFOGET':
            if len(mv) == 2:
                self._infomsg(mv[0], mv[1])
        elif self._curreply in ['EPOCHREFGET', 'EPOCHREFSET', 'EPOCHREFADJ1D']:
            if len(mv) == 2:
                self._refgetmsg(mv[0], mv[1])
        elif self._curreply in ['CONFGET', 'CONFSET']:
            if len(mv) == 2:
                self._confmsg(mv[0], mv[1])
        elif self._curreply == 'TIMESTAMPGET':
            if len(mv) == 1:
                self._timestampchk(mv[0])
        elif self._curreply == 'SITESURVEY':
            if len(mv) == 2:
                self._surveymsg(mv[0], mv[1])
        elif self._curreply == 'BEACONGET':
            self._beaconmsg(mv)
        else:
            _log.debug('%r : %r', self._curreply, mv)

    def _procline(self, l):
        """Handle the next line of response from decoder."""
        mv = l.split(';')
        if len(mv) > 0:
            if mv[0] == '#P':
                # pushed passing overrides cmd/reply logic
                self._passingmsg(mv[1:])
            elif mv[0] == 'PREWARN':
                self._curreply = mv[0]
            elif mv[0] == 'EOR':
                if self._curreply in ['PASSINGGET', 'PASSINGIDERROR']:
                    self._request_pending = False
                if self._curreply == 'SITESURVEY':
                    self._chansurf()
                self._curreply = None
            elif mv[0] in _REPLIES:
                if self._curreply is not None:
                    _log.debug('Protocol error: %r not terminated',
                               self._curreply)
                self._curreply = mv[0]
                if mv[1] != '00':
                    if self._curreply == 'PASSINGGET' and mv[1] == '10':
                        self._curreply = 'PASSINGIDERROR'
                    else:
                        _log.debug('%r error: %r', self._curreply, mv[1])
            else:
                if self._curreply is not None:
                    self._handlereply(mv)

    def _readline(self):
        """Read from the decoder until end of line or timeout condition."""
        ret = None
        ch = self._io.read(1)
        while ch != b'':
            if ch == b'\n':
                if len(self._rdbuf) > 0:
                    # linefeed ends the current 'message'
                    ret = self._rdbuf.lstrip(b'\0').decode(_RRU_ENCODING)
                    self._rdbuf = b''
                else:
                    ret = 'EOR'  # Flag end of response
                break
            else:
                self._rdbuf += ch
            ch = self._io.read(1)
        return ret

    def _request_next(self):
        """Queue a passingget request if the reftime is set."""
        if self._rrustamp is not None:
            if not self._request_pending:
                self._request_pending = True
                es = 'PASSINGGET;{0:08x}'.format(self._lastpassing)
                self._lastrequest = self._lastpassing
                self.write(es)
                self._refcount += 1
                if self._refcount > _RRU_REFCHECK:
                    self.write('TIMESTAMPGET')
                    self._refcount = 0

    def run(self):
        """Decoder main loop."""
        _log.debug('Starting')
        self._running = True
        while self._running:
            try:
                m = None  # next commmand
                if self._io is not None:
                    # Fetch all responses from unit
                    refetch = False
                    while True:
                        l = self._readline()
                        if l is None:
                            # wait for sitesurvey
                            if self._curreply != 'SITESURVEY':
                                # on time out, request passings
                                refetch = True
                                break
                        else:
                            #_log.debug('RECV: %r', l)
                            self._procline(l)
                            if self._curreply == 'PREWARN':
                                # Note: this does not work
                                refetch = True
                            if l == 'EOR':
                                break
                    if refetch:
                        self._request_next()
                    m = self._cqueue.get_nowait()
                else:
                    m = self._cqueue.get()
                self._cqueue.task_done()
                self._proccmd(m)
            except queue.Empty:
                pass
            except serial.SerialException as e:
                self._close()
                _log.error('%s: %s', e.__class__.__name__, e)
            except Exception as e:
                _log.critical('%s: %s', e.__class__.__name__, e)
                self._running = False
                self._boxname = None
        self.setcb()
        _log.debug('Exiting')
