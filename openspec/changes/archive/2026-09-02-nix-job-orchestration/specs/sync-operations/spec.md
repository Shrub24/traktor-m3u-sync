## MODIFIED Requirements

### Requirement: Rehearse exports without mutating configured state
The system SHALL support `--dry-run` for every export format, including through generated NixOS export jobs, validating and rendering against isolated temporary targets while leaving the configured output, NML collection, and referenced state store unchanged.

#### Scenario: Dry-run export succeeds
- **WHEN** the user runs export with `--dry-run` and valid populated state
- **THEN** the command emits the normal counts and warnings for that export
- **AND** it does not alter the configured target or store

#### Scenario: Dry-run NML export
- **WHEN** the user runs NML export with `--dry-run`
- **THEN** any sandbox rebuild and validation occurs only on an isolated temporary collection copy
- **AND** the configured collection file remains byte-for-byte unchanged

#### Scenario: Dry-run with an absent store
- **WHEN** the user runs an export dry run against an absent or uninitialized configured store
- **THEN** the command fails without creating the store database or its parent directory

#### Scenario: Generated export job uses dry-run
- **WHEN** an operator adds `--dry-run` to a NixOS export job's extra arguments
- **THEN** that generated job rehearses its configured format using its referenced state
- **AND** preserves its configured target and state store

### Requirement: Opt into warning-sensitive command outcomes
The system SHALL support `--fail-on-warning` for import and export commands, including through generated NixOS jobs. It SHALL return status `2` after a command otherwise completes with warnings when the flag is set, while preserving status `0` for warning-complete commands when the flag is absent.

#### Scenario: Strict warning outcome
- **WHEN** a command completes and emits at least one warning with `--fail-on-warning`
- **THEN** it emits its normal summary and warnings
- **AND** exits with status `2`

#### Scenario: Compatible warning outcome
- **WHEN** a command completes with warnings without `--fail-on-warning`
- **THEN** it exits with status `0`

#### Scenario: Generated job opts into strict warnings
- **WHEN** a NixOS import or export job includes `--fail-on-warning` in its extra arguments
- **THEN** the generated job preserves that argument as a distinct command argument
- **AND** systemd records status `2` as a failed job rather than activating its success targets
