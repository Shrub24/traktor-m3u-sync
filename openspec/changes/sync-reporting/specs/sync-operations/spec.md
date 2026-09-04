## ADDED Requirements

### Requirement: Emit a machine-readable run report
The system SHALL support `--report-file PATH` on import and export commands,
writing a JSON report after the run completes (including on warning-complete
runs): command, format, started/finished timestamps (UTC), counts, warnings
(code, message, detail), store provenance (source format, imported timestamp),
and exit status. Parent directories SHALL be created as needed; a report write
failure SHALL warn, never fail the run.

#### Scenario: Report written on success
- **WHEN** a command completes with `--report-file` pointing at a writable path
- **THEN** the JSON report exists with counts and warnings matching stdout
- **AND** the command exit status is unchanged

#### Scenario: Report write failure degrades gracefully
- **WHEN** the report path is not writable
- **THEN** the command emits a structured warning
- **AND** the run result and exit status are unaffected

### Requirement: Trace store provenance into export summaries
The system SHALL record `source_format` and `imported_at` (UTC) in the store
`meta` table on every wholesale rebuild, reject stores whose provenance rows
are absent the same way as a schema mismatch (fail fast, re-import), and
surface both values in every export summary and run report.

#### Scenario: Export shows store origin
- **WHEN** export reads a store rebuilt by an M3U import
- **THEN** its summary includes the source format and import timestamp

#### Scenario: Provenance survived a schema change
- **WHEN** an old store without provenance rows is opened
- **THEN** export and import fail fast with a re-import directive

### Requirement: Warn on structurally empty imports
The system SHALL emit an `empty_import_source` warning when the import source
is non-empty (files present) but yields zero playlists, so strict-mode
automation trips on the silent-empty failure class.

#### Scenario: Non-empty dir imports nothing
- **WHEN** the import directory contains files but zero playlists are stored
- **THEN** the summary reports zero playlists plus an `empty_import_source`
warning
- **AND** `--fail-on-warning` exits `2`

> Note: the M3U importer gates this warning on files being present (an empty
> directory stays silent-success). The NML importer warns whenever zero
> playlists import, since its single collection file is present by
> construction.
