## Purpose

Translate Traktor track paths (stored as `PRIMARYKEY` or split across `LOCATION` `VOLUME`/`DIR`/`FILE`) into M3U-side paths using configurable library roots.

## Requirements

### Requirement: Translate Traktor track paths for M3U export
The system SHALL translate Traktor track locations into M3U-side paths using one configured Traktor library root and one configured M3U library root.

#### Scenario: Translate from configured library roots
- **WHEN** a track path falls under the configured Traktor library root
- **THEN** the exporter rewrites that path so it falls under the configured M3U library root
- **AND** preserves the relative subpath beneath the library root

### Requirement: Prefer PRIMARYKEY over reconstructed LOCATION
The system SHALL use `PRIMARYKEY` as the preferred track path source when it is present and SHALL fall back to reconstructing a path from `LOCATION` when `PRIMARYKEY` is absent.

#### Scenario: PRIMARYKEY present
- **WHEN** a track entry contains a `PRIMARYKEY`
- **THEN** the exporter uses that value as the source path before applying library-root translation

#### Scenario: PRIMARYKEY absent
- **WHEN** a track entry lacks `PRIMARYKEY` but contains `LOCATION`
- **THEN** the exporter reconstructs the source path from `VOLUME`, `DIR`, and `FILE`
- **AND** uses the reconstructed path for library-root translation

### Requirement: Support relative M3U library roots
The system SHALL support both absolute and relative values for the configured M3U library root.

#### Scenario: Relative M3U library root configured
- **WHEN** the configured M3U library root is relative
- **THEN** exported playlist entries are written relative to the playlist output location according to that configured root behavior

### Requirement: Surface path translation anomalies
The system SHALL surface path translation failures or unmapped paths as structured warnings rather than failing the entire export when other playlists remain exportable.

#### Scenario: Track path cannot be translated cleanly
- **WHEN** a referenced track path cannot be mapped from the configured Traktor root into the configured M3U root
- **THEN** the exporter emits a structured warning for that track
- **AND** continues exporting other eligible tracks and playlists

### Requirement: Translate imported M3U paths back into Traktor library space
The system SHALL translate imported M3U track paths back into Traktor library space using the configured M3U library root and Traktor library root.

#### Scenario: Reverse-map a relative imported path
- **WHEN** an imported M3U track path falls beneath the configured relative or absolute M3U library root
- **THEN** the importer rewrites that path into the configured Traktor library root space
- **AND** preserves the relative subpath beneath the mapped roots

### Requirement: Resolve imported paths against collection entries deterministically
The system SHALL normalize reverse-mapped import paths so they can be matched deterministically against existing collection entries.

#### Scenario: Match against normalized collection path
- **WHEN** an imported path is reverse-mapped into Traktor library space
- **THEN** the importer normalizes that path into the Traktor-compatible path form used for collection lookup
- **AND** uses the normalized value when matching against collection references

### Requirement: Surface reverse translation anomalies
The system SHALL surface reverse path translation failures as structured warnings or errors according to whether the overall import can safely continue.

#### Scenario: Imported path cannot be reverse-mapped cleanly
- **WHEN** an imported track path cannot be mapped from the configured M3U root into the configured Traktor root
- **THEN** the importer reports the anomaly in structured output
- **AND** skips only the affected track when the rest of the import remains safe to continue
