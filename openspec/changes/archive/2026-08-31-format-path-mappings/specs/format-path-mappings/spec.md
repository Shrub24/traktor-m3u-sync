## Purpose

Keep path conversion owned by the adapter that needs it and render consumer file URIs independently of the worker filesystem namespace.

## ADDED Requirements

### Requirement: Configure roots in their owning format section
The system SHALL configure NML and M3U library roots in `[nml]` and `[m3u]` respectively, and SHALL require a root only when the command selects that format.

#### Scenario: M3U-to-iTunes requires no NML root
- **WHEN** an operator imports M3U and exports iTunes with no NML configuration
- **THEN** both commands validate and run without requiring an NML library root

#### Scenario: NML command requires NML root
- **WHEN** an operator invokes an NML import or export without `[nml].library_root`
- **THEN** the command exits non-zero with a structured configuration error

### Requirement: Render consumer file URIs from a configured base
The system SHALL construct iTunes Locations by appending each library-relative path to required `[itunes].location_base`, a complete absolute `file:` URI, with UTF-8 percent encoding.

#### Scenario: Render Windows consumer location on a Linux worker
- **WHEN** `location_base` is `file://localhost/M:/Music` and a stored path is `House/01 Track.mp3`
- **THEN** the exported Location is `file://localhost/M:/Music/House/01%20Track.mp3`

#### Scenario: Preserve URI path encoding
- **WHEN** a stored path contains spaces, `#`, `%`, or non-ASCII characters
- **THEN** its rendered URI encodes those characters without encoding `/` separators or a Windows drive colon

### Requirement: Check local files independently of consumer locations
The system SHALL use optional `[itunes].check_base_path` only for local missing-file warnings and SHALL not derive Locations from it.

#### Scenario: Check path differs from consumer path
- **WHEN** `check_base_path` is `/srv/music` and `location_base` is `file://localhost/M:/Music`
- **THEN** local checks use `/srv/music` while exported Locations use `file://localhost/M:/Music`

#### Scenario: No check path configured
- **WHEN** no `check_base_path` is configured
- **THEN** the export completes without local file-existence warnings solely because the worker cannot inspect the consumer path
