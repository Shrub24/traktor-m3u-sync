## Purpose

Export stored playlist state to an iTunes-compatible XML plist consumable by DJ software (Engine DJ primarily), with stable identifiers, absolute track locations, mirrored folder hierarchy, and guaranteed playlist referential integrity.

## Requirements

### Requirement: Export iTunes XML from the store
The system SHALL render store state to an iTunes Music Library-compatible XML plist at the configured output file, one export covering all stored playlists and their tracks.

#### Scenario: Export from a populated store
- **WHEN** the user runs export with format itunes against a store populated by import
- **THEN** the system writes an XML plist containing a Tracks dictionary and a Playlists array
- **AND** each stored playlist appears with its tracks in stored order

### Requirement: Build absolute track locations from the configured base path
The system SHALL construct each track's Location by joining the track's library-relative path to required `[itunes].location_base`, an absolute `file:` URI, percent-encoded per URL rules, and SHALL write Total Time in milliseconds.

#### Scenario: Location built from base path
- **WHEN** a stored track has library-relative path `House/01 Track.mp3` and `location_base` is `file://localhost/M:/Music`
- **THEN** the exported Location is `file://localhost/M:/Music/House/01%20Track.mp3`
- **AND** Total Time equals the stored duration in seconds multiplied by 1000

#### Scenario: Unresolvable track skipped
- **WHEN** a stored track has no resolvable library-relative path
- **THEN** it is omitted from Tracks and from all playlist item references
- **AND** a structured warning is emitted and counted

### Requirement: Generate stable identifiers
The system SHALL generate Track IDs as integers and Persistent IDs as uppercase 16-hex strings derived deterministically from track and playlist identity, so repeated exports of unchanged store state produce the same identifiers.

#### Scenario: Identifiers stable across exports
- **WHEN** the same store state is exported twice
- **THEN** every track and playlist carries identical Track IDs and Persistent IDs in both outputs

#### Scenario: Outer keys match inner values
- **WHEN** the Tracks dictionary is written
- **THEN** each outer dictionary key is the string form of that track's integer Track ID
- **AND** every playlist item reference equals the Track ID integer of an entry present in Tracks

### Requirement: Mirror playlist folder hierarchy
The system SHALL represent stored playlist folder paths as iTunes folder playlists, with folder entries marked as folders and child playlists and subfolders referencing their parent folder's Persistent ID.

#### Scenario: Nested playlists mirror stored hierarchy
- **WHEN** stored playlists live under nested folder paths
- **THEN** the export contains folder playlist entries for each folder segment
- **AND** each child playlist or subfolder carries the parent folder's Persistent ID

#### Scenario: Root-level playlists
- **WHEN** a stored playlist has no folder path
- **THEN** its playlist entry appears at the top level without a parent reference

### Requirement: Preserve referential integrity and omit smart playlists
The system SHALL only emit playlist item references to tracks present in the Tracks dictionary and SHALL never emit smart playlist fields or smart playlist entries.

#### Scenario: Referential integrity holds
- **WHEN** any playlist is exported
- **THEN** every item reference resolves to a track entry in the same file

#### Scenario: Smart playlists not emitted
- **WHEN** the export is generated
- **THEN** no Smart Info or Smart Criteria fields appear anywhere in the output

### Requirement: Warn on missing local files without blocking
The system SHALL check generated relative paths against optional `[itunes].check_base_path`, SHALL report missing local files as structured warnings included in the export summary, and SHALL NOT fail the export because of missing files.

#### Scenario: Missing local file warned
- **WHEN** a configured check base joined with a generated relative path does not exist on the worker filesystem at export time
- **THEN** a structured warning naming the track path is emitted
- **AND** the export completes with the track included and the warning counted in the summary

#### Scenario: Local checking is not configured
- **WHEN** no check base is configured
- **THEN** the export does not attempt worker filesystem existence checks
- **AND** still renders Locations from `location_base`

### Requirement: Configure iTunes export paths
The system SHALL load iTunes export settings from `[itunes]` (`output_file`, required `location_base`, optional `check_base_path`), SHALL require the selected command's required fields, and SHALL allow matching CLI overrides.

#### Scenario: CLI overrides configured iTunes paths
- **WHEN** configuration defines `[itunes]` values and the user also passes CLI values
- **THEN** the export uses the CLI-provided values and retains remaining configuration unchanged

#### Scenario: Missing required iTunes configuration
- **WHEN** the config file lacks required `output_file` or `location_base` for the invoked command
- **THEN** the CLI exits non-zero with a structured error identifying the missing element
