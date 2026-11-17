## ADDED Requirements

### Requirement: Export rekordbox XML from the store
The system SHALL render store state to a rekordbox "XML file format for playlists sharing" document (`DJ_PLAYLISTS` version `1.0.0`, with a `PRODUCT` element) at the configured output file. One export covers all stored playlists and their tracks, and the file is published atomically.

#### Scenario: Export from a populated store
- **WHEN** the user runs export with format rekordbox against a store populated by import
- **THEN** the system writes a `DJ_PLAYLISTS` document with a `COLLECTION` and a `PLAYLISTS` element
- **AND** `COLLECTION` `Entries` equals the number of `TRACK` children

### Requirement: Describe tracks in the collection
The system SHALL emit one collection `TRACK` per distinct resolvable store track. Each `TRACK` SHALL carry an integer `TrackID`, plus `Name`, `Artist` and `Location`, and SHALL include `Album` and `TotalTime` (in seconds) when the store has them. `Location` SHALL join the library-relative path to required `[rekordbox].location_base`, an absolute `file:` URI, with UTF-8 percent-encoding. TrackIDs SHALL be assigned in sorted identity order, so an unchanged store produces identical IDs.

#### Scenario: Location built from base path
- **WHEN** a stored track has library-relative path `House/01 Track.mp3` and `location_base` is `file://localhost/M:/Music`
- **THEN** its `Location` is `file://localhost/M:/Music/House/01%20Track.mp3`

#### Scenario: Unresolvable track skipped
- **WHEN** a stored track has no resolvable library-relative path
- **THEN** it is omitted from the collection and from every playlist
- **AND** a structured `track_unresolved` warning is emitted and counted

### Requirement: Mirror the playlist tree
The system SHALL place stored playlists under a `NODE` with `Type="0"` and `Name="ROOT"`. Each folder segment SHALL be a `Type="0"` node whose `Count` is its number of child nodes. Each playlist SHALL be a `Type="1"` node with `KeyType="0"`, an `Entries` count, and one `TRACK Key=<TrackID>` per resolvable membership, in stored order.

#### Scenario: Nested playlists
- **WHEN** stored playlists live under nested folder paths
- **THEN** each folder path appears once as a nested folder node holding its child folders and playlists in stored order

#### Scenario: Referential integrity
- **WHEN** any playlist is exported
- **THEN** every playlist `TRACK Key` equals the `TrackID` of a collection track in the same file

### Requirement: Warn on missing local files without blocking
The system SHALL check each collection track against optional `[rekordbox].check_base_path` and SHALL emit a `file_missing` warning for an absent file, without failing the export or omitting the track. Without a check base, no filesystem check SHALL run.

#### Scenario: Missing local file warned
- **WHEN** a configured check base joined with a track's relative path does not exist
- **THEN** a structured `file_missing` warning names the checked path and the track is still exported

### Requirement: Configure rekordbox export paths
The system SHALL load rekordbox export settings from `[rekordbox]` (`output_file`, required `location_base`, optional `check_base_path`). It SHALL require `output_file` and a valid `location_base` only when format rekordbox is selected, and SHALL apply the `--output-file`, `--location-base` and `--check-base-path` overrides to the selected format.

#### Scenario: Missing required rekordbox configuration
- **WHEN** export with format rekordbox lacks `output_file` or `location_base`
- **THEN** the CLI exits non-zero with a structured error naming the missing field and its `[rekordbox]` key

#### Scenario: Dry run
- **WHEN** export with format rekordbox runs with `--dry-run`
- **THEN** the exporter writes only into a temporary sandbox and the configured output file is untouched
