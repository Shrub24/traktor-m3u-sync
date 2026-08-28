## Purpose

Provide safe generated-output publication and explicit export controls for automation without embedding host scheduling policy in the application.

## ADDED Requirements

### Requirement: Atomically publish generated export targets
The system SHALL publish M3U playlist files and iTunes XML output by atomically replacing each configured target only after a complete export file has been written successfully.

#### Scenario: Successful generated export replacement
- **WHEN** an M3U or iTunes export completes successfully for an existing target
- **THEN** the configured target is replaced with the complete new export
- **AND** no temporary export file remains at the target path

#### Scenario: Generated export write fails
- **WHEN** serialization or writing of an M3U or iTunes export fails before publication
- **THEN** the prior target remains unchanged
- **AND** the command fails without publishing a partial target

#### Scenario: Generated export retains target permissions
- **WHEN** an M3U or iTunes export replaces an existing target
- **THEN** the replacement retains the prior target's file mode
- **AND** a newly created target does not become owner-only solely because of temporary-file creation

### Requirement: Rehearse exports without mutating configured state
The system SHALL support `--dry-run` for every export format, validating and rendering against isolated temporary targets while leaving the configured output, NML collection, and store unchanged.

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

### Requirement: Opt into warning-sensitive command outcomes
The system SHALL support `--fail-on-warning` for import and export commands. It SHALL return status `2` after a command otherwise completes with warnings when the flag is set, while preserving status `0` for warning-complete commands when the flag is absent.

#### Scenario: Strict warning outcome
- **WHEN** a command completes and emits at least one warning with `--fail-on-warning`
- **THEN** it emits its normal summary and warnings
- **AND** exits with status `2`

#### Scenario: Compatible warning outcome
- **WHEN** a command completes with warnings without `--fail-on-warning`
- **THEN** it exits with status `0`
