# SPDX-License-Identifier: MIT
"""Transponder 'decoder' interface."""

import threading
import queue
import logging

from metarace import tod

_log = logging.getLogger('decoder')
_log.setLevel(logging.DEBUG)
DECODER_LOG_LEVEL = 15
logging.addLevelName(DECODER_LOG_LEVEL, 'DECODER')
_PHOTOTHRESH = tod.tod('0.03')


class decoder(threading.Thread):
    """Idealised transponder decoder interface."""

    # API Methods
    def getcb(self):
        """Return the current callback function."""
        return self._cb

    def setcb(self, func=None):
        """Set or clear the event callback."""
        if func is not None:
            self._cb = func
        else:
            self._cb = self._defcallback

    def running(self):
        """Return state of running flag."""
        return self._running

    def connected(self):
        """Return true if decoder instance is connected."""
        return False

    def exit(self, msg=None):
        """Request thread termination."""
        self._running = False
        self._cqueue.put_nowait(('_exit', msg))

    def setport(self, device=None):
        """Request new device address."""
        self._flush()
        self._cqueue.put_nowait(('_port', device))

    def sane(self, data=None):
        """Reset decoder to sane state."""
        self._cqueue.put_nowait(('_sane', data))

    def sync(self, data=None):
        """Synchronise decoder to host PC time."""
        self._cqueue.put_nowait(('_sync', data))

    def start_session(self, data=None):
        """Request decoder start timing session."""
        self._cqueue.put_nowait(('_start_session', data))

    def stop_session(self, data=None):
        """Request decoder stop timing session."""
        self._cqueue.put_nowait(('_stop_session', data))

    def status(self, data=None):
        """Request status message from decoder."""
        self._cqueue.put_nowait(('_status', data))

    def clear(self, data=None):
        """Clear passings in decoder memory."""
        self._cqueue.put_nowait(('_clear', data))

    def trig(self, impulse=None):
        """Queue a fake timing impulse through decoder interface."""
        self._cqueue.put_nowait(('_trig', impulse))

    def replay(self, file=None):
        """Request replay of passings from the provided file indicator."""
        self._cqueue.put_nowait(('_replay', file))

    def wait(self):
        """Suspend calling thread until the command queue is empty."""
        self._cqueue.join()

    def write(self, msg=None):
        """Queue a raw device command string."""
        self._cqueue.put_nowait(('_write', msg))

    def photothresh(self):
        """Return the photo finish threshold."""
        return _PHOTOTHRESH

    # Private Methods
    def __init__(self):
        threading.Thread.__init__(self, daemon=True)
        self._cqueue = queue.Queue()
        self._running = False
        self._cb = self._defcallback

    def _defcallback(self, evt=None):
        """Default callback is a debug log entry."""
        _log.debug(str(evt))

    def _close(self):
        """Close hardware connection to decoder."""
        raise NotImplementedError('decoder._close()')

    def _flush(self):
        """Clear out the command queue."""
        try:
            while True:
                self._cqueue.get_nowait()
                self._cqueue.task_done()
        except queue.Empty:
            pass

    def _exit(self, msg):
        """Handle request to exit."""
        _log.debug('Request to exit: %r', msg)
        self._close()
        self._flush()
        self._running = False

    def _port(self, port):
        """Re-connect decoder hardware."""
        raise NotImplementedError('decoder._port()')

    def _sane(self, data=None):
        """Return decoder to known initial state."""
        raise NotImplementedError('decoder._sane()')

    def _sync(self, data=None):
        """Roughly align decoder timebase with host PC clock."""
        raise NotImplementedError('decoder._sync()')

    def _start_session(self, data=None):
        """Start decoder timing session."""
        raise NotImplementedError('decoder._start_session()')

    def _stop_session(self, data=None):
        """Stop decoder timing session."""
        raise NotImplementedError('decoder._stop_session()')

    def _status(self, data=None):
        """Request status from decoder."""
        raise NotImplementedError('decoder._status()')

    def _clear(self, data=None):
        """Request clear of memory on decoder."""
        raise NotImplementedError('decoder._clear()')

    def _trig(self, impulse):
        """Return a timing impulse to the host application."""
        self._cb(impulse)

    def _replay(self, file):
        """Request a replay of passings from file."""
        raise NotImplementedError('decoder._replay()')

    def _write(self, msg):
        """Write the supplied msg to the decoder."""
        raise NotImplementedError('decoder._write()')

    def _proccmd(self, cmd):
        """Process a command tuple from the queue."""
        method = getattr(self, cmd[0], None)
        if method is not None:
            method(cmd[1])
        else:
            _log.debug('Unknown command: %r', cmd)

    def run(self):
        """Decoder main loop."""
        _log.debug('Starting')
        self._running = True
        while self._running:
            try:
                c = self._cqueue.get()
                self._cqueue.task_done()
                self._proccmd(c)
            except Exception as e:
                # errors in dummy decoder should not appear in UI
                _log.debug('%s: %s', e.__class__.__name__, e)
        self.setcb()  # make sure callback is unrefed
        _log.debug('Exiting')
