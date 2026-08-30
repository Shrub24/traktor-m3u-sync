## REMOVED Requirements

### Requirement: Translate Traktor track paths for M3U export
**Reason**: Store-mediated adapters no longer translate directly between NML and M3U roots.
**Migration**: Use the NML and M3U adapter roots to normalize or render the shared library-relative identity.

### Requirement: Prefer PRIMARYKEY over reconstructed LOCATION
**Reason**: This NML-specific behavior moves under adapter-owned normalization.
**Migration**: Rely on the NML adapter's configured library root and path-normalization contract.

### Requirement: Support relative M3U library roots
**Reason**: M3U rendering is now an adapter-owned mapping concern.
**Migration**: Configure `[m3u].library_root` with the required absolute or relative M3U form.

### Requirement: Surface path translation anomalies
**Reason**: Pairwise translation is removed in favor of adapter-specific normalization warnings.
**Migration**: Inspect structured warnings emitted by the selected adapter.

### Requirement: Translate imported M3U paths back into Traktor library space
**Reason**: M3U import produces format-neutral relative identity rather than Traktor paths.
**Migration**: Use NML export only when rendering that relative identity into NML space.

### Requirement: Resolve imported paths against collection entries deterministically
**Reason**: Collection matching is NML-adapter behavior, not generic M3U path translation.
**Migration**: Use the NML adapter's library-root normalization when importing or exporting NML.

### Requirement: Surface reverse translation anomalies
**Reason**: Pairwise reverse mapping is removed.
**Migration**: Handle structured warnings from the selected adapter.

## ADDED Requirements

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
