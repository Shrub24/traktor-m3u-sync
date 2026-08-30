## Purpose

Translate Traktor track paths (stored as `PRIMARYKEY` or split across `LOCATION` `VOLUME`/`DIR`/`FILE`) into M3U-side paths using configurable library roots.

## Requirements

### Requirement: Normalize native paths to library-relative identity
The system SHALL normalize each path-bearing import format into the shared library-relative POSIX track identity using only that format's configured root.

#### Scenario: M3U path normalization
- **WHEN** an M3U import path falls under `[m3u].library_root`
- **THEN** the importer stores the relative subpath as the track path

#### Scenario: NML path normalization
- **WHEN** an NML entry falls under `[nml].library_root`
- **THEN** the importer stores the relative subpath as the track path

### Requirement: Render native paths from library-relative identity
The system SHALL render each path-bearing export format from the stored relative path using only that format's configured root.

#### Scenario: M3U path rendering
- **WHEN** M3U export renders a stored path
- **THEN** it appends that path to `[m3u].library_root` without consulting NML configuration

#### Scenario: NML path rendering
- **WHEN** NML export renders a stored path
- **THEN** it appends that path to `[nml].library_root` without consulting M3U configuration
