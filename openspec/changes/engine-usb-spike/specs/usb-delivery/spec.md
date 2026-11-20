## ADDED Requirements

### Requirement: Deliver a staged USB generation over SFTP

Delivery SHALL check a stick marker, use a pinned SSH host key, and compare content manifests independently of timestamps. It SHALL back up the current database and publish the new database only after its assets are present. It SHALL NOT delete media or replace assets referenced by the installed generation.

#### Scenario: Deliver a library update
- **WHEN** a new export adds or changes media
- **THEN** unchanged assets are skipped and new assets are installed before the database

#### Scenario: Interrupted transfer
- **WHEN** transfer fails before database publication
- **THEN** the installed database and its assets remain intact

#### Scenario: Unrecognized database
- **WHEN** a device database differs from a recorded delivery
- **THEN** delivery saves a local copy and refuses replacement unless the operator explicitly approves that exact snapshot against its installed baseline

### Requirement: Review and bring back Engine player edits

Review SHALL compare each matching track's cue, loop and adjusted grid data against the exported baseline and the current Engine library. It SHALL match source identity by origin database UUID and track ID. Write-back SHALL require explicit approval of the reviewed changes, preserve unrelated fields, and back up the source before publication. Engine SHALL be closed during write-back.

#### Scenario: Independent edits
- **WHEN** the player and source edit different performance fields
- **THEN** applying the reviewed changes brings back only the player-edited fields

#### Scenario: Conflicting edits
- **WHEN** both sides changed the same performance field differently
- **THEN** review reports a conflict and applying leaves the source value alone unless USB precedence was explicitly selected during review

#### Scenario: Source changes after review
- **WHEN** the proposed changes no longer match the approved review
- **THEN** write-back refuses publication
