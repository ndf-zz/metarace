# SPDX-License-Identifier: MIT
"""Race Result System decoder interface."""

import queue
import logging
import socket
import datetime

from . import (decoder, DECODER_LOG_LEVEL)
from metarace import sysconf
from metarace import tod

_log = logging.getLogger('decoder.rrs')
_log.setLevel(logging.DEBUG)

# desired target protocol level
_RRS_PROTOCOL = '3.2'
# decoder port
_RRS_TCP_PORT = 3601
# passing record length
_RRS_PASSLEN = 20
# status record length
_RRS_STATUSLEN = 25
# Warn if battery voltage is below this many volts
_RRS_LOWBATT = 2.3
_RRS_SYNFMT = 'SETTIME;{:04d}-{:02d}-{:02d};{:02d}:{:02d}:{:02d}.{:03d}'
_RRS_EOL = '\r\n'
_RRS_MARKER = '99999'
_RRS_ENCODING = 'iso8859-1'
_RRS_IOTIMEOUT = 1.0
_RRS_PASSIVEID = '1'

# Error flags from decoder status
_RRS_ERRORFLAGS = {
    1: 'UHF module reports an error',
    16: 'Active loop error',
    32: 'Active loop limit',
    64: 'Active connection lost',
    256: 'GPS time sync error',
    512: 'GPS communication error warning',
    1024: 'Active time sync error'
}

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Race Result System/Active Extension',
        'control': 'section'
    },
    'allowstored': {
        'type': 'bool',
        'attr': 'allowstored',
        'subtext': 'Report stored passings?',
        'prompt': 'Allow Stored:',
        'hint': 'Stored passings will be reported as normal passings',
        'control': 'check',
        'default': True,
    },
    'passiveloop': {
        'type': 'chan',
        'attr': 'passiveloop',
        'prompt': 'Passive Loop:',
        'hint': 'Assign loop ID to passive passings',
        'control': 'choice',
        'options': {
            '1': '1 (Base)',
            '2': '2',
            '3': '3',
            '4': '4',
            '5': '5',
            '6': '6',
            '7': '7',
            '8': '8'
        },
        'default': 1
    }
}


