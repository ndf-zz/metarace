## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

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
