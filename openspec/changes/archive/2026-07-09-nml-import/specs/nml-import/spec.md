## ADDED Requirements

### Requirement: Import M3U playlists into a managed sandbox
The system SHALL import UTF-8 `.m3u8` playlists into a managed sandbox folder inside Traktor `collection.nml` and SHALL rebuild that sandbox from current M3U state on each import run.

#### Scenario: Rebuild sandbox from current import input
- **WHEN** the user runs the import workflow with a readable `collection.nml` and an import directory containing supported `.m3u8` files
- **THEN** the system locates or creates the configured sandbox folder under `$ROOT`
- **AND** clears previously managed children inside that sandbox before rebuilding playlists from the import input

### Requirement: Support nested and flat M3U directory layouts
The system SHALL preserve hierarchy when `.m3u8` files are nested in directories and SHALL import flat directories without inferring additional hierarchy.

#### Scenario: Nested directory hierarchy preserved
- **WHEN** `.m3u8` files are organized in nested directories beneath the configured import directory
- **THEN** the importer recreates matching nested folder nodes under the sandbox
- **AND** writes playlists into the corresponding nested folders in the same relative order

#### Scenario: Flat directory remains flat
- **WHEN** `.m3u8` files are provided in a flat import directory with no subdirectories
- **THEN** the importer creates playlists directly under the sandbox root
- **AND** does not infer additional folder hierarchy from filenames alone

### Requirement: Match imported tracks to existing collection entries
The system SHALL only import playlist entries that can be matched to existing Traktor collection tracks within the supported library mapping model.

#### Scenario: Track matches existing collection entry
- **WHEN** an imported M3U track path can be reverse-mapped and resolved to a collection entry
- **THEN** the importer creates a playlist entry referencing that collection track in the rebuilt sandbox playlist

#### Scenario: Track cannot be matched
- **WHEN** an imported M3U track path cannot be resolved to any eligible collection entry
- **THEN** the importer skips that track
- **AND** emits a structured warning rather than failing the entire import when other playlists remain importable

### Requirement: Write playlist entries as collection references
The system SHALL write imported playlist membership using collection track references rather than duplicating non-playlist metadata into sandbox playlists.

#### Scenario: Imported playlist entry created
- **WHEN** the importer adds a matched track to a sandbox playlist
- **THEN** it writes that playlist entry as a reference to the existing collection track using `PRIMARYKEY`
- **AND** does not attempt to synchronize unrelated metadata such as cues, grids, or analysis data

### Requirement: Protect collection.nml before and after mutation
The system SHALL create a backup of `collection.nml` before saving changes and SHALL validate that the saved result can be reloaded successfully.

#### Scenario: Backup and reload validation succeed
- **WHEN** the importer is ready to save a rebuilt sandbox state
- **THEN** it writes a backup copy of the original `collection.nml` before mutation
- **AND** reloads the saved file after write to confirm the result parses and contains the expected sandbox structure

### Requirement: Support import config and CLI overrides
The system SHALL load import settings from TOML configuration and SHALL allow CLI flags to override import-specific workflow paths and sandbox settings.

#### Scenario: CLI overrides configured import values
- **WHEN** configuration defines import values and the user also passes CLI values for import workflow fields
- **THEN** the import workflow uses the CLI-provided values for those fields
- **AND** retains the remaining configuration values unchanged

### Requirement: Emit structured import summaries
The system SHALL emit structured warnings and a final import summary suitable for operator review and later automation.

#### Scenario: Import completes with mixed results
- **WHEN** the importer completes after matching some tracks and skipping others
- **THEN** it emits structured warning entries for skipped or limited cases
- **AND** prints a final summary containing counts for playlists processed, tracks matched, tracks skipped, and warnings emitted

### Requirement: Scope invertibility to supported playlist behavior
The system SHALL preserve supported playlist hierarchy, membership, and ordering across an export-to-import round-trip, while treating unsupported metadata fidelity as out of scope.

#### Scenario: Supported round-trip succeeds
- **WHEN** a supported playlist set is exported to `.m3u8` and then re-imported without external path changes
- **THEN** the resulting sandbox playlists reproduce the same supported hierarchy, track membership, and track ordering
- **AND** the system does not claim to reproduce unrelated NML metadata outside the supported playlist scope