class rrs(decoder):
    """RRS thread object class."""

    def __init__(self):
        decoder.__init__(self)
        self._io = None
        self._rdbuf = b''
        self._curfile = None
        self._lastpassing = None
        self._dorefetch = True
        self._fetchpending = False
        self._pending_command = None
        self._allowstored = True
        self._passiveloop = 1
        self._curport = None

    # API overrides
    def sync(self, data=None):
        self.stop_session(data)
        self._cqueue.put_nowait(('_sync', data))
        self.start_session(data)

    def start_session(self, data=None):
        self.write('STARTOPERATION')
        self.write('PASSINGS')

    def stop_session(self, data=None):
        self.write('STOPOPERATION')

    def status(self, data=None):
        self.write('GETSTATUS')

    def connected(self):
        return self._io is not None

    def clear(self, data=None):
        self.stop_session(data)
        self.write('CLEARFILES')
        self._cqueue.put_nowait(('_sync', data))
        self.start_session(data)

    # Device-specific functions
    def _close(self):
        if self._io is not None:
            _log.debug('Close connection')
            cp = self._io
            self._io = None
            try:
                cp.shutdown(socket.SHUT_RDWR)
            except Exception as e:
                _log.debug('%s: shutdown socket: %s', e.__class__.__name__, e)
            cp.close()

    def _sane(self, data=None):
        for m in [
                'GETPROTOCOL',
                'SETPROTOCOL;{}'.format(_RRS_PROTOCOL),
                'SETPUSHPREWARNS;0',
                'SETPUSHPASSINGS;1;0',
                'GETCONFIG;GENERAL;BOXNAME',
                'GETCONFIG;ACTIVE;LOOPID',
                'GETCONFIG;ACTIVE;POWER',
                'GETCONFIG;UPLOAD;CONNECTION',
                'GETINTERFACES',
                'GETSTATUS',
                'PASSINGS',
        ]:
            self.write(m)

    def _port(self, port):
        """Re-establish connection to supplied device port."""
        self._close()
        if port is None and self._curport is not None:
            port = self._curport
        if port is None:
            _log.debug('Re-connect cancelled: port is None')
            return
        addr = (port, _RRS_TCP_PORT)
        _log.debug('Connecting to %r', addr)
        self._rdbuf = b''
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_USER_TIMEOUT, 5000)
        except Exception as e:
            _log.debug('%s setting TCP_NODELAY/TCP_USER_TIMEOUT: %s',
                       e.__class__.__name__, e)
        s.connect(addr)
        s.settimeout(_RRS_IOTIMEOUT)
        self._io = s
        self.sane()
        self._curport = port

    def _sync(self, data=None):
        a = datetime.datetime.now()
        syncmd = _RRS_SYNFMT.format(a.year, a.month, a.day, a.hour, a.minute,
                                    a.second, a.microsecond // 1000)
        self._write(syncmd)

    def _replay(self, file):
        """RRS-specific replay"""
        if file.isdigit():
            _log.debug('Replay passings from %r', file)
            cmd = 'GETFILE;{:d}'.format(file)
            self._write(cmd)
        else:
            _log.error('Invalid file specified: %r', file)

    def _write(self, msg):
        if self._io is not None:
            ob = (msg + _RRS_EOL)
            self._io.sendall(ob.encode(_RRS_ENCODING))
            #_log.debug('SEND: %r', ob)

    def _passing(self, pv):
        """Process a RRS protocol passing."""
        if len(pv) == _RRS_PASSLEN:
            today = datetime.date.today().isoformat()
            istr = pv[0]  # <PassingNo>
            tagid = pv[1]  # <Bib/TranspCode>
            date = pv[2]  # <Date>
            timestr = pv[3]  # <Time>
            eventid = pv[4]  # <EventID>
            isactive = pv[8]  # <IsActive>
            loopid = pv[10]  # <LoopID>
            wuc = pv[12]  # <WakeupCounter>
            battery = pv[13]  # <Battery>
            adata = pv[15]  # <InternalActiveData>
            bname = pv[16]  # <BoxName>
            hits = pv[5]  # <Hits>
            rssi = pv[6]  # <MaxRSSI>

            # An error here will invalidate the whole passing
            pid = int(istr)
            if self._lastpassing is not None:
                expectpid = self._lastpassing + 1
                if pid != expectpid:
                    _log.debug('Ignore out of sequence passing: %r != %r', pid,
                               expectpid)
                    return
            self._lastpassing = pid

            active = False
            try:
                active = bool(int(isactive))
                if eventid == '0':
                    eventid = ''
            except Exception as e:
                _log.debug('%s reading isactive: %s', e.__class__.__name__, e)

            if not loopid:
                loopid = self._passiveloop
            if loopid is not None:
                try:
                    loopid = 'C' + str(int(loopid))
                except Exception as e:
                    _log.debug('%s reading loop id: %s', e.__class__.__name__,
                               e)
            else:
                # Assume passive without loop set
                loopid = 'PSV'
            activestore = False
            if active and adata:
                activestore = (int(adata) & 0x40) == 0x40
            if not active and tagid and eventid:
                tagid = '-'.join((eventid, tagid))
            if tagid == _RRS_MARKER:
                tagid = ''

            if battery and tagid:
                try:
                    bv = float(battery)
                    if bv < _RRS_LOWBATT:
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
                    if lstrength < 3 or twofour < -82 or hitcount < 3:
                        _log.warning(
                            'Poor read %s: Hits:%d RSSI:%ddBm Loop:%ddB',
                            tagid, hitcount, twofour, lstrength)
                except Exception as e:
                    _log.debug('%s reading hits/RSSI: %s',
                               e.__class__.__name__, e)

            # emit a decoder log line TBD
            _log.log(DECODER_LOG_LEVEL, ';'.join(pv))

            # accept valid passings and trigger callback
            t = tod.mktod(timestr)
            if t is not None:
                t.index = istr
                t.chan = loopid
                t.refid = tagid
                t.source = bname
                if not activestore or self._allowstored:
                    self._trig(t)
                else:
                    pass
        else:
            _log.info('Non-passing message: %r', pv)

    def _statusmsg(self, pv):
        """Process a RRS protocol status message."""
        if len(pv) == _RRS_STATUSLEN:
            pwr = pv[2]  # <HasPower>
            opmode = pv[4]  # <IsInOperationMode>
            uhf = pv[8]  # <ReaderIsHealthy>
            batt = pv[9]  # <BatteryCharge>
            active = pv[13]  # <ActiveExtConnected>
            eflag = pv[23]  # <ErrorFlags>
            if batt == '-1':
                batt = '[estimating]'
            else:
                batt += '%'
            loopch = 'n/a'
            loopid = self._passiveloop
            looppower = 'n/a'
            if active == '1':
                loopch = pv[14]
                loopid = pv[15]
                looppower = pv[16]
            else:
                loopch = pv[3]

            if opmode == '1':
                _log.info(
                    'Started, charge:%s, uhf:%s, batt:%s, ch:%s, loop:%s, power:%s',
                    pwr, uhf, batt, loopch, loopid, looppower)
            else:
                _log.warning(
                    'Not started, charge:%s, uhf:%s, batt:%s, ch:%s, loop:%s, power:%s',
                    pwr, uhf, batt, loopch, loopid, looppower)

            if eflag != '0':
                stat = int(eflag)
                evec = []
                for bit in _RRS_ERRORFLAGS:
                    if stat & bit == bit:
                        evec.append(_RRS_ERRORFLAGS[bit])
                _log.error('Error: %s', ', '.join(evec))

    def _configmsg(self, pv):
        """Process a RRS protocol config message."""
        if len(pv) > 3:
            if pv[1] == 'BOXNAME':
                boxid = pv[3]  # <DeviceId>
                _log.info('%r connected', boxid)
            elif pv[1] == 'LOOPID':
                _log.info('Config Loop ID: %s', pv[3])
            elif pv[1] == 'POWER':
                _log.info('Config Loop Power: %s', pv[3])

    def _protocolmsg(self, pv):
        """Respond to protocol message from decoder."""
        if len(pv) == 3:
            if _RRS_PROTOCOL > pv[2]:
                _log.error('Protocol %r unsupported (max %r), update firmware',
                           _RRS_PROTOCOL, pv[2])

    def _passingsmsg(self, pv):
        """Handle update of current passing count."""
        try:
            newfile = None
            if len(pv) > 1:
                newfile = int(pv[1])
            newidx = int(pv[0])
            if newfile != self._curfile:
                _log.debug('New passing file %r', newfile)
                self._curfile = newfile
                self._lastpassing = newidx
            else:
                if self._lastpassing is None or newidx < self._lastpassing:
                    # assume new connection or new file
                    _log.debug('Last passing %r updated to %r',
                               self._lastpassing, newidx)
                    self._lastpassing = newidx
                else:
                    # assume a broken connection and fetch missed passings
                    _log.debug('Missed %r passings, last passing = %r',
                               newidx - self._lastpassing, self._lastpassing)
            self._fetchpending = False
        except Exception as e:
            _log.debug('%s reading passing count: %s', e.__class__.__name__, e)

    def _procmsg(self, msg):
        """Process a decoder response message."""
        #_log.debug('RECV: %r', msg)
        mv = msg.strip().split(';')
        if mv[0].isdigit():  # Requested passing
            self._pending_command = 'PASSING'
            self._passing(mv)
        elif mv[0] == '#P':  # Pushed passing
            self._passing(mv[1:])
        elif mv[0] == 'GETSTATUS':
            self._statusmsg(mv[1:])
        elif mv[0] == 'GETCONFIG':
            self._configmsg(mv[1:])
        elif mv[0] == 'GETPROTOCOL':
            self._protocolmsg(mv[1:])
        elif mv[0] == 'PASSINGS':
            self._passingsmsg(mv[1:])
        elif mv[0] == 'SETTIME':
            _log.info('Time set to: %r %r', mv[1], mv[2])
        elif mv[0] == 'STARTOPERATION':
            self._curfile = None
            self._lastpassing = None
            _log.info('Start session')
        elif mv[0] == 'STOPOPERATION':
            self._curfile = None
            self._lastpassing = None
            _log.info('Stop session')
        elif mv[0].startswith('ONLY '):
            self._fetchpending = False
        elif mv[0] == '':
            _log.debug('End of requested passings')
            self._fetchpending = False
            self._pending_command = None
            self._dorefetch = True
        else:
            pass  # Ignore other responses

    def _procline(self):
        """Read and process whole line from decoder, return command status."""
        idx = self._rdbuf.find(b'\n')
        if idx < 0:
            inb = self._io.recv(512)
            if inb == b'':
                _log.info('Connection closed by peer')
                self._close()
            else:
                self._rdbuf += inb
            idx = self._rdbuf.find(b'\n')
        if idx >= 0:
            l = self._rdbuf[0:idx + 1].decode(_RRS_ENCODING)
            self._rdbuf = self._rdbuf[idx + 1:]
            self._procmsg(l)
        return self._pending_command is None

    def _refetch(self):
        """Poll decoder for new passings."""
        if not self._fetchpending:
            if self._dorefetch and self._lastpassing is not None:
                self._fetchpending = True
                self._dorefetch = False
                cmd = '{:d}:32'.format(self._lastpassing + 1)
                self.write(cmd)

    def run(self):
        """Decoder main loop."""
        _log.debug('Starting')
        sysconf.add_section('rrs', _CONFIG_SCHEMA)
        self._allowstored = sysconf.get_value('rrs', 'allowstored')
        self._passiveloop = sysconf.get_value('rrs', 'passiveloop')
        _log.debug('Allow stored passings: %r', self._allowstored)
        _log.debug('Passive loop id set to: %r', self._passiveloop)
        self._running = True
        while self._running:
            try:
                c = None
                if self._io is not None:
                    # Read responses until response complete or timeout
                    try:
                        while not self._procline():
                            pass
                    except socket.timeout:
                        self._dorefetch = True
                    self._refetch()
                    c = self._cqueue.get_nowait()
                else:
                    c = self._cqueue.get()
                self._cqueue.task_done()
                self._proccmd(c)
            except queue.Empty:
                pass
            except socket.error as e:
                self._close()
                _log.error('%s: %s', e.__class__.__name__, e)
            except Exception as e:
                _log.critical('%s: %s', e.__class__.__name__, e)
                self._running = False
        self.setcb()
        _log.debug('Exiting')
