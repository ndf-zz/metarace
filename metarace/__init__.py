#
#

import os
import logging
from tempfile import NamedTemporaryFile
from pkg_resources import resource_filename, resource_exists
from metarace import jsonconfig

DATA_PATH = os.path.realpath(os.path.expanduser(
                             os.path.join('~', 'Documents', 'metarace')))
DEFAULTS_PATH = os.path.join(DATA_PATH, '.default')
SYSCONF_FILE = 'metarace.json'
PDF_TEMPLATE_FILE = 'pdf_template.json'
HTML_TEMPLATE_FILE = 'html_template.json'
LOGFORMAT = '%(asctime)s %(levelname)s:%(name)s: %(message)s'
sysconf = jsonconfig.config() # system-defaults, populated by init() method

def init():
    # prepare data directory and chdir
    mk_data_path()
    os.chdir(DATA_PATH)

    # Set global logging options
    logging._srcfile = None
    logging.logThreads = 0
    logging.logProcesses = 0

    # read in system configuration - errors here print to stderr, but
    # are not necessarily fatal.
    conffile = default_file(SYSCONF_FILE)
    try:
        if os.path.exists(conffile):
            with open(conffile, 'r', encoding='utf-8', errors='ignore') as f:
                sysconf.read(f)
    except Exception as e:
        print('Error reading system config from '
              + repr(conffile) + ': ' + repr(e))

def mk_data_path():
    """Create shared data path if it does not exist."""
    if not os.path.exists(DATA_PATH):
        print ('metarace: Creating data directory ' + repr(DATA_PATH))
        os.makedirs(DATA_PATH)
    if not os.path.exists(DEFAULTS_PATH):
        print ('metarace: Creating system defaults in ' + repr(DEFAULTS_PATH))
        os.makedirs(DEFAULTS_PATH)

def default_file(filename=''):
    """Discard any path components then search for file in system paths."""
    filename = os.path.basename(filename)
    if filename in ['..','.','',None]:	# special cases
        return None	# check return value

    ret = filename
    # first try filename as provided in cwd
    if os.path.exists(filename):
        pass
    else:
        # try the system default path
        check = os.path.join(DEFAULTS_PATH, filename)
        if os.path.exists(check):
            ret = check
        else:
            # check for the file in package resources
            try:
                check = 'data/' + filename
                if resource_exists(__name__, check):
                    ret = resource_filename(__name__, check)
            except Exception as e:
                pass
    # it may not be an error if the file does not exist.
    # A failure to open the returned file should
    # be handled appropriately in the calling code.
    return ret

class savefile(object):
    """Tempfile-backed save file contextmanager."""
    def __init__(self, filename, mode='t', encoding='utf-8', tempdir='.'):
        self.__sfile = filename
        self.__path = tempdir
        self.__tfile = NamedTemporaryFile(mode='w'+mode, suffix='.tmp',
                                prefix='sav_', dir=self.__path,
                                encoding=encoding, delete=False)
    def __enter__(self):
        return self.__tfile
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.__tfile.close()
        if exc_type is not None:
            return False        # raise exception
        # otherwise, file is saved ok in temp file
        os.chmod(self.__tfile.name, 0o644)
        try:
            # Posix ensures this is atomic, in windows raises exception
            os.rename(self.__tfile.name, self.__sfile)
        except OSError:
            os.unlink(self.__sfile)
            os.rename(self.__tfile.name, self.__sfile)
        return True

