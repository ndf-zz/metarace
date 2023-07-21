# SPDX-License-Identifier: MIT
"""A collection of tools for preparing cycle race results."""

import os
import logging
import fcntl
import errno
from tempfile import NamedTemporaryFile
from shutil import copyfile
from metarace import jsonconfig
try:
    from importlib.resources import files, as_file
except ImportError:
    print('Python >= 3.9 is required to use this module')

VERSION = '2.1.4'
DATA_PATH = os.path.realpath(
    os.path.expanduser(os.path.join('~', 'Documents', 'metarace')))
DEFAULTS_PATH = os.path.join(DATA_PATH, 'default')
RESOURCE_PKG = 'metarace.data'
LOGO = 'metarace_icon.svg'
SYSCONF = 'metarace.json'
PDF_TEMPLATE = 'pdf_template.json'
LOGFILEFORMAT = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
LOGFORMAT = '%(levelname)s %(name)s: %(message)s'
LOGLEVEL = logging.DEBUG  # default console log level
sysconf = jsonconfig.config()  # system-defaults, populated by init() method
_log = logging.getLogger('metarace')
_log.setLevel(logging.DEBUG)


def init():
    """Shared metarace program initialisation."""
    copyconf = mk_data_path()

    # Set global logging options
    logging._srcfile = None
    logging.logThreads = 0
    logging.logProcesses = 0

    # read in a system configuration
    conffile = default_file(SYSCONF)
    try:
        if os.path.exists(conffile):
            sysconf.load(conffile)
            # don't copy path-specific config into defaults
            copyconf = False
        else:
            _log.info('System defaults not present, using package defaults')
            ref = files(RESOURCE_PKG).joinpath(SYSCONF)
            with ref.open('rb') as f:
                sysconf.read(f)
            copyconf = True
    except Exception as e:
        _log.error('%s reading system config: %s', e.__class__.__name__, e)

    # if required, create new system default file
    if copyconf:
        _log.info('Creating default system config %s', SYSCONF)
        with savefile(os.path.join(DEFAULTS_PATH, SYSCONF), perm=0o600) as f:
            sysconf.write(f)


def mk_data_path():
    """Create a shared data path if it does not yet exist."""
    ret = False
    if not os.path.exists(DATA_PATH):
        _log.info('Creating data directory: %r', DATA_PATH)
        os.makedirs(DATA_PATH)
    if not os.path.exists(DEFAULTS_PATH):
        _log.info('Creating system defaults directory: %r', DEFAULTS_PATH)
        os.makedirs(DEFAULTS_PATH)
        ret = True  # flag copy of config back to defaults path
    lfile = os.path.join(DEFAULTS_PATH, LOGO)
    if not os.path.exists(lfile):
        _log.info('Saving default app logo into defaults path')
        ref = files(RESOURCE_PKG).joinpath(LOGO)
        with ref.open('rb') as sf:
            with savefile(lfile, mode='b') as df:
                df.write(sf.read())
    return ret


def config_path(configpath=None):
    """Clean and check argument for a writeable meet configuration path."""
    ret = None
    if configpath is not None:
        # sanitise into expected config path
        ret = configpath
        if not os.path.isdir(ret):
            ret = os.path.dirname(ret)  # assume dangling path contains file
        ret = os.path.realpath(ret)
        _log.debug('Checking for meet %r using %r', configpath, ret)
        # then check if the path exists
        if not os.path.exists(ret):
            try:
                _log.info('Creating meet folder %r', ret)
                os.makedirs(ret)
            except Exception as e:
                _log.error('Unable to create folder %r: %s', ret, e)
                ret = None
        # check the path is writable
        if ret is not None:
            try:
                _log.debug('Checking folder %r for write access', ret)
                with NamedTemporaryFile(dir=ret, prefix='.chkwrite_') as f:
                    pass
            except Exception as e:
                _log.error('Unable to access meet folder %r: %s', ret, e)
                ret = None
    return ret


