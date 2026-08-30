## MODIFIED Requirements

### Requirement: Provide declarative NixOS service integration
The project SHALL expose a generic NixOS module that declaratively wires separate `export` and `import` oneshot service surfaces. The export format selection SHALL include every supported export format, while the import format selection SHALL include only supported source formats.

#### Scenario: Enable export service declaratively
- **WHEN** a NixOS configuration enables the export service surface
- **THEN** the module defines a oneshot systemd unit that invokes the packaged CLI export workflow
- **AND** allows the service to reference an overridable package output

#### Scenario: Enable iTunes export declaratively
- **WHEN** a NixOS configuration selects the itunes export format with required iTunes settings
- **THEN** the module renders the `[itunes]` TOML section and invokes `export --format itunes`
- **AND** validates `output_file` and absolute `location_base` before creating the unit

#### Scenario: Enable import service declaratively
- **WHEN** a NixOS configuration enables the import service surface
- **THEN** the module defines a oneshot systemd unit that invokes the packaged CLI import workflow
- **AND** keeps that service distinct from export rather than hiding both behaviors behind one combined abstraction
- **AND** rejects an unsupported import format at Nix evaluation time

### Requirement: Render declarative configuration to TOML
The deployment integration SHALL preserve TOML as the application contract and SHALL render declarative Nix configuration into TOML consumed by the CLI, including only the selected format's required path section.

#### Scenario: Module renders config for runtime use
- **WHEN** an operator configures the deployment module with supported workflow settings
- **THEN** the module renders those settings into a TOML configuration file for the CLI
- **AND** invokes the CLI with an explicit config path rather than bypassing the application’s config model

#### Scenario: Module renders iTunes config
- **WHEN** an operator configures iTunes export through the module
- **THEN** the rendered TOML contains `[itunes]` with `output_file` and `location_base`
- **AND** the config loads through the CLI's current format-specific validation

#### Scenario: Module uses external config file override
- **WHEN** an operator sets a module `configFile` override
- **THEN** the module invokes the CLI with that explicit TOML path
- **AND** does not require the same runtime workflow values to be re-declared through the generated-config option blocks

#### Scenario: Module omits an unselected NML root
- **WHEN** a module configuration selects M3U import and iTunes export only
- **THEN** it evaluates and renders without an NML library root
