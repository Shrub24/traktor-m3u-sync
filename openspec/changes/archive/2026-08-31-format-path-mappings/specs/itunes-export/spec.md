## MODIFIED Requirements

### Requirement: Build absolute track locations from the configured base path
The system SHALL construct each track's Location by joining the track's library-relative path to required `[itunes].location_base`, an absolute `file:` URI, percent-encoded per URL rules, and SHALL write Total Time in milliseconds.

#### Scenario: Location built from base path
- **WHEN** a stored track has library-relative path `House/01 Track.mp3` and `location_base` is `file://localhost/M:/Music`
- **THEN** the exported Location is `file://localhost/M:/Music/House/01%20Track.mp3`
- **AND** Total Time equals the stored duration in seconds multiplied by 1000

#### Scenario: Unresolvable track skipped
- **WHEN** a stored track has no resolvable library-relative path
- **THEN** it is omitted from Tracks and from all playlist item references
- **AND** a structured warning is emitted and counted

### Requirement: Warn on missing local files without blocking
The system SHALL check generated relative paths against optional `[itunes].check_base_path`, SHALL report missing local files as structured warnings included in the export summary, and SHALL NOT fail the export because of missing files.

#### Scenario: Missing local file warned
- **WHEN** a configured check base joined with a generated relative path does not exist on the worker filesystem at export time
- **THEN** a structured warning naming the track path is emitted
- **AND** the export completes with the track included and the warning counted in the summary

#### Scenario: Local checking is not configured
- **WHEN** no check base is configured
- **THEN** the export does not attempt worker filesystem existence checks
- **AND** still renders Locations from `location_base`

### Requirement: Configure iTunes export paths
The system SHALL load iTunes export settings from `[itunes]` (`output_file`, required `location_base`, optional `check_base_path`), SHALL require the selected command's required fields, and SHALL allow matching CLI overrides.

#### Scenario: CLI overrides configured iTunes paths
- **WHEN** configuration defines `[itunes]` values and the user also passes CLI values
- **THEN** the export uses the CLI-provided values and retains remaining configuration unchanged

#### Scenario: Missing required iTunes configuration
- **WHEN** the config file lacks required `output_file` or `location_base` for the invoked command
- **THEN** the CLI exits non-zero with a structured error identifying the missing element
