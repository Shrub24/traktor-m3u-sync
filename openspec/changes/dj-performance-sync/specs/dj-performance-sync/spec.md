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

### Requirement: Build Engine USB generations

`usb build` SHALL stage a standalone Engine library for the selected playlist tree from a closed Engine database, as a native clone with the source's track IDs and origins, a device UUID kept across builds, and media at content-addressed paths. It SHALL publish the generation with a manifest of every file only after the staged database passes integrity checks, keep the previous generation until then, and never modify the source.

#### Scenario: Track without saved analysis
- **WHEN** a selected track has no saved beat grid
- **THEN** the build fails and the previously published generation stays current

#### Scenario: Rebuild without changes
- **WHEN** the library is rebuilt unchanged
- **THEN** every file other than the database keeps its path and content hash

### Requirement: Write Pioneer USB libraries from a snapshot

`pioneer-usb` SHALL write a Pioneer USB library for a snapshot's playlist tree, in its order, with each track's beat grid, key, main cue, hot cues and saved loops taken from the snapshot and only waveforms computed from the audio. Every beat of the grid SHALL be written, with beats whose index is divisible by 4 as downbeats. Comments SHALL NOT be exported; names in a comment's `/* a / b */` lists SHALL become My Tags. It SHALL fail when the written library does not verify.

#### Scenario: Half-time grid
- **WHEN** Engine's saved grid is half the displayed BPM
- **THEN** the Pioneer grid and BPM follow the saved grid

#### Scenario: Tagged comment
- **WHEN** a track's comment is `1A - Energy 6 /* Groove / Dub */`
- **THEN** the track carries My Tags `Groove` and `Dub` and no comment

#### Scenario: Folder holding tracks
- **WHEN** a playlist holds both tracks and playlists
- **THEN** the export fails, since a Pioneer folder cannot hold tracks

### Requirement: Export a rekordbox XML reference library

`usb rekordbox-xml` SHALL read the same closed Engine library and playlist selection as the USB build. It SHALL emit an ordered rekordbox playlist XML with consumer-side file URIs and Engine's saved key, grid, main cue, hot cues and loops. It SHALL NOT alter the playlist-store XML export.

#### Scenario: Grid starts before the audio
- **WHEN** Engine's first grid marker is before zero
- **THEN** XML anchors the grid at the first in-range beat with its saved tempo and beat-in-bar

### Requirement: Deliver USB generations over SFTP

`usb build` and `usb push` SHALL share one `[usb]` configuration and use all enabled formats unless narrowed by repeatable `--format`. Push SHALL use pinned SFTP and the stick's marker UUID to track changed files per format, installing databases last.

#### Scenario: Default format selection
- **WHEN** neither the configuration nor the command selects formats
- **THEN** both Engine and Pioneer are built or pushed to the same stick root

#### Scenario: Unknown database
- **WHEN** the stick holds a database not recognized by delivery state
- **THEN** push saves a copy and refuses replacement, unless the exact Engine database was reviewed

#### Scenario: First delivery preview
- **WHEN** push previews delivery to a stick without a marker
- **THEN** it treats the stick as having no delivery history and does not write a marker

#### Scenario: Repeat delivery
- **WHEN** the same generation is pushed again
- **THEN** nothing is sent

#### Scenario: Interrupted delivery
- **WHEN** Engine delivery stops before its database is installed
- **THEN** the stick keeps its previous working Engine library, and a retry reuses completed media

#### Scenario: Interrupted Pioneer database switch
- **WHEN** Pioneer delivery stops between database replacements
- **THEN** a retry recognizes the partially installed set and finishes delivery without treating those replacements as player edits

#### Scenario: Player edits
- **WHEN** a stick database was changed on the player, or delivery would overwrite edited Pioneer analysis
- **THEN** push keeps the edited file and refuses replacement, unless the exact Engine database was reviewed

### Requirement: Return player edits to Engine

`usb review` SHALL list where the stick differs from current Engine, by key, beat grid, main cue and each hot cue and loop slot, with an approval code bound to both databases. Approving SHALL write the stick's value of exactly those fields into Engine, keep Engine's other bytes, and let the next push replace that stick database.

#### Scenario: Hot cue added and grid moved on the player
- **WHEN** a hot cue was set in one slot and the grid moved on one track
- **THEN** the review lists exactly that slot and that grid, and approving it leaves other tracks and the unadjusted grid unchanged in Engine

#### Scenario: SQLite sidecars on the stick
- **WHEN** the stick database has an empty rollback journal but no WAL sidecars
- **THEN** review can read the database without removing the journal
- **AND** a nonempty rollback journal or any WAL sidecar blocks review and replacement

#### Scenario: Unmarked Engine stick
- **WHEN** an Engine stick has no delivery marker
- **THEN** review and approval work without writing to the stick, and approval reports the exact database hash for explicit first delivery

#### Scenario: Stale approval
- **WHEN** Engine or the stick changed after the review
- **THEN** approving fails and Engine is unchanged

### Requirement: Serialize performance snapshots

Snapshots SHALL serialize to versioned JSON and parse back to an equal snapshot. Parsing SHALL reject an unknown version or malformed content.

#### Scenario: Unknown version
- **WHEN** a snapshot file declares a version this build does not know
- **THEN** parsing fails
