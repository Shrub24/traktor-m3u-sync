## MODIFIED Requirements

### Requirement: Format-based configuration sections
The system SHALL load store settings together with format-owned configuration sections, and SHALL allow CLI flags to override the fields each selected command uses without requiring unrelated format settings.

#### Scenario: CLI overrides configured values
- **WHEN** configuration defines format section values and the user also passes CLI overrides for the invoked command
- **THEN** the command uses the CLI-provided values and retains remaining configuration unchanged

#### Scenario: Missing required configuration
- **WHEN** the config file is missing a required section or field for the invoked command
- **THEN** the command exits with a non-zero code and a structured error identifying the missing element

#### Scenario: iTunes export configuration
- **WHEN** the user runs export with format itunes
- **THEN** the command loads its settings from the `[itunes]` configuration section
- **AND** the supported export formats include itunes and engine alongside m3u and nml

#### Scenario: Engine export configuration
- **WHEN** the user runs export with format engine
- **THEN** the command loads `database_path`, `track_path_prefix`, and `managed_root` from the `[engine]` configuration section with any command-line overrides applied
- **AND** does not enable engine as an import format

#### Scenario: Unselected format configuration omitted
- **WHEN** a command does not select NML or Engine DJ
- **THEN** it does not require NML or Engine DJ path settings to load or run
