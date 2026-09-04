## Purpose

Provide safe generated-output publication and explicit export controls for automation without embedding host scheduling policy in the application.

## Requirements

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

### Requirement: Emit a machine-readable run report
The system SHALL support `--report-file PATH` on import and export commands, writing a JSON report after the run completes (including warning-complete and hard-failed runs): command, format, started/finished timestamps (UTC), counts, warnings (code, message, detail), store provenance (source format, imported timestamp), `dry_run` marker on rehearsals, and exit status. Parent directories SHALL be created as needed; a report write failure SHALL warn, never fail the run.

#### Scenario: Report written on success
- **WHEN** a command completes with `--report-file` pointing at a writable path
- **THEN** the JSON report exists with counts and warnings matching stdout
- **AND** the command exit status is unchanged

#### Scenario: Report written on failure
- **WHEN** a command fails with `--report-file` set
- **THEN** the report records the true exit status with the error as a structured entry
- **AND** never claims success

#### Scenario: Report write failure degrades gracefully
- **WHEN** the report path is not writable
- **THEN** the command emits a structured warning
- **AND** the run result and exit status are unaffected

### Requirement: Trace store provenance into export summaries
The system SHALL record `source_format` and `imported_at` (UTC) in the store `meta` table on every wholesale rebuild, and surface both values in every export summary and run report. Read-mode opens of stores without provenance rows SHALL fail fast with a re-import directive; write-mode opens SHALL reset the disposable schema so the next import rebuilds in place.

#### Scenario: Export shows store origin
- **WHEN** export reads a store rebuilt by an M3U import
- **THEN** its summary includes the source format and import timestamp

#### Scenario: Provenance-less store opened for export
- **WHEN** an old store without provenance rows is opened read-only
- **THEN** export fails fast with a re-import directive

### Requirement: Warn on structurally empty imports
The system SHALL emit an `empty_import_source` warning when the import source is non-empty (files present) but yields zero playlists, so strict-mode automation trips on the silent-empty failure class.

#### Scenario: Non-empty dir imports nothing
- **WHEN** the import directory contains files but zero playlists are stored
- **THEN** the summary reports zero playlists plus an `empty_import_source` warning
- **AND** `--fail-on-warning` exits `2`

> Note: the M3U importer gates this warning on files being present (an empty directory stays silent-success). The NML importer warns whenever zero playlists import, since its single collection file is present by construction.
