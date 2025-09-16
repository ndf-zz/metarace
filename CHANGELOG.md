## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

## [2.1.17] - 2025-09-16

### Added

   - add zebra lines to rmsrider report section
   - add Daktronic/Venus symbols to unt4 for track sender

### Changed

   - allow extra space for info col on a5 program reports
   - update installer to skip adding print admin group when not present
     on system

## [2.1.16] - 2025-08-12

### Added

   - include link to JSON report source in report body element

### Changed

   - initialise reload icon with ellipsis
   - increase width of cat column on judge section rows

### Removed

   - remove trace debug lines from report

### Fixed

   - use correct italic style class for report section prize line
   - use consistent italic style on all report section "info" columns

## [2.1.15] - 2025-07-23

### Added

   - add flush method to replace unsent function in telegraph
   - add speed method to tod with min and maxspeed guards

### Changed

   - limit rawspeed and speedstr values between 20 and 80 km/h
   - map STA trigger on RC decoder to C0, BOX to C1

### Removed

   - remove problematic unsent and on_publish methods from telegraph

### Fixed

   - include cls and indent options in set_will_json to match publish_json
   - restore event index workaround for single 'startlist' button

## [2.1.14] - 2025-07-20

### Added

   - override column alignment option on html table export
   - comet weather station value reader
   - include debug in report ouput

### Changed

   - add gstreamer-1 to installed debian packaged for ttstart
   - add user to lpadmin group for debian-like installs
   - use org.6_v.APP style application names for desktop files
   - adjust debian system packages installed with shell script

### Deprecated

   - use __version__ in place of VERSION

### Fixed

   - update links to install scripts for default branch main

## [2.1.13] - 2025-07-12

### Fixed

   - added missing confopt_posfloat method

## [2.1.12] - 2025-07-10

### Added

   - provide subtract and unary negate on countback objects
   - sort riderdb by (series, no)
   - add option to include series on rider resname_bib string
   - fetch rider or create new with bibstr
   - add laptime report section type

### Changed

   - truncate string version of countback when counts are zero
   - don't suppress exception from invalid countback string
   - use "ssssss:rrrr" for riderno sorting key instead of integer approach
   - suppress ValueError and TypeError in strops instead of Exception
   - truncate long names on ittt lane report section
   - adjust strops dnfcode ordering to match current use
   - adjust tod faketimes to match strops dnfcode ordering

### Removed

   - remove obsolete/unused python2 methods in countback
   - remove problematic len function from countback

### Fixed

   - fix missing category distance override column key

## [2.1.11] - 2025-07-04

### Added

   - Add method to change rider no in tod list

### Fixed

   - Correct handling of byes in sprint round/final startlists

### Security

   - Remove development venv from built package

## [2.1.10] - 2025-07-02

### Added

   - set/clear rider's primary category
   - retain most recent impulse from timy
   - add schema for teams and number series
   - add copy function to duplicate riderdb entry

### Changed

   - consider all series beginning with 't' as team
   - use standard BIB.str throughout riderdb

### Fixed

   - preserve ordering of categories on add/remove
   - handle race condition when publishing qos=0 messages to telegraph
   - fix typos in judge/laps report section
