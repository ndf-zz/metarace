## [Unreleased]

### Added

### Changed

### Deprecated

### Removed

### Fixed

### Security

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
