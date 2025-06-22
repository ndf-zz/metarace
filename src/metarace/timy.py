# SPDX-License-Identifier: MIT
"""Alge Timy Interface

 Interface an Alge Timy chronoprinter via serial port.

 Example:

	import metarace
	from metarace import timy
	metarace.init()

	def timercb(impulse):
	    print(impulse)

	t = timy.timy()
	t.setport('/dev/ttyS0')
	t.setcb(timercb)
	t.start()
	t.sane()
	t.arm('C0')
	t.armlock()
	...

 Configuration is read from metarace system config (metarace.json),
 under section 'timy':

  key: (type) Description [default]
  --
  baudrate: (int) serial port speed [38400]
  ctsrts: (bool) if True, use hardware flow control [False]
  delayN: (tod) channel N delay time in seconds [None]

 Notes:

	- Callback function is only called for impulses received
	  while channel is armed.

	- ALL timing impulses correctly read from an attached
	  Timy will be logged by the command thread with the log
	  label 'TIMER', even when the channel is not armed.

	- It is assumed that messages are received over the serial
	  connection in the same order as they are measured by
	  the Timy.

	- Channel delay config compensates for wireless impulse
	  or relay sytems with a fixed processing time. To adjust
	  channel blocking delay times, instead use method timy.delaytime()

"""

import threading
import queue
import serial
import logging

from metarace import sysconf
from metarace import tod
from metarace.strops import chan2id, id2chan

# Configuration defaults
_DEFBAUD = 38400
_DEFCTSRTS = False

# Internal constants
_ENCODING = 'cp437'
_CHAN_UNKNOWN = -1
_CR = b'\x0d'
_TCMDS = ('EXIT', 'PORT', 'MSG', 'TRIG', 'RCLR')

# Logging
_log = logging.getLogger('timy')
_log.setLevel(logging.DEBUG)
_TIMER_LOG_LEVEL = 15
logging.addLevelName(_TIMER_LOG_LEVEL, 'TIMER')

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Alge Timy RS-232 Options',
        'control': 'section',
    },
    'baudrate': {
        'prompt': 'Baudrate:',
        'attr': 'baudrate',
        'hint': 'Serial line speed in bps',
        'control': 'choice',
        'type': 'int',
        'options': {
            '9600': '9600 (Timy)',
            '19200': '19200',
            '38400': '38400 (Timy 2/3)'
        },
        'default': _DEFBAUD,
    },
    'ctsrts': {
        'prompt': 'Handshake:',
        'attr': 'cstrts',
        'hint': 'Enable RTS-CTS handshake on serial line',
        'subtext': 'With RTS-CTS?',
        'control': 'check',
        'type': 'bool',
        'default': _DEFCTSRTS,
    },
    'dsec': {
        'prompt': 'Channel Delays',
        'control': 'section',
    },
    'delay0': {
        'prompt': 'C0:',
        'control': 'short',
        'subtext': '(Start)',
        'type': 'tod',
        'places': '4',
    },
    'delay1': {
        'prompt': 'C1:',
        'control': 'short',
        'subtext': '(Finish)',
        'type': 'tod',
        'places': '4',
    },
    'delay2': {
        'prompt': 'C2:',
        'control': 'short',
        'subtext': '(Cell/Pursuit A)',
        'type': 'tod',
        'places': '4',
    },
    'delay3': {
        'prompt': 'C3:',
        'control': 'short',
        'subtext': '(Plunger/Pursuit B)',
        'type': 'tod',
        'places': '4',
    },
    'delay4': {
        'prompt': 'C4:',
        'control': 'short',
        'subtext': '(Aux Start/200m Start)',
        'type': 'tod',
        'places': '4',
    },
    'delay5': {
        'prompt': 'C5:',
        'control': 'short',
        'subtext': '(100m Split)',
        'type': 'tod',
        'places': '4',
    },
    'delay6': {
        'prompt': 'C6:',
        'control': 'short',
        'type': 'tod',
        'places': '4',
    },
    'delay7': {
        'prompt': 'C7:',
        'control': 'short',
        'type': 'tod',
        'places': '4',
    },
    'delay8': {
        'prompt': 'C8:',
        'control': 'short',
        'type': 'tod',
        'places': '4',
    },
}


