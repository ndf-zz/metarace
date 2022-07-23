# SPDX-License-Identifier: MIT
"""export result files in a thread"""

import threading
import subprocess
import logging
import os

import metarace

MIRROR_CMD = 'echo'  # Command/Argument defaults
MIRROR_ARGS = ['dummy', 'srcdir={srcdir}', 'dstdir={dstdir}']
MIRROR_TIMEOUT = 30
LOG = logging.getLogger('metarace.export')
LOG.setLevel(logging.DEBUG)


class mirror(threading.Thread):
    """Mirror thread object class."""

    def __init__(self,
                 callback=None,
                 callbackdata=None,
                 localpath='.',
                 remotepath=None,
                 mirrorcmd=None,
                 arguments=None,
                 data=None):
        """Construct mirror thread object."""
        threading.Thread.__init__(self, daemon=True)
        self.__cb = None
        if callback is not None:
            self.__cb = callback
        self.__cbdata = None
        if callbackdata is not None:
            self.__cbdata = callbackdata
        self.__localpath = localpath
        self.__remotepath = ''
        if remotepath is not None:
            self.__remotepath = remotepath

        # config starts with module defaults
        self.__mirrorcmd = MIRROR_CMD
        self.__arguments = MIRROR_ARGS
        self.__timeout = MIRROR_TIMEOUT

        # then overwrite from sysconf - if present
        if metarace.sysconf.has_section('export'):
            if metarace.sysconf.has_option('export', 'command'):
                self.__mirrorcmd = metarace.sysconf.get('export', 'command')
            if metarace.sysconf.has_option('export', 'arguments'):
                self.__arguments = metarace.sysconf.get('export', 'arguments')
            if metarace.sysconf.has_option('export', 'timeout'):
                self.__timeout = metarace.sysconf.get('export', 'timeout')

        # and then finally allow override in object creation
        if mirrorcmd:
            self.__mirrorcmd = mirrorcmd
        if arguments:
            self.__arguments = arguments

        self.__data = data

    def set_remotepath(self, pathstr):
        """Set or clear the remote path value."""
        self.__remotepath = pathstr

    def set_localpath(self, pathstr):
        """Set or clear the local path value."""
        self.__localpath = pathstr

    def set_cb(self, func=None, cbdata=None):
        """Set or clear the event callback."""
        if func is not None:
            self.__cb = func
            self.__cbdata = cbdata
        else:
            self.__cb = None
            self.__cbdata = None

    def run(self):
        """Called via threading.Thread.start()."""
        running = True
        LOG.debug('Starting')
        ret = None
        try:
            # format errors in arguments caught as exception
            arglist = [
                a.format(srcdir=self.__localpath,
                         dstdir=self.__remotepath,
                         command=self.__mirrorcmd,
                         data=self.__data) for a in self.__arguments
            ]
            arglist.insert(0, self.__mirrorcmd)

            LOG.debug('Calling subprocess: %r', arglist)
            ret = subprocess.run(arglist,
                                 timeout=self.__timeout,
                                 check=True,
                                 capture_output=True)
            if self.__cb is not None:
                self.__cb(ret, self.__cbdata)
        except subprocess.CalledProcessError as e:
            LOG.error('%r returned %r: %s', self.__mirrorcmd, e.returncode,
                      e.stderr.decode('utf8', 'ignore'))
        except Exception as e:
            LOG.error('%s: %s', e.__class__.__name__, e)
        LOG.debug('Complete: Returned %r', ret)
