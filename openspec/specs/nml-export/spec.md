## Purpose

Bridge Traktor playlist state into M3U libraries: import `collection.nml` into the playlist store, then render UTF-8 `.m3u8` files from store state, preserving folder hierarchy and surfacing unsupported items as structured warnings.

## Requirements

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

### Requirement: Preserve playlist hierarchy during export
The system SHALL mirror the Traktor playlist folder hierarchy in the exported filesystem layout, excluding the synthetic `$ROOT` node.

#### Scenario: Omit $ROOT and preserve nested folders
- **WHEN** a playlist exists inside nested Traktor folder nodes beneath `$ROOT`
- **THEN** the exported `.m3u8` file is written under matching nested directories
- **AND** `$ROOT` does not appear as an output directory name

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

### Requirement: Emit structured export summaries
The system SHALL emit structured operational output for warnings and final export summaries that can later be adapted into automated notification or recovery flows.

#### Scenario: Export completes with warnings
- **WHEN** the exporter completes after skipping unsupported or anomalous items
- **THEN** it emits warning entries in a structured stdout/stderr format
- **AND** it prints a final summary containing counts for playlists written, tracks exported, and warnings emitted

### Requirement: Validate configuration and surface errors
The system SHALL validate configuration at load time and SHALL surface missing files, missing required sections, and missing required fields as structured errors with non-zero exit codes.

#### Scenario: Config file not found
- **WHEN** the user runs any command with a config path that does not exist
- **THEN** the CLI exits with a non-zero code and emits a structured error to stderr

#### Scenario: Required table or field missing
- **WHEN** the config file is missing a required section (`[library]`, `[store]`, `[nml]`, `[m3u]`) or a required field for the invoked command
- **THEN** the CLI exits with a non-zero code and emits a structured error identifying the missing element

### Requirement: Provide an example configuration template
The repository SHALL include a committed example configuration file that documents all supported config fields with inline comments.

#### Scenario: Developer needs a config starting point
- **WHEN** a developer wants to create a local config file
- **THEN** they can copy the example template and adjust paths for their setup
- **AND** the local config file is excluded from version control via `.gitignore`
