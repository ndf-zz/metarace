# metarace

Archived: 2026-05-14
Moved to: https://codeberg.org/ndf-zz/metarace

A collection of Python modules to assist with cycle race timekeeping
and official result preparation. Version 2 of Metarace is a
re-write for Python 3 which removes static pyGTK/GLib dependencies.

Desktop applications are available separately, and may be installed
using a shared installation script
[metarace-install](https://6-v.org/software/install.html).


## Support

   - Signal Group: [metarace](https://signal.group/#CjQKII2j2E7Zxn7dHgsazfKlrIXfhjgZOUB3OUFhzKyb-p_bEhBehsI65MhGABZaJeJ-tMZl)
   - Issues: [issues](https://codeberg.org/ndf-zz/metarace/issues)


## Requirements

System requirements:

   - Python >= 3.11
   - Cairo
   - Pango
   - Rsvg
   - Python gi
   - Python gi-cairo
   - tex-gyre (optional, recommended)
   - evince (optional, recommended)
   - fonts-noto (optional)
   - mosquitto (optional)
   - libreoffice (optional)

Python packages:

   - requests: HTTP requests
   - pyserial: Serial port interface
   - python-dateutil: Generic date/time string parser
   - xlsxwriter: XLSX file writer
   - paho-mqtt: MQTT interface
   - graphemeu: Unicode grapheme support


## Manual Installation

Install minimum system requirements with apt:

	$ sudo apt install python3-venv python3-pip python3-cairo python3-gi python3-gi-cairo gir1.2-rsvg-2.0 gir1.2-pango-1.0

Create a virtualenv for metarace and associated packages:

	$ python3 -m venv --system-site-packages venv

Install packages with pip:

	$ ./venv/bin/pip install metarace

