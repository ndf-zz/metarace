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
  chandelay: (dict) map of channel ids to delay time in seconds [{}]
             example: {'C2':'0.200'}

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
_log = logging.getLogger('metarace.timy')
_log.setLevel(logging.DEBUG)
_TIMER_LOG_LEVEL = 25
logging.addLevelName(_TIMER_LOG_LEVEL, 'TIMER')


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
        self.__port = None
        self.__cqueue = queue.Queue()  # command queue
        self.__rdbuf = b''
        self.__arms = [
            False, False, False, False, False, False, False, False, False,
            False
        ]
        self.__clearing = False
        self.__armlocked = False
        self.__chandelay = {}
        self.__cb = _defcallback
        self.__baudrate = _DEFBAUD
        self.__ctsrts = _DEFCTSRTS
        self.name = 'timy'
        self.error = False
        if sysconf.has_option('timy', 'baudrate'):
            self.__baudrate = sysconf.get_posint('timy', 'baudrate', _DEFBAUD)
            _log.debug('Set serial baudrate to: %d', self.__baudrate)
        if sysconf.has_option('timy', 'ctsrts'):
            self.__ctsrts = sysconf.get_bool('timy', 'ctsrts')
            _log.debug('Set serial CTSRTS to: %s', self.__ctsrts)
        if sysconf.has_option('timy', 'chandelay'):
            nd = sysconf.get('timy', 'chandelay')
            if isinstance(nd, dict):
                for cv in nd:
                    c = chan2id(cv)
                    if c != _CHAN_UNKNOWN:
                        nv = tod.mktod(nd[cv])
                        self.__chandelay[c] = nv
                        _log.debug('Set channel delay %s: %s', c,
                                   nv.rawtime(4))
            else:
                _log.debug('Invalid channel delay setting: %r', nd)

    def setcb(self, func=None):
        """Set or clear impulse callback function."""
        if func is not None:
            self.__cb = func
        else:
            self.__cb = _defcallback

    def printline(self, msg=''):
        """Print msg to Timy printer, stripped and truncated."""
        lmsg = msg[0:32]
        _log.log(_TIMER_LOG_LEVEL, lmsg)
        self.__cqueue.put_nowait(('MSG', 'DTP' + lmsg + '\r'))

    def linefeed(self):
        """Advance Timy printer by one line."""
        self.__cqueue.put_nowait(('MSG', 'PRILF\r'))

    def clrmem(self):
        """Clear memory in attached Timy."""
        self.__cqueue.put_nowait(('MSG', 'CLR\r'))

    def status(self):
        """Request status and current program from Timy."""
        self.__cqueue.put_nowait(('MSG', 'NSF?\r'))
        self.__cqueue.put_nowait(('MSG', 'PROG?\r'))

    def dumpall(self):
        """Request a dump of all recorded impulses to host."""
        self.__cqueue.put_nowait(('MSG', 'RSM\r'))

    def delaytime(self, newdelay='2.0'):
        """Update blocking delay time for all channels."""
        dt = tod.mktod(newdelay)
        if dt is not None:
            if dt > tod.ZERO and dt < tod.tod('99.99'):
                nt = dt.rawtime(2, zeros=True)[6:]
                self.__cqueue.put_nowait(('MSG', 'DTS' + nt + '\r'))
                self.__cqueue.put_nowait(('MSG', 'DTF' + nt + '\r'))
            else:
                _log.info('Ignoring invalid delay time: %s', dt.rawtime())
        else:
            _log.info('Ignoring invalid delay time')

    def printer(self, enable=False):
        """Enable or disable Timy printer."""
        cmd = '0'
        if enable:
            cmd = '1'
        self.__cqueue.put_nowait(('MSG', 'PRINTER' + cmd + '\r'))

    def printimp(self, doprint=True):
        """Enable or disable automatic printing of timing impulses."""
        cmd = '1'
        if doprint:
            cmd = '0'
        self.__cqueue.put_nowait(('MSG', 'PRIIGN' + cmd + '\r'))

    def keylock(self, setlock=True):
        """Set or clear Timy keypad lock function."""
        cmd = '1'
        if not setlock:
            cmd = '0'
        self.__cqueue.put_nowait(('MSG', 'KL' + cmd + '\r'))

    def write(self, msg=None):
        """Queue a raw command string to attached Timy."""
        self.__cqueue.put_nowait(('MSG', msg.rstrip() + '\r'))

    def exit(self, msg=None):
        """Request thread termination."""
        self.running = False
        self.__cqueue.put_nowait(('EXIT', msg))

    def setport(self, device=None):
        """Request (re)opening serial port as specified.

        Call setport with None or an empty string to close an open port
        or to run the Timy thread with no external device.

        """
        self.__cqueue.put_nowait(('PORT', device))

    def arm(self, channel=0):
        """Arm channel 0 - 8 for timing impulses."""
        chan = chan2id(channel)
        _log.debug('Arming channel %s', id2chan(chan))
        self.__arms[chan] = True

    def dearm(self, channel=0):
        """Disarm channel 0 - 8."""
        chan = chan2id(channel)
        _log.debug('De-arm channel %s', id2chan(chan))
        self.__arms[chan] = False

    def armlock(self, lock=True):
        """Set or clear the arming lock."""
        self.__armlocked = bool(lock)
        _log.debug('Armlock is now %s', self.__armlocked)

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
        for msg in [
                'TIMYINIT', 'NSF?', 'PROG?', 'KL0', 'CHK1', 'PRE4', 'RR0',
                'BE1', 'DTS02.00', 'DTF02.00', 'EMU0', 'PRINTER0', 'PRIIGN1',
                'SL0', 'PRILF'
        ]:
            self.write(msg)

    def wait(self):
        """Wait for Timy thread to finish processing any queued commands."""
        self.__cqueue.join()

    def __parse_message(self, msg):
        """Return tod object from timing msg or None."""
        ret = None
        msg = msg.rstrip()  # remove cr/lf if present
        tsum = 0
        csum = 0
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
                        if cid in self.__chandelay:
                            # note: ret might wrap over 24hr boundary
                            ret = ret - self.__chandelay[cid]
                        ret.index = e[0]
                        ret.chan = e[1]
                        ret.refid = ''
                        ret.source = self.name
                    else:
                        _log.error('Invalid message: %s', msg)
                else:
                    _log.error('Invalid message: %s', msg)
            else:
                _log.error('Corrupt message: %s', msg)
                _log.error('Checksum fail: 0x%02X != 0x%02X', tsum, csum)
        else:
            msg = msg.strip()
            if msg == 'CLR':
                self.__cqueue.put_nowait(('RCLR', ''))
        return ret

    def __proc_impulse(self, st):
        """Process a parsed tod impulse from the Timy.

        On reception of a timing channel message, the channel is
        compared against the list of armed channels. If the channel
        is armed, the callback is run.

        If arm lock is not set, the channel is then de-armed.
        """
        _log.log(_TIMER_LOG_LEVEL, st)
        channo = chan2id(st.chan)
        if channo != _CHAN_UNKNOWN:
            if self.__arms[channo]:
                self.__cb(st)
                if not self.__armlocked:
                    self.__arms[channo] = False
            if st.index.isdigit():
                index = int(st.index)
                if index > 2000 and not self.__clearing:
                    self.__clearing = True
                    self.clrmem()
                    _log.debug('Auto clear memory')
        else:
            pass
        return False

    def __read(self):
        """Read messages from timy until a timeout condition."""
        ch = self.__port.read(1)
        mcnt = 0
        while ch != b'':
            if ch == _CR:
                # Return ends the current 'message'
                self.__rdbuf += ch  # include trailing <cr>
                msg = self.__rdbuf.decode(_ENCODING, 'ignore')
                _log.debug(u'RECV: %r', msg)
                t = self.__parse_message(msg)
                if t is not None:
                    self.__proc_impulse(t)
                self.__rdbuf = b''
                mcnt += 1
                if mcnt > 4:  # break to allow write back
                    return
            else:
                self.__rdbuf += ch
            ch = self.__port.read(1)

    def run(self):
        """Run the Timy thread.

           Called by invoking thread method: timy.start()
        """
        running = True
        _log.debug('Starting')
        while running:
            try:
                # Read phase
                if self.__port is not None:
                    self.__read()
                    m = self.__cqueue.get_nowait()
                else:
                    m = self.__cqueue.get()
                self.__cqueue.task_done()

                # Write phase
                if isinstance(m, tuple) and m[0] in _TCMDS:
                    if m[0] == 'MSG':
                        if self.__port is not None and not self.error:
                            _log.debug('SEND: %r', m[1])
                            self.__port.write(m[1].encode(_ENCODING, 'ignore'))
                    elif m[0] == 'TRIG':
                        if isinstance(m[1], tod.tod):
                            self.__proc_impulse(m[1])
                    elif m[0] == 'RCLR':
                        self.__clearing = False
                    elif m[0] == 'EXIT':
                        _log.debug('Request to close: %s', m[1])
                        running = False
                    elif m[0] == 'PORT':
                        if self.__port is not None:
                            self.__port.close()
                            self.__port = None
                        if m[1] is not None and m[1] not in [
                                '', 'NULL', 'None'
                        ]:
                            _log.debug('Re-Connect port: %s @ %d', m[1],
                                       self.__baudrate)
                            self.__port = serial.Serial(m[1],
                                                        self.__baudrate,
                                                        rtscts=self.__ctsrts,
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
                if self.__port is not None:
                    self.__port.close()
                    self.__port = None
                self.error = True
                _log.error('Serial error: %s', e)
            except Exception as e:
                _log.error('%s: %s', e.__class__.__name__, e)
                self.error = True
        if self.__port is not None:
            self.__port.close()
            self.__port = None
        _log.info('Exiting')
