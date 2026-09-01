## ADDED Requirements

### Requirement: Safely publish Engine database exports
The system SHALL stage Engine changes in a same-directory database copy, retain an adjacent backup of the validated prior target, close and validate the staged database before atomically replacing the target, and preserve the target's existing file mode.

#### Scenario: Successful Engine database publication
- **WHEN** managed playlist rebuilding and staged validation succeed while Engine DJ is offline
- **THEN** the complete staged database atomically replaces the configured target
- **AND** an adjacent backup of the prior database remains available
- **AND** no staging file remains

#### Scenario: Engine staging or validation fails
- **WHEN** copying, playlist rebuilding, or validation fails before publication
- **THEN** the configured target remains byte-for-byte unchanged
- **AND** the command fails without leaving a staging file

#### Scenario: Engine post-publication validation fails
- **WHEN** reopening the published database fails its required validation
- **THEN** the exporter restores the validated prior database from its backup through atomic replacement
- **AND** reports a structured failure

#### Scenario: Engine appears active
- **WHEN** Engine database sidecar state indicates a detectable active write or incomplete transaction
- **THEN** export fails before staging and instructs the operator to stop Engine DJ

### Requirement: Rehearse Engine export without mutating configured state
The system SHALL run Engine dry-run export against an isolated temporary database copy while opening the playlist store read-only.

#### Scenario: Dry-run Engine export
- **WHEN** the user runs `export --format engine --dry-run`
- **THEN** target validation, matching, managed rebuilding, and result reporting execute against the isolated copy
- **AND** the configured Engine database, retained backup, and store remain unchanged
