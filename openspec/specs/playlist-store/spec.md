## Purpose

Provide the internal playlist model and a persistent, rebuildable SQLite store that stages imported playlist state between import and export runs.

## Requirements

### Requirement: Internal playlist model
The system SHALL represent playlists and tracks in a format-neutral internal model consisting of playlists with ordered track membership and tracks with library path, title, artist, album, and duration metadata.

#### Scenario: Model captures playlist state
- **WHEN** a source library is imported
- **THEN** the internal model represents each playlist with its name, folder path, and ordered track membership
- **AND** each track carries its library path and available title, artist, album, and duration metadata

### Requirement: Track identity normalization
The system SHALL identify tracks by a casefolded POSIX-normalized library-relative path, SHALL fall back to normalized artist and title for entries without a resolvable path, and SHALL flag unresolvable entries instead of dropping them.

#### Scenario: Same track from different path spellings
- **WHEN** two source entries reference the same library file with different path casing or separators
- **THEN** both entries resolve to a single track identity in the store
- **AND** the original path casing is preserved for rendering

#### Scenario: Ambiguous fallback identity
- **WHEN** multiple distinct tracks would collide on the artist-plus-title fallback identity
- **THEN** the system emits a structured warning and does not silently merge them

#### Scenario: Unresolvable track entry
- **WHEN** a track entry cannot be translated to a library-relative path or fallback identity
- **THEN** the entry is stored flagged as unresolved with its raw path
- **AND** it is excluded from identity dedup and handled by per-target warning policy

### Requirement: Persistent store between runs
The system SHALL persist imported playlist state to a SQLite database at the configured store path so that import and export run as independent processes, with a single source-of-truth default path constant.

#### Scenario: Export uses state from a prior import
- **WHEN** an import command has populated the store and a later export command runs
- **THEN** the export renders from the persisted store state without re-reading the import source

### Requirement: Wholesale rebuild on import
The system SHALL replace the entire store content on each import run rather than merging with previous store state.

#### Scenario: Re-import replaces previous state
- **WHEN** an import command runs against a store containing earlier state
- **THEN** the store contains only the state from the new import source when the command completes

### Requirement: Schema version fail-fast
The system SHALL version the store schema and SHALL fail with a structured error directing re-import when the store file's schema version does not match the current schema, instead of migrating.

#### Scenario: Store schema version mismatch
- **WHEN** a command opens a store file written with a different schema version
- **THEN** the command exits with a structured error identifying the version mismatch
- **AND** the error directs the user to re-run import to rebuild the store
