## MODIFIED Requirements

### Requirement: Match only tracks already known to the target Engine database
The system SHALL match each store track's normalized library-relative path to an existing Engine `Track.path` using the configured Engine path prefix, which MAY be relative (`..`, `../library`) or absolute (`M:/library`). It SHALL NOT delete or modify existing Engine track, performance-data, or album-art rows.

#### Scenario: Stored track matches one Engine track
- **WHEN** a stored relative path maps to exactly one Engine track path
- **THEN** playlist membership references that Engine track ID and the target database UUID

#### Scenario: Stored track is missing or ambiguous
- **WHEN** a stored track has no resolvable path, or has more than one case-insensitive Engine path match, or matches no Engine path and cannot be inserted
- **THEN** that membership is skipped with a structured warning that names the Engine path in its original case
- **AND** other valid memberships continue exporting

#### Scenario: Absolute engine path prefix
- **WHEN** the configured prefix is an absolute consumer path and its join with a stored relative path equals an Engine track path
- **THEN** that membership matches exactly like a relative-prefix join

### Requirement: Warn on worker-absent Engine track files
The system SHALL support an optional Engine `check_base_path`: a worker-side local mount joined with each resolved store-relative path. It is used for `file_missing` warnings on matched tracks, and it is the source for track insertion. When `check_base_path` is unconfigured, the system SHALL run no filesystem check and insert nothing. Each unique checked path warns at most once per export.

#### Scenario: Track file absent on the worker mount
- **WHEN** Engine export configures `check_base_path` and the joined file of a matched track does not exist
- **THEN** export emits a structured `file_missing` warning identifying the checked path
- **AND** the membership still exports

#### Scenario: No worker mount configured
- **WHEN** Engine export omits `check_base_path`
- **THEN** no filesystem existence check runs
- **AND** stored tracks without an Engine match are skipped

### Requirement: Report Engine export outcomes
The system SHALL emit the shared structured warning and result forms. The counts SHALL cover matched tracks, inserted tracks, written playlists and memberships, and skipped missing, ambiguous, or duplicate memberships.

#### Scenario: Engine export completes with skips
- **WHEN** valid playlists are written but one or more memberships are skipped
- **THEN** export emits the completed counts and structured warnings
- **AND** the shared warning-sensitive exit behavior remains available

## ADDED Requirements

### Requirement: Insert unknown tracks visible to the worker
When `check_base_path` is configured, the system SHALL insert one unanalyzed Engine `Track` row for each stored track that matches no Engine path and whose joined file exists. The row SHALL carry the prefixed path in its original case and SHALL omit an explicit `id`, so that Engine's own triggers assign the origin and performance-data rows. The membership SHALL reference the new row in the same run.

#### Scenario: Unknown track file exists
- **WHEN** a stored track matches no Engine track and its file exists under `check_base_path`
- **THEN** export inserts one unanalyzed `Track` row and writes the membership
- **AND** reports it under `tracks_inserted`

#### Scenario: Unknown track file absent
- **WHEN** a stored track matches no Engine track and its file does not exist under `check_base_path`
- **THEN** no row is inserted and the membership is skipped with `track_missing`

#### Scenario: Repeated export after insertion
- **WHEN** export runs again with an unchanged store
- **THEN** the previously inserted rows are matched and no further rows are inserted

### Requirement: Link embedded album art for inserted tracks
For each inserted track whose file embeds a picture, the system SHALL set `albumArtId` to the `AlbumArt` row whose `hash` is the SHA-1 of the first embedded picture's bytes. If no such row exists, it SHALL insert one with that hash and a NULL blob. Tracks without embedded art SHALL keep a NULL `albumArtId`.

#### Scenario: Picture already known to Engine
- **WHEN** an inserted track's embedded picture hashes to an existing `AlbumArt` row
- **THEN** the track references that row and no `AlbumArt` row is added

#### Scenario: New picture
- **WHEN** inserted tracks embed a picture with no matching `AlbumArt` row
- **THEN** export inserts one `AlbumArt` row for that hash, and every such track references it
