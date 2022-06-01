# metarace

A collection of Python libraries to assist cycle race timekeeping
and official result preparation. Version 2 of Metarace is a
re-write for Python 3, which removes static pyGTK/glib dependencies.

This library includes common shared elements that a metarace
application might require eg report, tod, decoder.
Unlike version 1, application-level modules are not contained in
the library, they are available separately as standalone projects.

## Progress

### metarace: Base Library

Shared initialisation and resource management for applications.
Includes a tempfile context manager for safely updating files that
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

### strops: Common String Manipulations

Commonly used functions for formatting competitor names,
rankings and procesing user inputs. Example:

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

Thread object for drawing text on a Caprica or Galactice DHI
scoreboard over TCP, UDP and serial connections.

## TODO

### countback: Aggregate and Compare Count of Places

### export: Result Export and Mirroring

### namebank: Rider Information Storage

### htlib: HTML Generation

### report: Report Generation

### decoder: Transponder Decoders

### timy: Alge Timy Chronometer

### gemini: Numeric Line Scoreboard Interface

## Requirements

   - paho-mqtt
   - importlib-resources


## Installation

	$ pip install metarace


