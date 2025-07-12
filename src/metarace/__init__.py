# SPDX-License-Identifier: MIT
"""A collection of tools for preparing cycle race results."""

import os
import logging
import errno
from tempfile import NamedTemporaryFile
from shutil import copyfile
from metarace import jsonconfig
try:
    from importlib.resources import files, as_file
except ImportError:
    print('Python >= 3.9 required to use this module')
flockstyle = None
try:
    import fcntl
    flockstyle = 'o-g'
except ImportError:
    pass
if flockstyle is None:
    # possibly a windows machine
    import msvcrt
    flockstyle = 'deviant'

VERSION = '2.1.13'
DATA_PATH = os.path.realpath(
    os.path.expanduser(os.path.join('~', 'Documents', 'metarace')))
DEFAULTS_PATH = os.path.join(DATA_PATH, 'default')
RESOURCE_PKG = 'metarace.data'
LOGO = 'metarace_icon.svg'
SYSCONF = 'metarace.json'
PDF_TEMPLATE = 'pdf_template.json'
PROGRAM_TEMPLATE = 'program_template.json'
LOGFILEFORMAT = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
LOGFORMAT = '%(levelname)s %(name)s: %(message)s'
LOGLEVEL = logging.DEBUG  # default console log level
sysconf = jsonconfig.config()  # system-defaults, populated by init() method
_log = logging.getLogger('metarace')
_log.setLevel(logging.DEBUG)


def init():
    """Shared metarace program initialisation."""
    copyconf = mk_data_path()

    # set global logging options
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
    """Create shared data path if it does not yet exist."""
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
    """Return a writeable meet configuration path.

    Args:
        configpath (str): Filename or path.

    Returns:
        str: Path to writeable meet folder or None if not available.

    """
    ret = None
    if configpath is not None:
        ret = configpath
        if not os.path.isdir(ret) and os.path.isfile(ret):
            ret = os.path.dirname(ret)  # assume dangling path contains file
        ret = os.path.realpath(ret)
        _log.debug('Checking for meet %r using %r', configpath, ret)
        if not os.path.exists(ret):
            try:
                _log.info('Creating meet folder %r', ret)
                os.makedirs(ret)
            except Exception as e:
                _log.error('Unable to create folder %r: %s', ret, e)
                ret = None
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

    If file is not found, the original filename is returned.

    Args:
        filename (str): Filename to look up.

    Returns:
        str: Full path to filename in defaults or current directory.

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
            checkfile = os.path.join(DEFAULTS_PATH, basefile)
            os.stat(checkfile)
            ret = checkfile
        except Exception as e:
            # ignore file not found and path errors
            pass
    return ret


def resource_text(name='', encoding='utf-8'):
    """Return string content of named resource.

    Args:
        name (str): Resource name.
        encoding (str, optional): Text file encoding

    Returns:
        str: Text content of named resource.

    Raises:
        FileNotFoundError: If name not available.

    """
    basefile = os.path.basename(name)
    if basefile in ['..', '.', '', None]:
        raise FileNotFoundError('Invalid resource name: ' + repr(name))
    t = files(RESOURCE_PKG).joinpath(basefile)
    if t is not None and t.is_file():
        return t.read_text(encoding=encoding)
    else:
        raise FileNotFoundError('Named resource not found: ' + repr(name))


def resource_file(name=''):
    """Return temporary filename context manager for a named resource.

    Note: Returns context manager for (potentially) temporary filename:

        with resource_file('resource.svg') as filename:
            with open(filename) as file:
                ...

    Args:
        name (str): Resource name.

    Raises:
        FileNotFoundError: If name not available.

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

    Create a temporary file with the desired mode and
    encoding and return a context manager and writable
    file handle.

    On close the temporary file is moved to the provided
    filename, or copied if os.rename is not possible.
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
            copyfile(self.__tfile.name, self.__sfile)
            os.unlink(self.__tfile.name)
        return True


def lockpath(path):
    """Request advisory lockfile in path."""
    if flockstyle is None:
        _log.error('Path locking not available')
        return None
    lockfile = None
    filename = os.path.join(path, '.lock')
    try:
        lockfile = open(filename, 'a+b')
        if flockstyle == 'o-g':
            fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
            _log.debug('Path lock %r acquired by fcntl', filename)
        else:
            lockfile.seek(0)
            msvcrt.locking(lockfile.fileno(), msvcrt.LK_NBLCK, 1)
            _log.debug('Path lock %r acquired by msvcrt', filename)
    except Exception as e:
        if lockfile is not None:
            lockfile.close()
            lockfile = None
        _log.error('Unable to acquire path lock %r: %s', filename, e)
    return lockfile


def unlockpath(path, lockfile):
    """Release advisory lockfile."""
    filename = os.path.join(path, '.lock')
    if os.path.exists(filename):
        os.unlink(filename)
    lockfile.close()
    _log.debug('Path lock %r released', filename)
    return None


LICENSETEXT = """
MIT License

Copyright (c) 2012-2025 ndf-zz and contributors

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""
