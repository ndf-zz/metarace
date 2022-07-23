# SPDX-License-Identifier: MIT
"""Tag Heuer/Chronelec Decoder Interface."""

# For connections to multiple decoders, use thbchub

import queue
import logging
import serial
import socket
import time

from . import (decoder, DECODER_LOG_LEVEL)
from metarace import sysconf
from metarace import tod
from libscrc import mcrf4xx

LOG = logging.getLogger('metarace.decoder.thbc')
LOG.setLevel(logging.DEBUG)

THBC_BAUD = 19200
THBC_UDP_PORT = 2008
THBC_ENCODING = 'iso8859-1'

# THbC protocol messages
ESCAPE = b'\x1b'
HELOCMD = b'MR1'
STOPCMD = ESCAPE + b'\x13\x5c'
REPEATCMD = ESCAPE + b'\x12'
ACKCMD = ESCAPE + b'\x11'

STATCMD = ESCAPE + b'\x05'  # fetch status
CHKCMD = ESCAPE + b'\x06'  # UNKNOWN
STARTCMD = ESCAPE + b'\x07'  # start decoder
SETCMD = ESCAPE + b'\x08'  # set configuration
IPCMD = ESCAPE + b'\x09'  # set IP configuration
QUECMD = ESCAPE + b'\x10'  # fetch configuration

STALVL = ESCAPE + b'\x1e'
BOXLVL = ESCAPE + b'\x1f'

NACK = b'\x07'
CR = b'\x0d'
LF = b'\x0a'
SETTIME = ESCAPE + b'\x48'
STATSTART = b'['
PASSSTART = b'<'

# decoder config consts
IPCONFIG_LEN = 16
CONFIG_LEN = 27
CONFIG_TOD = 0
CONFIG_GPS = 1
CONFIG_TZ_HOUR = 2
CONFIG_TZ_MIN = 3
CONFIG_485 = 4
CONFIG_FIBRE = 5
CONFIG_PRINT = 6
CONFIG_MAX = 7
CONFIG_PROT = 8
CONFIG_PULSE = 9
CONFIG_PULSEINT = 10
CONFIG_CELLSYNC = 11
CONFIG_CELLTOD_HOUR = 12
CONFIG_CELLTOD_MIN = 13
CONFIG_TONE_STA = 15
CONFIG_TONE_BOX = 17
CONFIG_TONE_MAN = 19
CONFIG_TONE_CEL = 21
CONFIG_TONE_BXX = 23
CONFIG_ACTIVE_LOOP = 14
CONFIG_SPARE = 25
CONFIG_FLAGS = {
    CONFIG_TOD: 'Time of Day',
    CONFIG_GPS: 'GPS Sync',
    CONFIG_TZ_HOUR: 'Timezone Hour',
    CONFIG_TZ_MIN: 'Timezone Min',
    CONFIG_485: 'Distant rs485',
    CONFIG_FIBRE: 'Distant Fibre',
    CONFIG_PRINT: 'Serial Print',
    CONFIG_MAX: 'Detect Max',
    CONFIG_PROT: 'Protocol',
    CONFIG_PULSE: 'Sync Pulse',
    CONFIG_PULSEINT: 'Sync Interval',
    CONFIG_CELLSYNC: 'CELL Sync',
    CONFIG_CELLTOD_HOUR: 'CELL Sync Hour',
    CONFIG_CELLTOD_MIN: 'CELL Sync Min',
    CONFIG_TONE_STA: 'STA Tone',
    CONFIG_TONE_BOX: 'BOX Tone',
    CONFIG_TONE_MAN: 'MAN Tone',
    CONFIG_TONE_CEL: 'CEL Tone',
    CONFIG_TONE_BXX: 'BXX Tone',
    CONFIG_ACTIVE_LOOP: 'Active Loop',
    CONFIG_SPARE: '[spare]'
}
DEFAULT_IPCFG = {
    'IP': '192.168.0.10',
    'Netmask': '255.255.255.0',
    'Gateway': '0.0.0.0',
    'Host': '192.168.0.255'
}
DEFPORT = '/dev/ttyS0'


def thbc_sum(msgstr=b''):
    """Return sum of character values as decimal string."""
    ret = 0
    for ch in msgstr:
        ret = ret + ch
    return '{0:04d}'.format(ret).encode('ascii', 'ignore')


