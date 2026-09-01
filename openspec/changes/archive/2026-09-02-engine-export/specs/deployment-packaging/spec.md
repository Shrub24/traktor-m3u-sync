## ADDED Requirements

### Requirement: Expose Engine DJ export declaratively
The NixOS module SHALL support Engine DJ on the export service only and SHALL render selected Engine settings into the same TOML contract consumed by the CLI.

#### Scenario: Enable Engine export declaratively
- **WHEN** a NixOS configuration selects engine export with a media database path, track path prefix, and managed-root name
- **THEN** the module renders an `[engine]` TOML section
- **AND** invokes `export --format engine` through the packaged CLI

#### Scenario: Reject Engine import declaratively
- **WHEN** an operator attempts to select engine as the import format
- **THEN** Nix evaluation rejects the unsupported format

#### Scenario: Generated Engine service configuration
- **WHEN** the module generates Engine configuration rather than using `configFile`
- **THEN** it validates the required Engine fields at evaluation time
- **AND** does not create, chown, or grant access to the configured database path
