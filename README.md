# metarace

A collection of Python modules to assist with cycle race timekeeping
and official result preparation. Version 2 of Metarace is a
re-write for Python 3, which removes static pyGTK/glib dependencies.

This package includes common shared elements that a metarace
application might require eg report, tod, decoder.
Unlike version 1, application-level modules are not contained in
the library, they are available separately as standalone projects.

## TODO

### riderdb: CSV Rider and Category list


## Module Overview

For details on module contents, methods and properties, use
pydoc:

	$ pydoc metarace.tod

### metarace: Base Library

Shared initialisation and resource management for applications.
Includes a tempfile context manager for updating files that
may be read while being updated.


### jsonconfig: Configuration File Wrapper

A thin wrapper on a dictionary-based configuration
with JSON export and import. The structure for a configuration
is a dictionary of sections, each of which contains a dictionary
of key/value pairs, where the key is a unicode string and the
value may be any base type supported by python & JSON. For example:

	"modulename": {
		"simpleoption": "string value",
		"complexoption": {
			"ordering": ["a","b","c"],
			"counter": 1023
		}
	}


### tod: Time of Day Object

Represent timing measurements and calculations for short intervals 
(<24 hours) and aggregates.


### timy: Alge Timy Chronometer

Read time of day measurements from an attached Alge Timy.


### decoder: Transponder Decoders

Standardised interfaces for transponder readers from Race Result
and Chronelec:

   - rrs : Race Result System Decoder (passive and active)
   - rru : Race Result USB Timing Box (active)
   - thbc : Chronelec (Tag Heuer) Protime/Elite RC and LS


### strops: Common String Manipulations

Commonly used functions for formatting competitor names,
rankings and user inputs. Example:

	>>> strops.lapstring(3)
	'3 Laps'
	>>> strops.riderlist_split('1+2  6-10, 22')
	['1', '2', '6', '7', '8', '9', '10', '22']


### telegraph: Interprocess Communication

MQTT backed message exchange service. 


### unt4: Legacy Timing Protocol

Swiss Timing UNT4 protocol wrapper, for legacy devices and DHI
communications.


### sender: Legacy DHI Scoreboard Interface

Thread object for drawing text on a
[Caprica](https://github.com/ndf-zz/caprica)
or Galactica DHI scoreboard over TCP, UDP and serial connections.


### gemini: Numeric LED Scoreboard Interface

Thread object for writing to a pair of Swiss Timing Gemini
numeric LED boards, and lap count displays.


### countback: Accumulate and Compare Count of Places

Represent a countback of places and allow for simple comparisons:

	>>> from metarace import countback
	>>> a=countback.countback('-,2')
	>>> b=countback.countback('-,1,1')
	>>> a>b
	True
	>>> a[3]+=1
	>>> b[1]+=1
	>>> a>b
	False
	>>> str(a)
	'-,2,-,1'
	>>> str(b)
	'-,2,1'
	>>> str(a+b)
	'-,4,1,1'


### htlib: HTML Generation

Functional primitives for HTML generation.

	>>> htlib.div(htlib.p(('Check the',
	...                    htlib.a('website', {'href':'#website'}),
	...                    'for more.')))
	'<div><p>Check the\n<a href="#website">website</a>\nfor more.</p></div>'


### report: Report Generation

Create sectioned reports and save to PDF, HTML, XLS and JSON.


### export: Result Export and Mirroring

Provides a means to execute a process on the host system, to
mirror result files to a remote server, or to run a script.


### eventdb: CSV Event List

Mainly for trackmeet, a CSV event listing object.


## Requirements

System requirements:

   - Cairo
   - Pango
   - PangoCairo
   - Rsvg
   - Python gi
   - Python gi cairo
   - tex-gyre fonts
   - mosquitto (optional)

Python packages:

   - pyserial: Serial port interface
   - python-dateutil: Generic date/time string parser
   - xlwt: XLS file writer
   - libscrc: 16 bit CRC for thbc
   - paho-mqtt: MQTT interface
   - importlib-resources: Package data files() interface (transitional)


## Installation

For a Debian-ish system, install the system requirements first:

	# apt-get install gir1.2-rsvg-2.0 gir1.2-pango-1.0 tex-gyre python3-cairo python3-gi python3-gi-cairo python3-pip

Then use pip3 to install metarace:

	$ pip3 install metarace


