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
     id management.
   - [ttstart](https://github.com/ndf-zz/metarace-ttstart) : Time
     Trial starter console.


## Work in Progress

   - submit file archive service
   - update text vertical layout from font metrics
   - overhaul report sections and event index for trackmeet
   - re-write report library
   - remove html templates
   - bootstrap update to new vers
   - new result structure for analysis with links instead of direct content
   - add js utils for in-page reports
   - replace xls export with xlsx
   - module documentation
   - sample scripts


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
   - xlwt: XLS file writer
   - paho-mqtt: MQTT interface
   - ugrapheme: Unicode grapheme support


## Installation

Check that your python version is at least 3.11 before installing.
This library will not work with python versions less than 3.11.


### Debian 12

Install system requirements with apt:

	$ sudo apt install python3-venv python3-pip python3-cairo python3-gi python3-gi-cairo
	$ sudo apt install gir1.2-rsvg-2.0 gir1.2-pango-1.0
	$ sudo apt install python3-serial python3-paho-mqtt python3-dateutil python3-xlwt

Optionally add fonts, PDF viewer and MQTT broker:

	$ sudo apt install tex-gyre fonts-noto evince mosquitto

Create a virtualenv for metarace and associated packages:

	$ python3 -m venv --system-site-packages venv

Install packages with pip:

	$ ./venv/bin/pip install metarace

