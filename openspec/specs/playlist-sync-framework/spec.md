## Purpose

Define the format adapter contract and the store-mediated import/export command surface that all format modalities implement.

## Requirements

### Requirement: Import command populates the store from a source format
The system SHALL provide an import command that accepts a format selector, reads the configured source for that format through the format's importer adapter, and rebuilds the store from it.

#### Scenario: Import from a supported format
- **WHEN** the user runs import with a supported format selector and valid configuration
- **THEN** the system reads the source through that format's importer and rebuilds the store
- **AND** emits a structured summary of playlists and tracks imported plus warnings

### Requirement: Export command renders only from the store
The system SHALL provide an export command that accepts a format selector and renders store state through that format's exporter adapter, without reading any import source directly.

#### Scenario: Export without a populated store
- **WHEN** the export command runs against an empty or uninitialized store
- **THEN** the command fails with a structured error directing the user to run an import first

#### Scenario: Export from a populated store
- **WHEN** the export command runs with a supported format selector after a successful import
- **THEN** the system renders store state through that format's exporter
- **AND** emits a structured summary of playlists written, tracks exported, and warnings

### Requirement: Format selection via flag
The system SHALL require an explicit format selector on import and export commands and SHALL reject unknown formats with a structured error.

#### Scenario: Unknown format requested
- **WHEN** the user passes an unsupported format selector
- **THEN** the command exits with a non-zero code and a structured error listing the failure

### Requirement: Uniform adapter contract
The system SHALL route all format reading and writing through importer and exporter adapters implementing a shared contract, including per-format path mapping to the internal track identity and uniform structured warning and summary types.

#### Scenario: Warnings are uniform across formats
- **WHEN** any importer or exporter adapter encounters an anomalous item
- **THEN** it emits a warning in the same structured form regardless of format

### Requirement: Format-based configuration sections
The system SHALL load settings from per-format configuration sections together with library root and store sections, and SHALL allow CLI flags to override the fields each command uses.

#### Scenario: CLI overrides configured values
- **WHEN** configuration defines format section values and the user also passes CLI overrides for the invoked command
- **THEN** the command uses the CLI-provided values and retains remaining configuration unchanged

#### Scenario: Missing required configuration
- **WHEN** the config file is missing a required section or field for the invoked command
- **THEN** the command exits with a non-zero code and a structured error identifying the missing element

#### Scenario: iTunes export configuration
- **WHEN** the user runs export with format itunes
- **THEN** the command loads its settings from the `[itunes]` configuration section
- **AND** the supported export formats include itunes alongside m3u and nml

### Requirement: Support explicit operational command controls
The system SHALL expose explicit command flags for operational behavior without changing the default import/export result contract.

#### Scenario: Operational flags are explicit
- **WHEN** an operator invokes an import or export command without operational flags
- **THEN** the command retains its existing result and exit behavior

#### Scenario: Warning-sensitive automation
- **WHEN** an operator invokes a command with `--fail-on-warning`
- **THEN** the command exposes warning completion through its documented distinct status
