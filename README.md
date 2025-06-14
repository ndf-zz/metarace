# metarace

A collection of Python modules to assist with cycle race timekeeping
and official result preparation. Version 2 of Metarace is a
re-write for Python 3 which removes static pyGTK/GLib dependencies.

Application-level modules are not contained in
the library, they are available separately:

   - [roadmeet](https://github.com/ndf-zz/metarace-roadmeet) : Timing
     and results for UCI Part 2 Road Races, UCI Part 5 Cyclo-Cross,
     criterium, road handicap and ad-hoc time trial events.
   - [trackmeet](https://github.com/ndf-zz/metarace-trackmeet) : Timing
     and results for UCI Part 3 Track Races.
   - [tagreg](https://github.com/ndf-zz/metarace-tagreg) : Transponder
     registration tool.
   - [ttstart](https://github.com/ndf-zz/metarace-ttstart) : Time
     Trial starter console.

A shared install script may be used to install metarace
applications on most POSIX systems:

	$ wget https://github.com/ndf-zz/metarace/raw/refs/heads/master/metarace-install.sh
	$ sh metarace-install.sh

For installation on Windows systems, a powershell script is provided
to install metarace applications under a WSL Debian container:

	wget https://github.com/ndf-zz/metarace/raw/refs/heads/master/wsl-install.ps1


## Support

   - Signal Group: [metarace](https://signal.group/#CjQKII2j2E7Zxn7dHgsazfKlrIXfhjgZOUB3OUFhzKyb-p_bEhBehsI65MhGABZaJeJ-tMZl)
   - Github Issues: [issues](https://github.com/ndf-zz/metarace-roadmeet/issues)


## Module Overview

Use pydoc to read module-specific documentation.


### metarace: Base Library

   - shared configuration, default files and resources
   - tempfile-backed file writer
   - meet folder locking


### jsonconfig: Configuration Options

Schema defined dictionary-like
configuration with JSON export and import.


### riderdb: CSV-backed Competitor Information

Store details for competitors, teams, and categories.


### tod: Time of Day

Represent timing measurements, calculations for
short intervals (<24 hours) and aggregate times.


### timy: Alge Timy Chronometer

Read time of day measurements from an attached Alge Timy
in PC-TIMER mode.


### decoder: Transponder Decoders

Read transponder and timing information from
Race Result and Chronelec devices:

   - rrs : Race Result System Decoder (passive and active)
   - rru : Race Result USB Timing Box (active)
   - thbc : Chronelec (Tag Heuer) Protime/Elite RC and LS


### strops: Common String Manipulations

Commonly used functions for formatting competitor names,
rankings and user inputs.


### telegraph: Interprocess Communication

MQTT-backed pub/sub message exchange service.


### unt4: Legacy Timing Protocol

Swiss Timing UNT4 protocol wrapper, for legacy devices
and DHI communications.


### countback: Accumulate and Compare Count of Places

Represent a countback of places and allow for simple
placing comparisons.


### htlib: HTML Generation

Functional primitives for HTML generation.


### report: Report Generation

Create sectioned reports and save to PDF, HTML, XLS and JSON.


### export: Result Export and Mirroring

Mirror export files to a remote host using rsync over ssh,
rsync TCP daemon or by running a local script.


## Work in Progress

   - submit file archive service
   - update text vertical layout from font metrics
   - overhaul report sections and event index for trackmeet
   - re-write report library
   - module documentation
   - sample scripts


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

   - pyserial: Serial port interface
   - python-dateutil: Generic date/time string parser
   - xlsxwriter: XLSX file writer
   - paho-mqtt: MQTT interface
   - graphemeu: Unicode grapheme support


## Manual Installation

Install system requirements with apt:

	$ sudo apt install python3-venv python3-pip python3-cairo python3-gi python3-gi-cairo gir1.2-rsvg-2.0 gir1.2-pango-1.0

Create a virtualenv for metarace and associated packages:

	$ python3 -m venv --system-site-packages venv

Install packages with pip:

	$ ./venv/bin/pip install metarace

