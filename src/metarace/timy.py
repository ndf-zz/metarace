"""Alge Timy I/O helper.

This module provides an interface to an Alge Timy connected
via serial port. Methods are provided to read timing events
as tod objects and to write commands to the Timy. 

A calling thread creates a timy thread and configures it via the
public methods. Timing events are delivered via callback function.

Timing events are only returned if the corresponding channel
is armed. The channel is then de-armed automatically unless
the armlock has been set by the calling thread.

For example:

	Calling thread		Cmd Thread		Timy
						<-	C0 1:23.4567
				C0 not armed
	response is None
	arm(3)		->
				C3 armed
						<-	C3 1:24.4551
				C3 queued
	C3 1:24.4551	<-
				C3 dearmed
						<-	C3 1:24.4901
				C3 not armed
	response is None

When a calling thread sets the arming lock with timy.armlock(True),
a channel remains armed until explicitly dearmed by a calling thread.

Notes:

	- ALL timing impulses correctly read from an attached
	  Timy will be logged by the command thread with the log
	  label 'TIMER', even when the channel is not armed.

	- It is assumed that messages are received over the serial
	  connection in the same order as they are measured by
	  the Timy.
"""

import threading
import queue
import serial
import logging

from metarace import sysconf
from metarace import tod
from metarace import strops

# System default timy serial port
DEFPORT = '/dev/ttyS0'
ENCODING = 'cp437'  # Timy serial interface encoding

# TIMY serial baudrate
TIMY_BAUD = 38400  # default baudrate
TIMY_CTSRTS = False  # default hardware flow control

# thread queue commands
TCMDS = ('EXIT', 'PORT', 'MSG', 'TRIG', 'RCLR')

# timing channel ids
CHAN_UNKNOWN = -1
CHAN_START = 0
CHAN_FINISH = 1
CHAN_PA = 2
CHAN_PB = 3
CHAN_200 = 4
CHAN_100 = 5
CHAN_AUX = 6
CHAN_7 = 7
CHAN_8 = 8
CHAN_INT = 9

CR = b'\x0d'
LOG = logging.getLogger('metarace.timy')
LOG.setLevel(logging.DEBUG)
TIMER_LOG_LEVEL = 25
logging.addLevelName(TIMER_LOG_LEVEL, 'TIMER')


def timy_checksum(msg):
    """Return the checksum for the Timy message string."""
    ret = 0
    for ch in msg:
        ret = ret + ord(ch)
    LOG.debug('checksum calc = %r', ret)
    return ret & 0xff


def timy_getsum(chkstr):
    """Convert Timy checksum string to an integer."""
    ret = -1
    try:
        ms = (ord(chkstr[0]) - 0x30) & 0xf
        ls = (ord(chkstr[1]) - 0x30) & 0xf
        ret = ms << 4 | ls
    except Exception as e:
        LOG.debug('error collecting timy checksum: %s', e)
    return ret


def chan2id(chanstr='0'):
    """Return ID for the provided channel string."""
    ret = CHAN_UNKNOWN
    if (isinstance(chanstr, str) and len(chanstr) > 1
            and chanstr[0].upper() == 'C' and chanstr[1].isdigit()):
        ret = int(chanstr[1])
    else:
        try:
            ret = int(chanstr)
        except Exception:
            pass
    if ret < CHAN_UNKNOWN or ret > CHAN_INT:
        ret = CHAN_UNKNOWN
    return ret


def id2chan(chanid=0):
    """Return normalised channel string for the provided channel id."""
    ret = 'C?'
    if isinstance(chanid, int) and chanid >= CHAN_START and chanid <= CHAN_INT:
        ret = 'C' + str(chanid)
    return ret


