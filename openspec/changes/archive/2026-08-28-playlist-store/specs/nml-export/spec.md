## REMOVED Requirements

### Requirement: Export playlists from collection.nml
**Reason**: Replaced by the store-mediated flow — the direct NML→M3U8 export no longer exists as a single command.
**Migration**: Run `import --format nml` to populate the store from `collection.nml`, then `export --format m3u` to render `.m3u8` output.

## ADDED Requirements

### Requirement: Import collection.nml into the store
The system SHALL populate the store from a `collection.nml` file by traversing the playlist tree and storing playlists and tracks under normalized track identity.

#### Scenario: Import standard playlists
- **WHEN** the user runs import with format nml and a readable `collection.nml`
- **THEN** the store contains one playlist per supported playlist with ordered track membership
- **AND** track entries carry library-relative identity translated from Traktor path forms

### Requirement: Export M3U8 playlists from the store
The system SHALL render UTF-8 `.m3u8` files from store state, one file per stored playlist.

#### Scenario: Export standard playlists
- **WHEN** the user runs export with format m3u against a store populated from `collection.nml`
- **THEN** the system writes one UTF-8 `.m3u8` file per stored playlist
- **AND** each file begins with a valid M3U header and ordered playlist entries

## MODIFIED Requirements

### Requirement: Skip unsupported smartlists with warnings
The system SHALL skip `SMARTLIST` nodes while importing `collection.nml` into the store and SHALL report their omission as structured warnings.

#### Scenario: Smartlist encountered during export
- **WHEN** the NML importer traverses a smartlist node
- **THEN** it does not store a playlist for that node
- **AND** it emits a structured warning entry and includes the skip in the final summary

### Requirement: Support config and CLI override inputs
The system SHALL load settings from format-based TOML configuration sections and SHALL allow CLI flags to override the fields each command uses.

#### Scenario: CLI overrides configured export paths
- **WHEN** configuration defines NML or M3U settings and the user also passes CLI values for the invoked command's fields (e.g. `collection_path` for NML import, `output_dir` for M3U export)
- **THEN** the invoked command uses the CLI-provided values
- **AND** retains the remaining configuration values unchanged

### Requirement: Validate configuration and surface errors
The system SHALL validate configuration at load time and SHALL surface missing files, missing required sections, and missing required fields as structured errors with non-zero exit codes.

#### Scenario: Config file not found
- **WHEN** the user runs any command with a config path that does not exist
- **THEN** the CLI exits with a non-zero code and emits a structured error to stderr

#### Scenario: Required table or field missing
- **WHEN** the config file is missing a required section (`[library]`, `[store]`, `[nml]`, `[m3u]`) or a required field for the invoked command
- **THEN** the CLI exits with a non-zero code and emits a structured error identifying the missing element
