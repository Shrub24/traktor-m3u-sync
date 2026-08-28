## Purpose

Bridge M3U libraries into Traktor: import UTF-8 `.m3u8` playlists into the playlist store, then rebuild a managed sandbox inside Traktor `collection.nml` from store state, preserving supported playlist hierarchy, membership, and ordering while protecting the underlying collection file.

## Requirements

### Requirement: Import M3U playlists into the store
The system SHALL populate the store from UTF-8 `.m3u8` files, capturing playlist names, folder hierarchy, membership, and ordering under normalized track identity.

#### Scenario: Import M3U input
- **WHEN** the user runs import with format m3u and an import directory containing supported `.m3u8` files
- **THEN** the store contains one playlist per supported file with ordered track membership
- **AND** track entries carry library-relative identity resolved from M3U paths

### Requirement: Rebuild managed sandbox from the store
The system SHALL rebuild the managed sandbox folder inside Traktor `collection.nml` from store state on each sandbox export run.

#### Scenario: Rebuild sandbox from store state
- **WHEN** the user runs export with format nml against a store populated from M3U input and a readable `collection.nml`
- **THEN** the system locates or creates the configured sandbox folder under `$ROOT`
- **AND** clears previously managed children inside that sandbox before rebuilding playlists from store state

### Requirement: Support nested and flat M3U directory layouts
The system SHALL capture hierarchy when `.m3u8` files are nested in directories and SHALL import flat directories without inferring additional hierarchy.

#### Scenario: Nested directory hierarchy preserved
- **WHEN** `.m3u8` files are organized in nested directories beneath the configured import directory
- **THEN** the store records matching nested folder paths for the imported playlists
- **AND** the sandbox export recreates the nested folder nodes under the sandbox in the same relative order

#### Scenario: Flat directory remains flat
- **WHEN** `.m3u8` files are provided in a flat import directory with no subdirectories
- **THEN** the store records the playlists directly under the sandbox root path
- **AND** no additional folder hierarchy is inferred from filenames alone

### Requirement: Match imported tracks to existing collection entries
The system SHALL only write sandbox playlist entries for store tracks that can be matched to existing Traktor collection tracks within the supported library mapping model.

#### Scenario: Track matches existing collection entry
- **WHEN** a store track can be reverse-mapped and resolved to a collection entry during sandbox export
- **THEN** the exporter creates a playlist entry referencing that collection track in the rebuilt sandbox playlist

#### Scenario: Track cannot be matched
- **WHEN** a store track cannot be resolved to any eligible collection entry
- **THEN** the exporter skips that track
- **AND** emits a structured warning rather than failing the entire export when other playlists remain exportable

### Requirement: Write playlist entries as collection references
The system SHALL write sandbox playlist membership using collection track references rather than duplicating non-playlist metadata into sandbox playlists.

#### Scenario: Imported playlist entry created
- **WHEN** the sandbox exporter adds a matched track to a sandbox playlist
- **THEN** it writes that playlist entry as a reference to the existing collection track using `PRIMARYKEY`
- **AND** does not attempt to synchronize unrelated metadata such as cues, grids, or analysis data

### Requirement: Protect collection.nml before and after mutation
The system SHALL create a backup of `collection.nml` before saving sandbox export changes and SHALL validate that the saved result can be reloaded successfully.

#### Scenario: Backup and reload validation succeed
- **WHEN** the sandbox exporter is ready to save a rebuilt sandbox state
- **THEN** it writes a backup copy of the original `collection.nml` before mutation
- **AND** reloads the saved file after write to confirm the result parses and contains the expected sandbox structure

### Requirement: Support import config and CLI overrides
The system SHALL load settings from format-based TOML configuration sections and SHALL allow CLI flags to override the fields each command uses.

#### Scenario: CLI overrides configured import values
- **WHEN** configuration defines M3U or NML settings and the user also passes CLI values for the invoked command's fields (e.g. `import_dir` for M3U import, sandbox export fields for NML export)
- **THEN** the invoked command uses the CLI-provided values
- **AND** retains the remaining configuration values unchanged

### Requirement: Emit structured import summaries
The system SHALL emit structured warnings and final summaries for both the M3U import and the sandbox export commands, suitable for operator review and later automation.

#### Scenario: Import completes with mixed results
- **WHEN** an M3U import or sandbox export completes after processing playlists with resolvable, unmatched, or skipped tracks
- **THEN** it emits structured warning entries for skipped or limited cases
- **AND** prints a final summary containing counts for playlists processed, tracks stored or matched, tracks skipped, and warnings emitted

### Requirement: Scope invertibility to supported playlist behavior
The system SHALL preserve supported playlist hierarchy, membership, and ordering across the store-mediated round trip, while treating unsupported metadata fidelity as out of scope.

#### Scenario: Supported round-trip succeeds
- **WHEN** a supported playlist set is imported from `collection.nml` into the store, exported to `.m3u8`, re-imported from those files, and exported back to a sandbox without external path changes
- **THEN** the resulting sandbox playlists reproduce the same supported hierarchy, track membership, and track ordering
- **AND** the system does not claim to reproduce unrelated NML metadata outside the supported playlist scope