def _timy_checksum(msg):
    """Return a checksum for the Timy message string."""
    ret = 0
    for ch in msg:
        ret = ret + ord(ch)
    return ret & 0xff


def _timy_getsum(chkstr):
    """Convert Timy checksum string to an integer."""
    ret = -1
    try:
        ms = (ord(chkstr[0]) - 0x30) & 0xf
        ls = (ord(chkstr[1]) - 0x30) & 0xf
        ret = ms << 4 | ls
    except Exception as e:
        _log.debug('error collecting timy checksum: %s', e)
    return ret


def _defcallback(impulse=None):
    """Default impulse callback."""
    _log.debug('Unhandled impulse: %r', impulse)


class timy(threading.Thread):
    """Timy thread object class."""

    def __init__(self):
        """Construct Timy thread object."""
        threading.Thread.__init__(self, daemon=True)
        self._port = None
        self._cqueue = queue.Queue()  # command queue
        self._rdbuf = b''
        self._arms = [
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
            False,
        ]
        self._lastimpulse = [
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        ]
        self._clearing = False
        self._armlocked = False
        self._chandelay = {}
        self._cb = _defcallback
        self._name = 'timy'
        self.error = False

        sysconf.add_section('timy', _CONFIG_SCHEMA)
        self._baudrate = sysconf.get_value('timy', 'baudrate')
        self._ctsrts = sysconf.get_value('timy', 'ctsrts')
        _log.debug('Set serial baudrate to: %d', self._baudrate)
        _log.debug('Set serial CTSRTS to: %s', self._ctsrts)
        for c in range(0, 8):
            cd = sysconf.get_value('timy', 'delay' + str(c))
            if cd is not None:
                self._chandelay[c] = cd
                _log.debug('Set channel delay %s: %s', c, cd.rawtime(4))

    def setcb(self, func=None):
        """Set or clear impulse callback function."""
        if func is not None:
            self._cb = func
        else:
            self._cb = _defcallback

    def printline(self, msg=''):
        """Print msg to Timy printer, stripped and truncated."""
        lmsg = msg[0:32]
        _log.log(_TIMER_LOG_LEVEL, lmsg)
        self._cqueue.put_nowait(('MSG', 'DTP' + lmsg + '\r'))

    def linefeed(self):
        """Advance Timy printer by one line."""
        self._cqueue.put_nowait(('MSG', 'PRILF\r'))

    def clrmem(self):
        """Clear memory in attached Timy."""
        self._cqueue.put_nowait(('MSG', 'CLR\r'))

    def status(self):
        """Request status and current program from Timy."""
        self._cqueue.put_nowait(('MSG', 'NSF?\r'))
        self._cqueue.put_nowait(('MSG', 'PROG?\r'))

    def dumpall(self):
        """Request a dump of all recorded impulses to host."""
        self._cqueue.put_nowait(('MSG', 'RSM\r'))

    def delaytime(self, newdelay='2.0'):
        """Update blocking delay time for all channels."""
        dt = tod.mktod(newdelay)
        if dt is not None:
            if dt > tod.ZERO and dt < tod.tod('99.99'):
                nt = dt.rawtime(2, zeros=True)[6:]
                self._cqueue.put_nowait(('MSG', 'DTS' + nt + '\r'))
                self._cqueue.put_nowait(('MSG', 'DTF' + nt + '\r'))
            else:
                _log.info('Ignoring invalid delay time: %s', dt.rawtime())
        else:
            _log.info('Ignoring invalid delay time')

    def printer(self, enable=False):
        """Enable or disable Timy printer."""
        cmd = '0'
        if enable:
            cmd = '1'
        self._cqueue.put_nowait(('MSG', 'PRINTER' + cmd + '\r'))

    def printimp(self, doprint=True):
        """Enable or disable automatic printing of timing impulses."""
        cmd = '1'
        if doprint:
            cmd = '0'
        self._cqueue.put_nowait(('MSG', 'PRIIGN' + cmd + '\r'))

    def keylock(self, setlock=True):
        """Set or clear Timy keypad lock function."""
        cmd = '1'
        if not setlock:
            cmd = '0'
        self._cqueue.put_nowait(('MSG', 'KL' + cmd + '\r'))

    def write(self, msg=None):
        """Queue a raw command string to attached Timy."""
        self._cqueue.put_nowait(('MSG', msg.rstrip() + '\r'))

    def exit(self, msg=None):
        """Request thread termination."""
        self.running = False
        self._cqueue.put_nowait(('EXIT', msg))

    def setport(self, device=None):
        """Request (re)opening serial port as specified.

        Call setport with None or an empty string to close an open port
        or to run the Timy thread with no external device.

        """
        self._cqueue.put_nowait(('PORT', device))

    def arm(self, channel=0):
        """Arm channel 0 - 8 for timing impulses."""
        chan = chan2id(channel)
        _log.debug('Arming channel %s', id2chan(chan))
        self._arms[chan] = True

    def dearm(self, channel=0):
        """Disarm channel 0 - 8."""
        chan = chan2id(channel)
        _log.debug('De-arm channel %s', id2chan(chan))
        self._arms[chan] = False

    def armlock(self, lock=True):
        """Set or clear the arming lock."""
        self._armlocked = bool(lock)
        _log.debug('Armlock is now %s', self._armlocked)

    def lastimpulse(self, channel=0):
        """Return the last received impulse on channel"""
        chan = chan2id(channel)
        return self._lastimpulse[chan]

    def sane(self):
        """Initialise Timy to 'sane' values.

        Values set by sane():

            TIMIYINIT		- initialise
            KL0			- keylock off
	    CHK1		- enable "checksum"
	    PRE4		- 10,000th sec precision
	    RR0			- Round by 'cut'
	    BE1			- Beep on
	    DTS02.00		- Start delay 2.0
	    DTF02.00		- Finish & intermediate delay 2.0
	    EMU0		- Running time off
	    PRINTER0		- Printer off
	    PRIIGN1		- Don't print all impulses to receipt
            SL0			- Logo off
	    PRILF		- Linefeed
	
        All commands are queued individually to the command thread
        so it may be necessary to use wait() to suspend the calling
        thread until all the commands are sent:

            t.start()
	    t.sane()
	    t.wait()
    
        Note: "sane" here comes from use at track meets with the
              trackmeet program. It may not always make sense eg, to
              have all channel delays set to 2 seconds, or to have
              the internal impulse print off by default.

        """
        for msg in (
                'TIMYINIT',
                'NSF?',
                'PROG?',
                'KL0',
                'CHK1',
                'PRE4',
                'RR0',
                'BE1',
                'DTS02.00',
                'DTF02.00',
                'EMU0',
                'PRINTER0',
                'PRIIGN1',
                'SL0',
                'PRILF',
        ):
            self.write(msg)

    def wait(self):
        """Wait for Timy thread to finish processing any queued commands."""
        self._cqueue.join()

    def _parse_message(self, msg):
        """Return tod object from timing msg or None."""
        ret = None
        msg = msg.rstrip()  # remove cr/lf if present
        tsum = 0
        csum = 0

        if msg == 'CLR':
            self._cqueue.put_nowait(('RCLR', ''))
            _log.debug('RCLR Ack')
        elif msg.startswith('HW_SN'):
            _log.info('%r connected', msg.split()[-1])
        elif msg.startswith('NSF'):
            _log.info('Version: %r', msg.replace('NSF', ''))
        elif msg.startswith('PROG:'):
            _log.debug('Program: %r', msg.split()[-1])
        elif msg.startswith('PULSE HOLD:'):
            _log.warning('Pulse hold: %s', msg.split('][')[1])
        else:
            if len(msg) == 28:
                # assume checksum present, grab it and truncate msg
                tsum = _timy_getsum(msg[26:28])
                msg = msg[0:26]
                csum = _timy_checksum(msg)
            if len(msg) == 26:
                # assume now msg is a timing impulse
                if tsum == csum:
                    e = msg.split()
                    if len(e) == 4:
                        cid = chan2id(e[1])
                        ret = tod.mktod(e[2])
                        if ret is not None:
                            if cid in self._chandelay:
                                # note: ret might wrap over 24hr boundary
                                ret = ret - self._chandelay[cid]
                            ret.index = e[0]
                            ret.chan = e[1]
                            ret.refid = ''
                            ret.source = self._name
                        else:
                            _log.error('Invalid message: %s', msg)
                    else:
                        _log.error('Invalid message: %s', msg)
                else:
                    _log.warning('Corrupt message: %s', msg)
                    _log.debug('Checksum fail: 0x%02X != 0x%02X', tsum, csum)
        return ret

    def _proc_impulse(self, st):
        """Process a parsed tod impulse from the Timy.

        On reception of a timing channel message, the channel is
        compared against the list of armed channels. If the channel
        is armed, the callback is run.

        If arm lock is not set, the channel is then de-armed.
        """
        _log.log(_TIMER_LOG_LEVEL, st)
        nt = tod.now()
        channo = chan2id(st.chan)
        if channo != _CHAN_UNKNOWN:
            if self._arms[channo]:
                self._cb(st)
                if not self._armlocked:
                    self._arms[channo] = False
            if st.index.isdigit():
                index = int(st.index)
                if index > 2000 and not self._clearing:
                    self._clearing = True
                    self.clrmem()
                    _log.debug('Auto clear memory')
            # save impulse to last
            self._lastimpulse[channo] = (st, nt)
        else:
            pass
        return False

    def _read(self):
        """Read messages from timy until a timeout condition."""
        ch = self._port.read(1)
        mcnt = 0
        while ch != b'':
            if ch == _CR:
                # Return ends the current 'message'
                self._rdbuf += ch  # include trailing <cr>
                msg = self._rdbuf.decode(_ENCODING, 'ignore')
                _log.debug('RECV: %r', msg)
                t = self._parse_message(msg)
                if t is not None:
                    self._proc_impulse(t)
                self._rdbuf = b''
                mcnt += 1
                if mcnt > 4:  # break to allow write back
                    return
            else:
                self._rdbuf += ch
            ch = self._port.read(1)

    def run(self):
        """Run the Timy thread.

           Called by invoking thread method: timy.start()
        """
        running = True
        _log.debug('Starting')
        while running:
            try:
                # Read phase
                if self._port is not None:
                    self._read()
                    m = self._cqueue.get_nowait()
                else:
                    m = self._cqueue.get()
                self._cqueue.task_done()

                # Write phase
                if isinstance(m, tuple) and m[0] in _TCMDS:
                    if m[0] == 'MSG':
                        if self._port is not None and not self.error:
                            _log.debug('SEND: %r', m[1])
                            self._port.write(m[1].encode(_ENCODING, 'ignore'))
                    elif m[0] == 'TRIG':
                        if isinstance(m[1], tod.tod):
                            self._proc_impulse(m[1])
                    elif m[0] == 'RCLR':
                        self._clearing = False
                    elif m[0] == 'EXIT':
                        _log.debug('Request to close: %s', m[1])
                        running = False
                    elif m[0] == 'PORT':
                        if self._port is not None:
                            self._port.close()
                            self._port = None
                        if m[1] is not None and m[1] not in [
                                '', 'NULL', 'None'
                        ]:
                            _log.debug('Re-Connect port: %s @ %d', m[1],
                                       self._baudrate)
                            self._port = serial.Serial(m[1],
                                                       self._baudrate,
                                                       rtscts=self._ctsrts,
                                                       timeout=0.2)
                            self.error = False
                        else:
                            _log.debug('Not connected')
                            self.error = True
                    else:
                        pass
                else:
                    _log.warning('Unknown message: %r', m)
            except queue.Empty:
                pass
            except serial.SerialException as e:
                if self._port is not None:
                    self._port.close()
                    self._port = None
                self.error = True
                _log.error('Serial error: %s', e)
            except Exception as e:
                _log.error('%s: %s', e.__class__.__name__, e)
                self.error = True
        if self._port is not None:
            self._port.close()
            self._port = None
        _log.info('Exiting')
