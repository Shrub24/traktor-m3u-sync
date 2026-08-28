## MODIFIED Requirements

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
