## Purpose

Export store-mediated playlists into an existing Engine DJ 5.0 media database without changing Engine-owned tracks, analysis data, or unrelated playlists.

## ADDED Requirements

### Requirement: Validate an existing Engine DJ media database before export
The system SHALL require an existing Engine DJ media `m.db`, SHALL support schema version 3.0.2 in rollback-journal mode only, and SHALL fail before publication when the schema, journal mode, integrity, foreign-key state, or required playlist structures are incompatible.

#### Scenario: Compatible media database
- **WHEN** Engine export targets an existing schema 3.0.2 media database in rollback-journal mode whose integrity and required structures validate
- **THEN** the exporter may stage a managed playlist rebuild

#### Scenario: Incompatible or corrupt media database
- **WHEN** the target is absent, uses another schema version, uses WAL journal mode, fails an integrity or foreign-key check, or lacks required playlist structures
- **THEN** export fails with a structured error before replacing the target
- **AND** does not create a new Engine database or recreate Engine's schema

### Requirement: Match only tracks already known to the target Engine database
The system SHALL match each store track's normalized library-relative path to an existing Engine `Track.path` using the configured Engine path prefix and SHALL NOT insert, delete, or modify Engine track or performance-data rows.

#### Scenario: Stored track matches one Engine track
- **WHEN** a stored relative path maps to exactly one Engine track path
- **THEN** playlist membership references that Engine track ID and the target database UUID

#### Scenario: Stored track is missing or ambiguous
- **WHEN** a stored track has no resolvable path, no matching Engine path, or more than one case-insensitive Engine path match
- **THEN** that membership is skipped with a structured warning
- **AND** other valid memberships continue exporting

### Requirement: Rebuild one managed playlist subtree
The system SHALL replace exactly one configured top-level managed subtree with the store's playlist hierarchy, membership, and order while preserving every unrelated Engine playlist.

#### Scenario: Rebuild managed playlists
- **WHEN** export runs with a populated store and compatible target
- **THEN** the configured managed root contains one leaf for every stored playlist
- **AND** folders, sibling order, playlist membership, and track order match the store

#### Scenario: Repeated managed export
- **WHEN** export runs repeatedly against unchanged store state
- **THEN** exactly one managed root remains
- **AND** no stale managed playlists, orphaned entities, duplicate memberships, or broken linked-list successors remain

#### Scenario: Duplicate source membership
- **WHEN** one stored playlist repeats a track that Engine's native uniqueness constraint cannot represent
- **THEN** the first membership is retained in source order
- **AND** each later duplicate is skipped with a structured warning

#### Scenario: Unrelated Engine playlists exist
- **WHEN** the target contains playlists outside the configured managed root
- **THEN** their memberships, hierarchy, and relative ordering remain unchanged

### Requirement: Target one media-drive database in v1
The system SHALL mutate only the configured Engine media-drive database and SHALL NOT mirror playlist changes into a separate Engine main-library database.

#### Scenario: Main and media databases are separate
- **WHEN** an operator configures the M: media-drive `m.db` as the Engine export target while a separate L: main-library database exists
- **THEN** export writes only the configured media database
- **AND** leaves the main-library database unchanged

### Requirement: Report Engine export outcomes
The system SHALL emit the shared structured warning and result forms with counts for matched tracks, written playlists and memberships, and skipped missing, ambiguous, or duplicate memberships.

#### Scenario: Engine export completes with skips
- **WHEN** valid playlists are written but one or more memberships are skipped
- **THEN** export emits the completed counts and structured warnings
- **AND** the shared warning-sensitive exit behavior remains available
