## Purpose

Demonstrate that the internal playlist store can be transferred into an Engine DJ 5.0.0 database copy without adding a native library dependency.

## ADDED Requirements

### Requirement: Proof writes only an Engine database copy
The proof SHALL read the playlist store without modifying it and SHALL mutate only a caller-provided copy of an Engine-generated database.

#### Scenario: Run proof against copied databases
- **WHEN** the proof runs with a populated store and an Engine DJ database copy
- **THEN** the store remains unchanged
- **AND** only the supplied Engine database copy receives managed playlist rows

### Requirement: Proof rejects incompatible or corrupt Engine databases
The proof SHALL require Engine schema version 3.0.2 and successful SQLite integrity checks before writing.

#### Scenario: Unsupported Engine schema
- **WHEN** the target database does not report Engine schema 3.0.2
- **THEN** the proof fails before inserting or deleting data

### Requirement: Proof transfers ordered playlists
The proof SHALL match resolved store tracks to existing Engine media-drive track rows and SHALL create a managed playlist root preserving playlist names, hierarchy, membership, and track order.

#### Scenario: Successful store transfer
- **WHEN** the store contains ordered playlists with resolved tracks
- **THEN** the Engine database contains corresponding playlists referencing its existing track rows
- **AND** each playlist's `nextEntityId` chain resolves to its source track order
- **AND** all playlist entity database UUIDs match the target Engine database UUID

#### Scenario: Store track absent from Engine
- **WHEN** a store playlist references a track path absent from the Engine media database
- **THEN** the proof reports and skips that membership without inserting a track row

### Requirement: Proof validates its result
The proof SHALL perform the transfer in one SQLite transaction and SHALL validate integrity, references, hierarchy, and ordered membership before committing.

#### Scenario: Invalid generated state
- **WHEN** post-write validation detects a broken reference, hierarchy, order chain, or integrity error
- **THEN** the transaction rolls back without publishing the invalid state