def default_file(filename=''):
    """Return a path to the named file.

    Path components are stripped, then the the following locations
    are checked in order to find the first instance of filename:
        - current working directory
        - DEFAULTS_PATH
    """
    basefile = os.path.basename(filename)
    if basefile in ['..', '.', '', None]:
        _log.debug('Invalid filename %r ignored', filename)
        return None
    ret = basefile
    if os.path.exists(basefile):
        pass
    else:
        try:
            check = os.path.join(DEFAULTS_PATH, basefile)
            os.stat(check)
            ret = check
        except Exception as e:
            # ignore file not found and path errors
            pass
    return ret


def resource_text(name=''):
    """Return a string from the contents of the named resource."""
    basefile = os.path.basename(name)
    if basefile in ['..', '.', '', None]:
        raise FileNotFoundError('Invalid resource name: ' + repr(name))
    t = files(RESOURCE_PKG).joinpath(basefile)
    if t is not None and t.is_file():
        return t.read_text(encoding='utf-8')
    else:
        raise FileNotFoundError('Named resource not found: ' + repr(name))


def resource_file(name=''):
    """Return a temporary filename context manager for a named resource.

    Note: This returns a context manager for a (potentially) temporary
          filename on the filesystem, it must be used in a with statement
          eg:

          with resource_file('resource.svg') as r:
              Gtk.Image.new_from_file(r)
    """

    basefile = os.path.basename(name)
    if basefile in ['..', '.', '', None]:
        raise FileNotFoundError('Invalid resource name: ' + repr(name))
    t = files(RESOURCE_PKG).joinpath(basefile)
    if t is not None and t.is_file():
        return as_file(t)
    else:
        raise FileNotFoundError('Named resource not found: ' + repr(name))


class savefile:
    """Tempfile-backed save file contextmanager.

       Creates a temporary file with the desired mode and encoding
       and returns a context manager and writable file handle.

       On close, the temp file is atomically moved to the provided
       filename (if possible).

       Note: This function will log a warning if the file could not be
       moved atomically.
    """

    def __init__(self,
                 filename,
                 mode='t',
                 encoding='utf-8',
                 tempdir='.',
                 perm=0o644):
        self.__sfile = filename
        self.__path = tempdir
        self.__perm = perm
        if mode == 'b':
            encoding = None
        self.__tfile = NamedTemporaryFile(mode='w' + mode,
                                          suffix='.tmp',
                                          prefix='sav_',
                                          dir=self.__path,
                                          encoding=encoding,
                                          delete=False)

    def __enter__(self):
        return self.__tfile

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__tfile.close()
        if exc_type is not None:
            return False  # raise exception
        # otherwise, file is saved ok in temp file
        os.chmod(self.__tfile.name, self.__perm)
        try:
            os.rename(self.__tfile.name, self.__sfile)
        except OSError as e:
            _log.debug('os.rename failed: %s', e)
            copyfile(self.__tfile.name, self.__sfile)
            _log.warn('Un-safely moved file: %r', self.__sfile)
            os.unlink(self.__tfile.name)
        return True


def lockpath(configpath):
    """Open an advisory lock file in the meet config path."""
    lf = None
    lfn = os.path.join(configpath, '.lock')
    try:
        lf = open(lfn, 'a+b')
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _log.debug('Config lock %r acquired', lfn)
    except Exception as e:
        if lf is not None:
            lf.close()
            lf = None
        _log.error('Unable to acquire config lock %r: %s', lfn, e)
    return lf


def unlockpath(configpath, lockfile):
    """Release advisory lock and remove lock file."""
    lfn = os.path.join(configpath, '.lock')
    os.unlink(lfn)
    lockfile.close()
    _log.debug('Config lock %r released', lfn)
    return None


LICENSETEXT = """
MIT License

Copyright (c) 2012-2023 Nathan Fraser and contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
