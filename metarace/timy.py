
"""
Notes:

	- ALL timing impulses correctly read from an attached
	  Timy will be logged by the command thread with the log
	  label 'TIMER', even when the channel is not armed.

	- It is assumed that messages are received over the serial
	  connection in the same order as they are measured by
	  the Timy. This means that for any two tod messages read by
          a calling thread, say m1 and m2, the time measured by the
          Timy between the messages will be m2 - m1.

                net = m2 - m1

"""

import threading
import queue
import serial
import logging
import metarace
from metarace import tod
from metarace import strops

# Fallback Configuration defaults
TIMY_PORT = '/dev/ttyS0'
TIMY_ENCODING = 'cp437'	# Timy serial interface encoding
TIMY_BAUD = 38400	# baudrate
TIMY_CTSRTS = False	# hardware flow override in default config

# timing channels
CHAN_START = 0
CHAN_FINISH = 1
CHAN_PA = 2
CHAN_PB = 3
CHAN_200 = 4
CHAN_100 = 5
CHAN_50 = 0  # TODO: use for AUX line into C0
CHAN_AUX = 6 # channels 6-8 are not connected with original TSW-1 cable
CHAN_7 = 7
CHAN_8 = 8
CHAN_INT = 9  # complete the keypad - a key not from timy
CHAN_UNKNOWN = -1

# track layout configurations
LAYOUTS = {
	'DISC':{
		'len':250.0,
		'chans':[CHAN_FINISH, CHAN_200, 6, CHAN_PB, CHAN_100,
                         7, 8, CHAN_PA],
		'offsets':{CHAN_FINISH:0.0,
                           CHAN_200:50.0,
                           6:100.0,		# 50m split
                           CHAN_PB:112.5,
                           CHAN_100:150.0,
                           7:175.0,		# quarter lap split
                           8:200.0,		# 150m split
                           CHAN_PA:237.5}
		}
}

CHANDELAY = {
    0:tod.ZERO, 1:tod.ZERO, 2:tod.ZERO, 3:tod.ZERO,
    4:tod.ZERO, 5:tod.ZERO, 6:tod.ZERO, 7:tod.ZERO,
    8:tod.ZERO, 9:tod.ZERO
}

# thread queue commands -> private to timy thread
TCMDS = ('EXIT', 'PORT', 'MSG', 'TRIG', 'RCLR')

CR = chr(0x0d)
LF = chr(0x0a)

TIMER_LOG_LEVEL = 25
logging.addLevelName(TIMER_LOG_LEVEL, 'TIMER')

def make_sectormap(layout=None):
    """Return a track configuration for the provided layout."""
    ret = {}
    # load layout
    if layout not in LAYOUTS:
        return ret
    track = LAYOUTS[layout]
    tracklen = track['len']	# what about rational lens?
    schans = track['chans']
    dchans = track['chans']
    softs = track['offsets']
    dofts = track['offsets']
    
    for sc in schans:
        for dc in dchans:
            key = (sc, dc)
            if sc == dc:
                ret[key] = tracklen	# full lap
            else:
                soft = softs[sc]
                doft = dofts[dc]
                if soft < doft:
                    ret[key] = doft - soft
                else:
                    ret[key] = tracklen - soft + doft
    return ret
                
def timy_checksum(msg):
    """Return the character sum for the Timy message string."""
    ret = 0
    for ch in msg:
        ret = ret + ord(ch)
    return ret & 0xff

def timy_getsum(chkstr):
    """Convert Timy 'checksum' string to an integer."""
    # assumes ord/string compat - ok for now
    return ((((ord(chkstr[0]) - 0x30) << 4) & 0xf0)
            | ((ord(chkstr[1]) - 0x30) & 0x0f))

def chan2id(chanstr='0'):
    """Return a channel ID for the provided string, without fail."""
    ret = CHAN_UNKNOWN
    if (type(chanstr) in [str, str] and len(chanstr) > 1
        and chanstr[0].upper() == 'C' and chanstr[1].isdigit()):
        ret = int(chanstr[1])
    else:
        try:
            ret = int(chanstr)
        except:
            pass # other errors will re-occur later anyhow
    if ret < CHAN_UNKNOWN or ret > CHAN_INT:
        ret = CHAN_UNKNOWN
    return ret

def id2chan(chanid=0):
    """Return a normalised channel string for the provided channel id."""
    ret = 'C?'
    if type(chanid) is int and chanid >= CHAN_START and chanid <= CHAN_INT:
        ret = 'C' + str(chanid)
    return ret

