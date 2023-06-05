# metarace

A collection of Python modules to assist with cycle race timekeeping
and official result preparation. Version 2 of Metarace is a
re-write for Python 3 which removes static pyGTK/GLib dependencies.

Unlike version 1, application-level modules are not contained in
the library, they are available separately:

   - [roadmeet](https://github.com/ndf-zz/metarace-roadmeet) : Timing
     and results for UCI Part 2 Road Races, UCI Part 5 Cyclo-Cross,
     criterium, road handicap and ad-hoc time trial events.
   - [tagreg](https://github.com/ndf-zz/metarace-tagreg) : Transponder
     id management.
   - [ttstart](https://github.com/ndf-zz/metarace-ttstart) : Time
     Trial starter console.


## Module Overview

For details on module contents, methods and properties, use
pydoc:

	$ pydoc metarace.tod


### metarace: Base Library

   - shared configuration, default files and resources
   - tempfile-backed file writer
   - meet folder locking


### jsonconfig: Configuration File Wrapper

A thin wrapper on a dictionary-based configuration
with JSON export and import.


### riderdb: CSV-backed Competitor Information

Store details for competitors, teams, and categories.


### tod: Time of Day

Represent timing measurements and calculations for
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


### sender: Legacy DHI Scoreboard Interface

Thread object for drawing text on a
[Caprica](https://github.com/ndf-zz/caprica)
or Galactica DHI scoreboard over TCP,
UDP and serial connections.


### gemini: Numeric LED Scoreboard Interface

Thread object for writing to a pair of Swiss Timing Gemini
numeric LED boards, and lap count displays.


### countback: Accumulate and Compare Count of Places

Represent a countback of places and allow for simple
placing comparisons.


### htlib: HTML Generation

Functional primitives for HTML generation.


### report: Report Generation

Create sectioned reports and save to PDF, HTML, XLS and JSON.


### export: Result Export and Mirroring

Execute a process on the host system, to
mirror result files to a remote server,
or to run a script.


### eventdb: CSV Event List

Store details for events within a meet.


## Requirements

System requirements:

   - Cairo
   - Pango
   - PangoCairo
   - Rsvg
   - Python gi
   - Python gi cairo
   - tex-gyre (fonts)
   - mosquitto (optional)
   - evince (optional)
   - libreoffice (optional)

Python packages:

   - pyserial: Serial port interface
   - python-dateutil: Generic date/time string parser
   - xlwt: XLS file writer
   - libscrc: 16 bit CRC for thbc
   - paho-mqtt: MQTT interface
   - importlib-resources: Package data files() interface (transitional)


## Installation

Install system requirements Cairo, Pango, Rsvg,
Tex-Gyre and optionally Mosquitto, then use pip
to install metarace.


### Debian (11+)

	$ sudo apt-get install gir1.2-rsvg-2.0 gir1.2-pango-1.0 tex-gyre python3-cairo python3-gi python3-gi-cairo python3-pip mosquitto evince
	$ pip install metarace