class timy(threading.Thread):
    """Timy thread object class."""

    def __init__(self, port=None, name='timy'):
        """Construct timy thread object.

        Named parameters:

          port -- serial port
          name -- text identifier for attached unit

        """
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
        self.__chandelay = {}  # filled in from sysconf
        self.__cb = self.__defcallback
        self.name = name
        self.error = False
        if port is not None:
            self.setport(port)

    def __defcallback(self, evt=None):
        """Default callback is a tod log entry."""
        LOG.debug(evt)
        return False

    def setcb(self, func=None):
        """Set or clear the event callback."""
        if func is not None:
            self.__cb = func
        else:
            self.__cb = self.__defcallback

    def printline(self, msg=''):
        """Print msg to Timy printer, stripped and truncated."""
        lmsg = msg[0:32]
        LOG.log(TIMER_LOG_LEVEL, lmsg)
        self.__cqueue.put_nowait(('MSG', 'DTP' + lmsg + '\r'))

    def linefeed(self):
        """Advance Timy printer by one line."""
        self.__cqueue.put_nowait(('MSG', 'PRILF\r'))

    def clrmem(self):
        """Clear memory in attached Timy."""
        self.__cqueue.put_nowait(('MSG', 'CLR\r'))

    def status(self):
        """Request status and current program."""
        self.__cqueue.put_nowait(('MSG', 'NSF\r'))
        self.__cqueue.put_nowait(('MSG', 'PROG?\r'))

    def dumpall(self):
        """Request a dump of all times to host."""
        self.__cqueue.put_nowait(('MSG', 'RSM\r'))

    def delaytime(self, newdelay):
        """Update the timy hardware channel delays."""
        dt = tod.mktod(newdelay)
        if dt is not None:
            if dt > tod.ZERO and dt < tod.tod('99.99'):
                nt = dt.rawtime(2, zeros=True)[6:]
                self.__cqueue.put_nowait(('MSG', 'DTS' + nt + '\r'))
                self.__cqueue.put_nowait(('MSG', 'DTF' + nt + '\r'))
            else:
                LOG.info('Ignoring invalid delay time: %s', dt.rawtime())
        else:
            LOG.info('Ignoring invalid delay time')

    def printer(self, enable=False):
        """Enable or disable printer."""
        cmd = '0'
        if enable:
            cmd = '1'
        self.__cqueue.put_nowait(('MSG', 'PRINTER' + cmd + '\r'))

    def printimp(self, doprint=True):
        """Enable or disable internal print of timing impulses."""
        cmd = '1'
        if doprint:
            cmd = '0'
        self.__cqueue.put_nowait(('MSG', 'PRIIGN' + cmd + '\r'))

    def keylock(self, setlock=True):
        """Set or clear the timy keypad lock function."""
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
        """Request (re)opening port as specified.

        Device is passed unchanged to serial.Serial constructor.

        Call setport with no argument, None, or an empty string
        to close an open port or to run the timy thread with no
        external device.

        """
        self.__cqueue.put_nowait(('PORT', device))

    def arm(self, channel=0):
        """Arm timing channel 0 - 8 for response through rqueue."""
        chan = chan2id(channel)
        LOG.debug('Arming channel %s', id2chan(chan))
        self.__arms[chan] = True

    def dearm(self, channel=0):
        """Disarm timing channel 0 - 8 for response through rqueue."""
        chan = chan2id(channel)
        LOG.debug('De-arm channel %s', id2chan(chan))
        self.__arms[chan] = False

    def armlock(self, lock=True):
        """Set or clear the arming lock - flag only."""
        self.__armlocked = bool(lock)
        LOG.debug('Armlock is now %s', self.__armlocked)

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
	    PRILF		- Linefeed
	
        All commands are queued individually to the command thread
        so it may be necessary to use wait() to suspend the calling
        thread until all the commands are sent:

            t.start()
	    t.sane()
	    t.wait()
    
        Note: "sane" here comes from use at track meets with the
              trackmeet program. It may not always make sense eg, to
              have all channel delays set to 2 hundredths of a
              second, or to have the internal impulse print off
              by default.

        """
        for msg in [
                'TIMYINIT', 'NSF', 'PROG?', 'KL0', 'CHK1', 'PRE4', 'RR0',
                'BE1', 'DTS02.00', 'DTF02.00', 'EMU0', 'PRINTER0', 'PRIIGN1',
                'DTPMetarace ' + tod.now().meridiem(), 'PRILF'
        ]:
            self.write(msg)

    def trig(self, impulse):
        """Queue a fake timing event."""
        impulse.chan = id2chan(chan2id(impulse.chan))
        self.__cqueue.put_nowait(('TRIG', impulse))

    def wait(self):
        """Suspend caller until the command queue is empty."""
        self.__cqueue.join()

    def __parse_message(self, msg):
        """Return tod object from timing msg or None."""
        LOG.debug('TIMY raw msg: %r', msg)
        ret = None
        msg = msg.rstrip()  # remove cr/lf if present
        tsum = 0
        csum = 0
        if len(msg) == 28:
            # assume checksum present, grab it and truncate msg
            tsum = timy_getsum(msg[26:28])
            msg = msg[0:26]
            csum = timy_checksum(msg)
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
                        LOG.error('Invalid message: %s', msg)
                else:
                    LOG.error('Invalid message: %s', msg)
            else:
                LOG.error('Corrupt message: %s', msg)
                LOG.error('Checksum fail: 0x%02X != 0x%02X', tsum, csum)
        else:
            msg = msg.strip()
            if msg == 'CLR':
                self.__cqueue.put_nowait(('RCLR', ''))
            LOG.debug(msg)  # log std responses
        return ret

    def __proc_impulse(self, st):
        """Process a parsed tod impulse from the Timy.

        On reception of a timing channel message, the channel is
        compared against the list of armed channels. If the channel
        is armed, the callback is run.

        If arm lock is not set, the channel is then de-armed.
        """
        LOG.log(TIMER_LOG_LEVEL, st)
        channo = chan2id(st.chan)
        if channo != CHAN_UNKNOWN:
            if self.__arms[channo]:
                self.__cb(st)
                if not self.__armlocked:
                    self.__arms[channo] = False
            if st.index.isdigit():
                index = int(st.index)
                if index > 2000 and not self.__clearing:
                    self.__clearing = True
                    self.clrmem()
                    LOG.debug('Auto clear memory')
        else:
            pass
        return False

    def __read(self):
        """Read messages from timy until a timeout condition."""
        ch = self.__port.read(1)
        mcnt = 0
        while ch != b'':
            if ch == CR:
                # Return ends the current 'message'
                self.__rdbuf += ch  # include trailing <cr>
                t = self.__parse_message(self.__rdbuf.decode(ENCODING, 'replace'))
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
        running = True
        LOG.debug('Starting')

        # re-read serial port and delay config from sysconf
        baudrate = TIMY_BAUD
        if sysconf.has_option('timy', 'baudrate'):
            baudrate = strops.confopt_posint(sysconf.get('timy', 'baudrate'),
                                             baudrate)
            LOG.debug('Set serial baudrate to: %d', baudrate)
        ctsrts = TIMY_CTSRTS
        if sysconf.has_option('timy', 'ctsrts'):
            ctsrts = strops.confopt_bool(sysconf.get('timy', 'ctsrts'))
            LOG.debug('Set serial CTSRTS to: %s', str(ctsrts))
        if sysconf.has_option('timy', 'chandelay'):
            nd = sysconf.get('timy', 'chandelay')
            for cv in nd:
                c = chan2id(cv)
                if c != CHAN_UNKNOWN:
                    nv = tod.mktod(nd[cv])
                    self.__chandelay[c] = nv
                    LOG.debug('Set channel delay %s: %s', c, nv.rawtime(4))
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
                if isinstance(m, tuple) and m[0] in TCMDS:
                    if m[0] == 'MSG':
                        if self.__port is not None and not self.error:
                            LOG.debug('Sending rawmsg: %s', repr(m[1]))
                            self.__port.write(m[1].encode(ENCODING, 'replace'))
                    elif m[0] == 'TRIG':
                        if isinstance(m[1], tod.tod):
                            self.__proc_impulse(m[1])
                    elif m[0] == 'RCLR':
                        self.__clearing = False
                    elif m[0] == 'EXIT':
                        LOG.debug('Request to close: %s', m[1])
                        running = False
                    elif m[0] == 'PORT':
                        if self.__port is not None:
                            self.__port.close()
                            self.__port = None
                        if m[1] is not None and m[1] not in [
                                '', 'NULL', 'None'
                        ]:
                            LOG.debug('Re-Connect port: %s @ %d', m[1],
                                      baudrate)
                            self.__port = serial.Serial(m[1],
                                                        baudrate,
                                                        rtscts=ctsrts,
                                                        timeout=0.2)
                            self.error = False
                        else:
                            LOG.debug('Not connected')
                            self.error = True
                    else:
                        pass
                else:
                    LOG.warning('Unknown message: %r', m)
            except queue.Empty:
                pass
            except serial.SerialException as e:
                if self.__port is not None:
                    self.__port.close()
                    self.__port = None
                self.error = True
                LOG.error('Serial error: %s', e)
            except Exception as e:
                LOG.error('%s: %s', e.__class__.__name__, e)
                self.error = True
        if self.__port is not None:
            self.__port.close()
            self.__port = None
        LOG.info('Exiting')
