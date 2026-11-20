## ADDED Requirements

### Requirement: Capture Engine performance data

The system SHALL capture a performance snapshot from a closed Engine 3.0.2 database. The snapshot SHALL identify each track by its Engine origin database UUID and origin track ID, and SHALL carry its key, adjusted beat grid, main cue, hot cues and saved loops in seconds. It SHALL record the library UUID and the SHA-256 of the exact database bytes it read, and SHALL NOT modify the database.

#### Scenario: Analyzed track
- **WHEN** a track has saved analysis with a hot cue and a saved loop
- **THEN** the snapshot carries its key, grid, main cue, that hot cue in its slot and that loop in its slot

#### Scenario: Unanalyzed track
- **WHEN** a track has no saved performance data
- **THEN** the snapshot carries it with no grid, cues or loops

#### Scenario: Database is in use
- **WHEN** the database has an active journal or write-ahead log
- **THEN** capture fails without reading it

### Requirement: Preserve Engine performance blobs

Decoding and re-encoding an Engine `beatData`, `quickCues` or `loops` blob SHALL reproduce it byte for byte, including fields the performance model does not represent.

#### Scenario: Unmodelled fields
- **WHEN** a blob carries a default grid, main-cue flags or trailing bytes
- **THEN** re-encoding it reproduces those bytes unchanged

### Requirement: Serialize performance snapshots

Snapshots SHALL serialize to versioned JSON and parse back to an equal snapshot. Parsing SHALL reject an unknown version or malformed content.

#### Scenario: Unknown version
- **WHEN** a snapshot file declares a version this build does not know
- **THEN** parsing fails
