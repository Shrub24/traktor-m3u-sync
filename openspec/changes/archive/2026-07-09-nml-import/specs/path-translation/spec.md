## ADDED Requirements

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
