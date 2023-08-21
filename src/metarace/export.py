# SPDX-License-Identifier: MIT
"""export result files in a subprocess"""

import threading
import subprocess
import logging
import os

import metarace

# Default Rsync options:
#  -a archive mode
#  -z compress file data during the transfer
#  -L transform symlink into referent file/dir
_RSYNC_OPTS = '-azL'

# Password file for TCP daemon connections
_RSYNC_PWD = 'rsync.pwd'

_log = logging.getLogger('export')
_log.setLevel(logging.DEBUG)

_CONFIG_SCHEMA = {
    'ttype': {
        'prompt': 'Result Export',
        'control': 'section',
    },
    'method': {
        'prompt': 'Method:',
        'hint': 'Export mechanism',
        'control': 'choice',
        'options': {
            'ssh': 'Rsync over SSH',
            'rsync': 'Rsync TCP daemon',
            'shell': 'Export script',
        },
    },
    'timeout': {
        'prompt': 'Timeout:',
        'subtext': 'seconds',
        'hint': 'Export command timeout',
        'control': 'short',
        'type': 'int',
        'default': 30
    },
    'host': {
        'prompt': 'Hostname:',
        'hint': 'Optional hostname, IP or SSH host to connect to',
    },
    'port': {
        'prompt': 'Port:',
        'subtext': '(TCP daemon only)',
        'hint': 'Optional TCP port for rsync TCP daemon',
        'type': 'int',
        'control': 'short',
    },
    'username': {
        'prompt': 'Username:',
        'hint': 'Optional username on remote host',
    },
    'basepath': {
        'prompt': 'Basepath:',
        'hint': 'Optional base path on remote server (without trailing slash)',
    }
}


class mirror(threading.Thread):
    """Mirror thread object class."""

    def __init__(self,
                 callback=None,
                 callbackdata=None,
                 localpath=None,
                 remotepath=None,
                 mirrorcmd=None):
        """Construct mirror thread object."""
        threading.Thread.__init__(self, daemon=True)
        self.__cb = None
        if callback is not None:
            self.__cb = callback
        self.__cbdata = None
        if callbackdata is not None:
            self.__cbdata = callbackdata
        self.__localpath = '.'
        if localpath is not None:
            self.__localpath = localpath
        self.__remotepath = ''
        if remotepath is not None:
            self.__remotepath = remotepath
        self.__mirrorcmd = ''
        if isinstance(mirrorcmd, str) and mirrorcmd:
            self.__mirrorcmd = mirrorcmd

        # read configuration from sysconf
        metarace.sysconf.add_section('export', _CONFIG_SCHEMA)
        self.__method = metarace.sysconf.get_value('export', 'method')
        self.__timeout = metarace.sysconf.get_value('export', 'timeout')
        self.__host = metarace.sysconf.get_value('export', 'host')
        self.__port = metarace.sysconf.get_value('export', 'port')
        self.__username = metarace.sysconf.get_value('export', 'username')
        self.__basepath = metarace.sysconf.get_value('export', 'basepath')

        # save return code and output
        self.returncode = None
        self.stderr = None

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
        if self.__method is None:
            _log.info('Export method not set, files not mirrored')
            return None

        # prepare command line
        _log.debug('Starting export method=%r', self.__method)
        if self.__method == 'shell':
            if self.__mirrorcmd:
                arglist = (self.__mirrorcmd, self.__remotepath)
            else:
                _log.warning('No mirrorcmd specified, export cancelled')
                return None
        elif self.__method == 'ssh':
            dest = self.__remotepath
            if self.__basepath:
                dest = os.path.join(self.__basepath, dest)
            if self.__host:
                dest = self.__host + ':' + dest
            if self.__username:
                dest = self.__username + '@' + dest
            arglist = ('rsync', _RSYNC_OPTS, self.__localpath, dest)
        elif self.__method == 'rsync':
            if self.__host:
                pwarg = '--password-file=' + metarace.default_file('rsync.pwd')
                host = self.__host
                if self.__port is not None:
                    host = host + ':' + str(self.__port)
                if self.__username is not None:
                    host = self.__username + '@' + host
                host = 'rsync://' + host
                dest = self.__remotepath
                if self.__basepath:
                    dest = os.path.join(self.__basepath, dest)
                dest = host + '/' + dest
                arglist = ('rsync', pwarg, _RSYNC_OPTS, self.__localpath, dest)
            else:
                _log.info('TCP host missing, export ignored')
                return None
        else:
            _log.info('Unknown export method %r ignored', self.__method)
            return None

        ret = None
        try:
            _log.debug('Calling subprocess: %r', arglist)
            res = subprocess.run(arglist,
                                 timeout=self.__timeout,
                                 check=True,
                                 capture_output=True)
            if self.__cb is not None:
                self.__cb(res, self.__cbdata)
            self.returncode = res.returncode
            ret = res.returncode
        except subprocess.CalledProcessError as e:
            _log.debug('%r stderr: %r', self.__method, e.stderr)
            _log.error('Export command failed with error: %r', e.returncode)
            self.stderr = e.stderr
        except subprocess.TimeoutExpired as e:
            _log.debug('%r stderr: %r', self.__method, e.stderr)
            _log.error('Timeout waiting for export command to complete')
        except Exception as e:
            _log.error('%s: %s', e.__class__.__name__, e)
        _log.debug('Complete: Returned %r', ret)