def val2hexval(val):
    """Convert int to decimal digit equivalent hex byte."""
    ret = 0x00
    ret |= ((val // 10) & 0x0f) << 4  # msd	97 -> 0x90
    ret |= (val % 10) & 0x0f  # lsd   97 -> 0x07
    return ret


def hexval2val(hexval):
    """Unconvert a decimal digit equivalent hex byte to int."""
    ret = 10 * (hexval >> 4)  # tens 0x97 -> 90
    ret += hexval & 0x0f  # ones 0x97 ->  7
    return ret


class thbc(decoder):
    """Tag Heuer / Chronelec thread object class."""

    def __init__(self):
        decoder.__init__(self)
        self._boxname = 'thbc'
        self._version = ''
        self._decoderconfig = {}
        self._decoderipconfig = {}
        self._io = None
        self._cksumerr = 0
        self._rdbuf = b''  # bytestring read buffer

    # API overrides
    def status(self):
        """Request status message from decoder."""
        self.write(STATCMD)

    def stop_session(self):
        """Send a stop command to decoder."""
        self.write(STOPCMD)

    def start_session(self):
        """Send a depart command to decoder."""
        self.write(STARTCMD)

    def clear(self):
        """Start a new session and request time sync."""
        self.stop_session()
        self.start_session()
        self.sync()

    def get_config(self):
        """Request decoder configuration."""
        self.write(QUECMD)

    def ipconfig(self):
        """Request sanity check in decoder thread."""
        self._cqueue.put_nowait(('_ipcfg', None))

    # Device-specific functions
    def _close(self):
        if self._io is not None:
            LOG.debug('Close connection')
            cp = self._io
            self._io = None
            try:
                cp.close()
            except Exception as e:
                LOG.debug('%s closing io: %s', e.__class__.__name__, e)

    def _port(self, port):
        """Re-establish connection to supplied device port."""
        self._close()
        s = None
        self._rdbuf = b''
        if '/' not in port and '.' in port:
            LOG.debug('Attempting UDP on %r', port)
            s = dgram(port, THBC_UDP_PORT)
        else:
            # assume device file
            s = serial.Serial(port, THBC_BAUD, rtscts=False, timeout=0.2)
        self._boxname = 'thbc'
        self._io = s
        self._write(QUECMD)

    def _sync(self, data=None):
        LOG.debug('Performing blocking sync')
        acceptval = tod.tod('0.001')
        nt = tod.now()
        diff = nt - nt.truncate(0)
        while diff > acceptval and diff < tod.ONE:
            time.sleep(0.0005)
            nt = tod.now()
            diff = nt - nt.truncate(0)
        self._write(self._set_time_cmd(nt))
        LOG.debug('Set time: %r', nt.meridiem())

    def _ipcfg(self, data=None):
        """Alter the attached decoder's IP address."""
        ipcfg = sysconf.get('thbc', 'ipconfig')
        cmd = b'\x09\x09'
        for i in ['IP', 'Netmask', 'Gateway', 'Host']:
            if i not in ipcfg:
                ipcfg[i] = DEFAULT_IPCFG[i]
            cmd += socket.inet_aton(socket.gethostbyname(ipcfg[i]))
        LOG.info('Attempting IP config update')
        self._v3_cmd(cmd)

    def _sane(self, data=None):
        """Check decoder config against system settings."""
        doconf = False
        if self._boxname != 'thbc':
            if sysconf.has_option('thbc', 'decoderconfig'):
                oconf = sysconf.get('thbc', 'decoderconfig')
                for flag in self._decoderconfig:
                    key = CONFIG_FLAGS[flag]
                    if key in oconf:
                        if oconf[key] != self._decoderconfig[flag]:
                            LOG.info('Key mismatch: %r', key)
                            self._decoderconfig[flag] = oconf[key]
                            doconf = True

        # re-write config if required
        if doconf:
            LOG.info('Re-configuring %r', self._boxname)
            self._set_config()

        # force decoder levels
        if sysconf.has_option('thbc', 'levels'):
            lvl = sysconf.get('thbc', 'levels')
            self._setlvl(box=lvl[0], sta=lvl[1])

    def _v3_cmd(self, cmdstr=b''):
        """Pack and send a v3 command directly to port."""
        crc = mcrf4xx(cmdstr)
        crcstr = bytes([(crc >> 8) & 0xff, crc & 0xff])
        self._write(ESCAPE + cmdstr + crcstr + b'>')

    def _serialise_config(self):
        """Convert current decoder setting into a config string"""
        obuf = bytearray(CONFIG_LEN)
        # fill in level bytes
        obuf[CONFIG_SPARE] = 0x13  # will be fixed by subsequent levelset
        obuf[CONFIG_SPARE + 1] = 0x15

        # fill in tone values
        for opt in [
                CONFIG_TONE_STA, CONFIG_TONE_BOX, CONFIG_TONE_MAN,
                CONFIG_TONE_CEL, CONFIG_TONE_BXX
        ]:
            if opt in self._decoderconfig:
                obuf[opt] = val2hexval(self._decoderconfig[opt] // 100)  # xx00
                obuf[opt + 1] = val2hexval(self._decoderconfig[opt] %
                                           100)  # 00xx

        # fill in single byte values
        for opt in [
                CONFIG_TZ_HOUR, CONFIG_TZ_MIN, CONFIG_PROT, CONFIG_PULSEINT,
                CONFIG_CELLTOD_HOUR, CONFIG_CELLTOD_MIN
        ]:
            if opt in self._decoderconfig:
                obuf[opt] = val2hexval(self._decoderconfig[opt] % 100)  # ??

        # fill in flags
        for opt in [
                CONFIG_TOD, CONFIG_GPS, CONFIG_485, CONFIG_FIBRE, CONFIG_PRINT,
                CONFIG_MAX, CONFIG_PULSE, CONFIG_CELLSYNC, CONFIG_ACTIVE_LOOP
        ]:
            if opt in self._decoderconfig:
                if self._decoderconfig[opt]:
                    obuf[opt] = 0x01
        return bytes(obuf)

    def _set_config(self):
        """Write current configuration to decoder."""
        cmd = b'\x08\x08' + self._serialise_config()
        self._v3_cmd(cmd)
        self._write(QUECMD)

    def _set_date(self, timestruct=None):
        """Set the date on the decoder."""
        if timestruct is None:
            timestruct = time.localtime()
        LOG.debug('Set date on decoder: %s',
                  time.strftime('%Y-%m-%d', timestruct))
        cmd = bytearray(5)
        cmd[0] = 0x0a
        cmd[1] = 0x0a
        cmd[2] = 0xff & timestruct[2]  # day
        cmd[3] = 0xff & timestruct[1]  # month
        cmd[4] = 0xff & (timestruct[0] - 2000)  # year, after 2000
        self._v3_cmd(bytes(cmd))

    def _setlvl(self, box='10', sta='10'):
        """Set the read level on box and sta channels."""
        # TODO: verify opts
        self.write(BOXLVL + box.encode(THBC_ENCODING))
        self.write(STALVL + sta.encode(THBC_ENCODING))

    def _set_time_cmd(self, t):
        """Return a set time command string for the provided time of day."""
        body = bytearray(4)
        s = int(t.timeval)
        body[0] = s // 3600  # hours
        body[1] = (s // 60) % 60  # minutes
        body[2] = s % 60  # seconds
        body[3] = 0x74
        return SETTIME + bytes(body)

    def _parse_config(self, msg):
        # decoder configuration message.
        ibuf = bytearray(msg)
        self._decoderconfig = {}
        for flag in sorted(CONFIG_FLAGS):  # import all
            # tone values
            if flag in [
                    CONFIG_TONE_STA, CONFIG_TONE_BOX, CONFIG_TONE_MAN,
                    CONFIG_TONE_CEL, CONFIG_TONE_BXX
            ]:
                self._decoderconfig[flag] = 100 * hexval2val(ibuf[flag])
                self._decoderconfig[flag] += hexval2val(ibuf[flag + 1])

            # single byte values
            elif flag in [
                    CONFIG_TZ_HOUR, CONFIG_TZ_MIN, CONFIG_PROT,
                    CONFIG_PULSEINT, CONFIG_CELLTOD_HOUR, CONFIG_CELLTOD_MIN
            ]:
                self._decoderconfig[flag] = hexval2val(ibuf[flag])

            # 'booleans'
            elif flag in [
                    CONFIG_TOD, CONFIG_GPS, CONFIG_485, CONFIG_FIBRE,
                    CONFIG_PRINT, CONFIG_MAX, CONFIG_PULSE, CONFIG_CELLSYNC,
                    CONFIG_ACTIVE_LOOP
            ]:
                self._decoderconfig[flag] = bool(ibuf[flag])

        self._boxname = ''
        for c in msg[43:47]:
            self._boxname += chr(c + ord('0'))
        self._version = str(hexval2val(ibuf[47]))
        stalvl = hexval2val(msg[25])
        boxlvl = hexval2val(msg[26])
        LOG.info('Info Decoder ID: %s', self._boxname)
        LOG.debug('Info Firmware Version: %r', self._version)
        LOG.debug('Levels: STA=%r, BOX=%r', stalvl, boxlvl)
        self._decoderipconfig['IP'] = socket.inet_ntoa(msg[27:31])
        self._decoderipconfig['Mask'] = socket.inet_ntoa(msg[31:35])
        self._decoderipconfig['Gateway'] = socket.inet_ntoa(msg[35:39])
        self._decoderipconfig['Host'] = socket.inet_ntoa(msg[39:43])
        for key in ['IP', 'Mask', 'Gateway', 'Host']:
            LOG.debug('%r: %r', key, self._decoderipconfig[key])

    def _parse_message(self, msg, ack=True):
        """Return tod object from timing msg or None."""
        ret = None
        if len(msg) > 4:
            if msg[0] == PASSSTART[0]:  # RFID message
                idx = msg.find(b'>')
                if idx == 37:  # Valid length
                    data = msg[1:33]
                    msum = msg[33:37]
                    tsum = thbc_sum(data)
                    if tsum == msum:  # Valid 'sum'
                        pvec = data.decode(THBC_ENCODING).split()
                        istr = pvec[3] + ':' + pvec[5]
                        rstr = pvec[1].lstrip('0')
                        cstr = 'C1'
                        if pvec[0] == 'BOX':
                            cstr = 'C2'
                        elif pvec[0] == 'MAN':
                            cstr = 'C0'
                        if pvec[5] == '3':  # LOW BATTERY ALERT
                            LOG.warning('Low battery on %r', rstr)
                        ret = tod.tod(pvec[2],
                                      index=istr,
                                      chan=cstr,
                                      refid=rstr,
                                      source=self._boxname)
                        # Log a hardware-specific passing
                        LOG.log(DECODER_LOG_LEVEL, msg.strip())
                        if ack:
                            self._write(ACKCMD)  # Acknowledge if ok
                        self._cksumerr = 0
                    else:
                        LOG.warning('Invalid checksum: %r != %r: %r', tsum,
                                    msum, msg)
                        self._cksumerr += 1
                        if self._cksumerr > 3:
                            # assume error on decoder, so acknowledge and
                            # continue with log
                            # NOTE: This path is triggered when serial comms
                            # fail and a tag read happens before a manual trig
                            LOG.error('Erroneous message from decoder')
                            if ack:
                                self._write(ACKCMD)
                else:
                    LOG.debug('Invalid message: %r', msg)
            elif msg[0] == STATSTART:  # Status message
                data = msg[1:22]
                pvec = data.decode(THBC_ENCODING).split()
                if len(pvec) == 5:
                    LOG.info('%r@%s Noise:%s/%s Levels:%s/%s', self._boxname,
                             pvec[0], pvec[1], pvec[2], pvec[3], pvec[4])
                else:
                    LOG.info('Invalid status: %r', msg)
            elif b'+++' == msg[0:3] and len(msg) > 53:
                self._parse_config(msg[3:])
            else:
                pass
        else:
            LOG.debug('Short message: %r', msg)
        return ret

    def _ipcompletion(self):
        """Blocking wait for ipconfig completion - horrible."""
        LOG.info('IP Config')
        time.sleep(10)
        self.write(QUECMD)

    def _read(self):
        """Read messages from the decoder until a timeout condition."""
        ch = self._io.read(1)
        while ch != b'':
            if ch == LF and len(self._rdbuf) > 0 and self._rdbuf[-1] == CR[0]:
                # Return ends the current 'message', if preceeded by return
                self._rdbuf += ch  # include trailing newline
                LOG.debug('RECV: %r', self._rdbuf)
                t = self._parse_message(self._rdbuf.lstrip(b'\0'))
                if t is not None:
                    self._trig(t)
                self._rdbuf = b''
            elif len(self._rdbuf) > 40 and b'\x1e\x86\x98' in self._rdbuf:
                # Assume acknowledge from IP Command
                LOG.debug('RECV: %r', self._rdbuf)
                self._rdbuf = b''
                self._ipcompletion()
            else:
                self._rdbuf += ch
            ch = self._io.read(1)

    def _write(self, msg):
        if self._io is not None:
            self._io.write(msg)
            LOG.debug('SEND: %r', msg)

    def run(self):
        """Decoder main loop."""
        LOG.debug('Starting')
        self._running = True
        while self._running:
            try:
                c = None
                if self._io is not None:
                    # Read responses until response complete or timeout
                    try:
                        self._read()
                    except socket.timeout:
                        pass
                    c = self._cqueue.get_nowait()
                else:
                    c = self._cqueue.get()
                self._cqueue.task_done()
                self._proccmd(c)
            except queue.Empty:
                pass
            except (serial.SerialException, socket.error) as e:
                self._close()
                LOG.error('%s: %s', e.__class__.__name__, e)
            except Exception as e:
                LOG.critical('%s: %s', e.__class__.__name__, e)
                self._running = False
        self.setcb()
        LOG.debug('Exiting')


class dgram(object):
    """Serial-like UDP port object."""

    def __init__(self, host, port):
        self._host = host
        self._port = port
        self._s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._s.settimeout(0.2)
        self._s.bind(('', self._port))
        self._buf = b''

    def read(self, sz=1):
        ret = b''  # check this condition
        if len(self._buf) == 0:
            nb, addr = self._s.recvfrom(4096)  # timeout raises exception
            if addr[0] == self._host:
                self._buf += nb
        if len(self._buf) > 0:
            ret = self._buf[0]
            self._buf = self._buf[1:]
        return ret

    def write(self, buf=b''):
        return self._s.sendto(buf, (self._host, self._port))

    def close(self):
        self._s.close()
