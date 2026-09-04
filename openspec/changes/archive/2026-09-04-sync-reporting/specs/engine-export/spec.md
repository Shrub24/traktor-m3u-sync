## MODIFIED Requirements

### Requirement: Match only tracks already known to the target Engine database
The system SHALL match each store track's normalized library-relative path to an existing Engine `Track.path` using the configured Engine path prefix, which MAY be relative (`..`, `../library`) or absolute (`M:/library`), and SHALL NOT insert, delete, or modify Engine track or performance-data rows.

#### Scenario: Stored track matches one Engine track
- **WHEN** a stored relative path maps to exactly one Engine track path
- **THEN** playlist membership references that Engine track ID and the target database UUID

#### Scenario: Stored track is missing or ambiguous
- **WHEN** a stored track has no resolvable path, no matching Engine path, or more than one case-insensitive Engine path match
- **THEN** that membership is skipped with a structured warning
- **AND** other valid memberships continue exporting

#### Scenario: Absolute engine path prefix
- **WHEN** the configured prefix is an absolute consumer path and its join with a stored relative path equals an Engine track path
- **THEN** that membership matches exactly like a relative-prefix join

## ADDED Requirements

### Requirement: Warn on worker-absent Engine track files
The system SHALL support an optional Engine `check_base_path`: a worker-side local mount joined with each resolved store-relative path purely for `file_missing` warnings. The check SHALL never alter matching, Locations, or membership outcomes, and SHALL be omitted entirely when unconfigured.

#### Scenario: Track file absent on the worker mount
- **WHEN** Engine export configures `check_base_path` and the joined file does not exist
- **THEN** export emits a structured `file_missing` warning identifying the checked path
- **AND** the membership still exports when its Engine path matches

#### Scenario: No worker mount configured
- **WHEN** Engine export omits `check_base_path`
- **THEN** no filesystem existence check runs
- **AND** matching behavior is unchanged