class timy(threading.Thread):
    """Timy thread object class."""
    def __init__(self, port=None, name='timy'):
        """Construct timy thread object.

        Named parameters:

          port -- serial port
          name -- text identifier for use in log messages

        """
        threading.Thread.__init__(self) 
        self.name = name

        self.port = None
        self.armlocked = False
        self.arms = [False, False, False, False, False,
                     False, False, False, False, False]
        self.lindex = 0
        self.unitno = 'timy01'
        self.clearing = False
        self.error = False
        self.errstr = ''
        self.cqueue = queue.Queue()	# command queue
        self.log = logging.getLogger(self.name)
        self.log.setLevel(logging.DEBUG)
        self.__rdbuf = ''	# should be bytestr?
        self.setcb()	# init but allow overwrite after loadconf
        self.setqcb()	# init but allow overwrite after loadconf
        if port is not None:
            self.setport(port)
        self.chandelay = {}
        for c in CHANDELAY:
            self.chandelay[c] = CHANDELAY[c]

    def __queuecallback(self, evt=None):
        """Default method to queue a callback function."""
        self.__cb(evt)
        return False

    def __defcallback(self, evt=None):
        """Default callback is a tod log entry."""
        self.log.debug('CB ' + str(evt))
        return False

    def setcb(self, func=None):
        """Set or clear the event callback."""
        # if func is not callable, gtk mainloop will catch the error
        if func is not None:
            self.__cb = func
        else:
            self.__cb = self.__defcallback

    def setqcb(self, func=None):
        """Set of clear the queue callback function."""
        if func is not None:
            self.__qcb = func
        else:
            self.__qcb = self.__queuecallback

    def printline(self, msg=''):
        """Print msg to Timy printer, stripped and truncated."""
        lmsg = msg[0:32]
        self.log.log(TIMER_LOG_LEVEL, lmsg)
        self.cqueue.put_nowait(('MSG', 'DTP' + lmsg + '\r'))

    def linefeed(self):
        """Advance Timy printer by one line."""
        self.cqueue.put_nowait(('MSG', 'PRILF\r'))

    def clrmem(self):
        """Clear memory in attached Timy."""
        self.cqueue.put_nowait(('MSG', 'CLR\r'))

    def status(self):
        """Send message to timy."""
        self.cqueue.put_nowait(('MSG', 'NSF\r'))
        self.cqueue.put_nowait(('MSG', 'PROG?\r'))

    def dumpall(self):
        """Request a dump of all times to host."""
        self.cqueue.put_nowait(('MSG', 'RSM\r'))

    def delaytime(self, newdelay):
        """Update the timy channel delays."""
        dt = tod.str2tod(newdelay)
        if dt is not None:
            if dt > tod.ZERO and dt < tod.tod('99.99'):
                nt = dt.rawtime(2, zeros=True)[6:]
                self.cqueue.put_nowait(('MSG', 'DTS' + nt + '\r'))
                self.cqueue.put_nowait(('MSG', 'DTF' + nt + '\r'))
            else:
                sef.log.info('Ignoring invalid delay time: ' + dt.rawtime())
        else:
            sef.log.info('Ignoring invalid delay time.')

    def printer(self, enable=False):
        """Enable or disable printer."""
        cmd = '0'
        if enable:
            cmd = '1'
        self.cqueue.put_nowait(('MSG', 'PRINTER' + cmd + '\r'))

    def printimp(self, doprint=True):
        """Enable or disable internal printing of timing impulses."""
        cmd = '1'
        if doprint:
            cmd = '0'
        self.cqueue.put_nowait(('MSG', 'PRIIGN' + cmd + '\r'))

    def keylock(self, setlock=True):
        cmd = '1'
        if not setlock:
            cmd = '0'
        self.cqueue.put_nowait(('MSG', 'KL' + cmd + '\r'))

    def write(self, msg=None):
        """Queue a raw command string to attached Timy."""
        self.cqueue.put_nowait(('MSG', msg.rstrip() + '\r'))

    def exit(self, msg=None):
        """Request thread termination."""
        self.running = False
        self.cqueue.put_nowait(('EXIT', msg)) # "Prod" command thread

    def setport(self, device=None):
        """Request (re)opening port as specified.

        Device is passed unchanged to serial.Serial constructor.

        Call setport with no argument, None, or an empty string
        to close an open port or to run the timy thread with no
        external device.

        """
        self.cqueue.put_nowait(('PORT', device))

    def arm(self, channel=0):
        """Arm timing channel 0 - 8 for response through rqueue."""
        chan = chan2id(channel)
        self.log.debug('Arming channel ' + id2chan(chan))
        self.arms[chan] = True;

    def dearm(self, channel=0):
        """Disarm timing channel 0 - 8 for response through rqueue."""
        chan = chan2id(channel)
        self.log.debug('Disarming channel ' + id2chan(chan))
        self.arms[chan] = False;

    def armlock(self, lock=True):
        """Set or clear the arming lock - flag only."""
        # thread ok, but needs help
        self.armlocked = bool(lock)

    def start_session(self):
        """Not used."""
        self.log.info('Start Session')

    def stop_session(self):
        """Not used."""
        self.log.info('Stop Session')

    def sync(self):
        """[deprecated] Roughly synchronise Timy to PC clock."""
        self.log.info('Timy Sync deprecated.')

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
              metarace program. It may not always make sense eg, to
              have all channel delays set to 2 hundredths of a
              second, or to have the internal impulse printing off
              by default.

        """
        for msg in ['TIMYINIT', 'NSF', 'PROG?', 'KL0', 'CHK1', 'PRE4',
                    'RR0', 'BE1', 'DTS02.00', 'DTF02.00', 'EMU0',
                    'PRINTER0', 'PRIIGN1',
                    'DTPMetarace ' + metarace.VERSION, 'PRILF']:
            self.write(msg)

    def trig(self, timeval='now', index='FAKE', chan='0',
                   refid='', sourceid=None):
        """Create a fake timing event.

        Parameters:

	    same as for tod constructor

        Fake events are still subject to arming, but they are
        not sent to an attached Timy. While fake events are
        logged with a TIMER label, they will not appear on the
        Timy receipt unless printed explicitly. Fake events are
	processed even if there is no open timy.

        Channel is sanitised before sending to timy thread to
        ensure correct function.

        """
        srcid = self.name
        if sourceid:
            srcid = sourceid
        t = tod.tod(timeval, index, id2chan(chan2id(chan)),
                             refid.lstrip('0'), source=srcid)
        self.cqueue.put_nowait(('TRIG', t))

    def wait(self):
        """Suspend calling thread until the command queue is empty."""
        self.cqueue.join()

    def __parse_message(self, msg):
        """Return tod object from timing msg or None."""
        ret = None
        msg = msg.rstrip()	# remove cr/lf if present
        tsum = 0
        csum = 0
        #ltime = tod.now()
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
                    iv = tod.str2tod(e[2])
                    if iv is not None and cid in self.chandelay:
                        tv = self.chandelay[cid] + iv
                        ret = tod.tod(timeval=tv.timeval, index=e[0],
                                      chan=e[1], source=self.name)
                                      #ltime=ltime.timeval)
                    else:
                        self.log.error('Invalid message: ' + repr(msg))
                else:
                    self.log.error('Invalid message: ' + repr(msg))
            else:
                self.log.error('Corrupt message: ' + repr(msg))
                self.log.error('Checksum fail: 0x%02X != 0x%02X',
                               tsum, csum)
        else:
            msg = msg.strip()
            if msg == 'CLR':
                self.cqueue.put_nowait(('RCLR', ''))
            self.log.debug(repr(msg))	# log std responses
        return ret

    def __proc_impulse(self, st):
        """Process a parsed tod impulse from the Timy.

        On reception of a timing channel message, the channel is
        compared against the list of armed channels. If the channel
        is armed, the tod object is inserted into the response queue.
        If the arm lock is not set, the channel is then de-armed.

        Other messages are ignored for now.

        Todo: Maintain a queue of commands sent and check non-timing
              responses against queued commands to help detect connection
	      errors. [low priority]

        """
        self.log.log(TIMER_LOG_LEVEL, ' ' + str(st))
        channo = chan2id(st.chan)
        if channo != CHAN_UNKNOWN:
            if self.arms[channo]:
                # send the tod to the callback queue function
                self.__qcb(st)
                if not self.armlocked:
                    self.arms[channo] = False
            if st.index.isdigit():
                index = int(st.index) # Value of this is questionable
                #if index - self.lindex > 1:	# in order
                #self.log.warn('Discontinuity in timer: '
                          #+ repr(self.lindex) + ' -> ' + repr(index))
                #self.lindex = index

                # check for mem overflow - dodgey
                if index > 2000 and not self.clearing:
                    self.clearing = True
                    self.clrmem()
                    self.log.log(TIMER_LOG_LEVEL, '-- auto clear memory --')
        else:
            pass # ok to ignore these messages
        return False

    def __read(self):
        """Read messages from timy until a timeout condition."""
## check bytes reading and decode
        ch = self.port.read(1).decode(ENCODING, 'ignore')
        mcnt = 0
        while ch != '':
            if ch == CR:
                # Return ends the current 'message'
                self.__rdbuf += ch      # include trailing <cr>
                t = self.__parse_message(self.__rdbuf)
                if t is not None:
                    self.__proc_impulse(t)
                self.__rdbuf = ''
                mcnt += 1
                if mcnt > 4:	# break to allow write back
                    return
            else:
                self.__rdbuf += ch
            ch = self.port.read(1).decode(ENCODING, 'ignore')

    def run(self):
        running = True
        self.log.debug('Starting')

        # re-read configs from sysconf
        baudrate = TIMY_BAUD
        if metarace.sysconf.has_option('timy', 'baudrate'):
            baudrate = strops.confopt_posint(metarace.sysconf.get('timy',
                                               'baudrate'), baudrate)
        ctsrts = TIMY_CTSRTS
        if metarace.sysconf.has_option('timy', 'ctsrts'):
            ctsrts = strops.confopt_bool(metarace.sysconf.get('timy',
                                               'ctsrts'))
        if metarace.sysconf.has_option('timy', 'chandelay'):
            nd = metarace.sysconf.get('timy', 'chandelay')
            for cv in nd:
                c = chan2id(cv)
                if c in self.chandelay:
                    nv = tod.str2tod(nd[cv])
                    self.chandelay[c] = nv
                    self.log.debug('Set channel delay ' + repr(c) + 
                                   ' : ' + nv.rawtime(4))

        while running:
            try:
                # Read phase
                if self.port is not None:
                    self.__read()
                    m = self.cqueue.get_nowait()	# lock-stepped?
                else:
                    # when no read port avail, block on read of command queue
                    m = self.cqueue.get()
                self.cqueue.task_done()
                
                # Write phase
                if type(m) is tuple and type(m[0]) is str and m[0] in TCMDS:
                    if m[0]=='MSG' and self.port is not None and not self.error:
                        self.log.debug('Sending rawmsg ' + repr(m[1]))
                        self.port.write(m[1].encode(ENCODING,'replace'))
                    elif m[0] == 'TRIG':
                        if type(m[1]) is tod.tod:
                            self.__proc_impulse(m[1])
                    elif m[0] == 'RCLR':
                        self.clearing = False
                    elif m[0] == 'EXIT':
                        self.log.debug('Request to close : ' + str(m[1]))
                        running = False	# This may already be set
                    elif m[0] == 'PORT':
                        if self.port is not None:
                            self.port.close()
                            self.port = None
                        if m[1] is not None and m[1] != '' and m[1] != 'NULL':
                            self.log.debug('Re-Connect port: ' + repr(m[1]))
                            self.port = serial.Serial(m[1], baudrate,
                                                      rtscts=ctsrts,
                                                      timeout=0.2)
                            self.error = False
                        else:
                            self.log.debug('Not connected.')
                            self.error = True
                    else:
                        pass
                else:
                    self.log.warn('Unknown message: ' + repr(m))
            except queue.Empty:
                pass
            except serial.SerialException as e:
                if self.port is not None:
                    self.port.close()
                    self.port = None
                self.errstr = 'Serial port error.'
                self.error = True
                self.log.error('Closed serial port: ' + str(type(e)) + str(e))
            except Exception as e:
                self.log.error('Exception: ' + str(type(e)) + str(e))
                self.errstr = str(e)
                self.error = True
        if self.port is not None:
            self.port.close()
            self.port = None
        self.log.info('Exiting')

if __name__ == '__main__':
    import metarace
    import time
    import random
    metarace.init()
    t = timy(TIMY_PORT)
    lh = logging.StreamHandler()
    lh.setLevel(logging.DEBUG)
    lh.setFormatter(logging.Formatter(
                      "%(asctime)s %(levelname)s:%(name)s: %(message)s"))
    t.log.addHandler(lh)
    ucnt = 0
    try:
        t.start()
        t.sane()
        t.wait()
        t.armlock(True)
        t.arm(0)
        t.arm(1)
        t.arm(2)
        time.sleep(60)
    except:
        t.exit('Exception')
        t.join()
        raise
