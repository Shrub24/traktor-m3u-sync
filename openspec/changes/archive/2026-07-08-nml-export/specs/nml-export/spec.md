## ADDED Requirements

### Requirement: Export playlists from collection.nml
The system SHALL export Traktor playlist state from a `collection.nml` file into UTF-8 `.m3u8` files.

#### Scenario: Export standard playlists
- **WHEN** the user runs the export workflow with a readable `collection.nml`
- **THEN** the system writes one UTF-8 `.m3u8` file per supported playlist
- **AND** each file begins with a valid M3U header and ordered playlist entries

### Requirement: Preserve playlist hierarchy during export
The system SHALL mirror the Traktor playlist folder hierarchy in the exported filesystem layout, excluding the synthetic `$ROOT` node.

#### Scenario: Omit $ROOT and preserve nested folders
- **WHEN** a playlist exists inside nested Traktor folder nodes beneath `$ROOT`
- **THEN** the exported `.m3u8` file is written under matching nested directories
- **AND** `$ROOT` does not appear as an output directory name

### Requirement: Skip unsupported smartlists with warnings
The system SHALL skip `SMARTLIST` nodes during export and SHALL report their omission as structured warnings.

#### Scenario: Smartlist encountered during export
- **WHEN** the exporter traverses a smartlist node
- **THEN** it does not write a `.m3u8` file for that node
- **AND** it emits a structured warning entry and includes the skip in the final summary

### Requirement: Support config and CLI override inputs
The system SHALL load export settings from TOML configuration and SHALL allow CLI flags to override export-specific workflow paths.

#### Scenario: CLI overrides configured export paths
- **WHEN** configuration defines export paths and the user also passes CLI values for `collection_path` or `output_dir`
- **THEN** the export workflow uses the CLI-provided values for those fields
- **AND** retains the remaining configuration values unchanged

### Requirement: Emit structured export summaries
The system SHALL emit structured operational output for warnings and final export summaries that can later be adapted into automated notification or recovery flows.

#### Scenario: Export completes with warnings
- **WHEN** the exporter completes after skipping unsupported or anomalous items
- **THEN** it emits warning entries in a structured stdout/stderr format
- **AND** it prints a final summary containing counts for playlists written, tracks exported, and warnings emitted
