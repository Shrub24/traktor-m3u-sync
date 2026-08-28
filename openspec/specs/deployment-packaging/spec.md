## Purpose

Provide a Nix-native runtime package, flake app, declarative NixOS module integration, and TOML-rendering support for deploying `traktor-m3u-sync` without relying on the development shell.

## Requirements

### Requirement: Provide a Nix-native runtime package
The project SHALL expose a Nix-native runtime package for the `traktor-m3u-sync` CLI as a flake package output separate from the development shell.

#### Scenario: Build runtime package from the flake
- **WHEN** an operator builds the default package from the flake
- **THEN** the result contains the `traktor-m3u-sync` executable and its runtime dependencies
- **AND** does not depend on the development shell to run the application

### Requirement: Provide a flake app for direct execution
The project SHALL expose a flake app that runs the packaged CLI through `nix run`.

#### Scenario: Run packaged CLI through flake app
- **WHEN** an operator runs the default flake app
- **THEN** the system launches the packaged `traktor-m3u-sync` executable
- **AND** uses the same packaged runtime artifact exposed by the flake package output

### Requirement: Provide declarative NixOS service integration
The project SHALL expose a generic NixOS module that declaratively wires separate `export` and `import` oneshot service surfaces. The export format selection SHALL include every supported export format, while the import format selection SHALL include only supported source formats.

#### Scenario: Enable export service declaratively
- **WHEN** a NixOS configuration enables the export service surface
- **THEN** the module defines a oneshot systemd unit that invokes the packaged CLI export workflow
- **AND** allows the service to reference an overridable package output

#### Scenario: Enable iTunes export declaratively
- **WHEN** a NixOS configuration selects the itunes export format with required iTunes settings
- **THEN** the module renders the `[itunes]` TOML section and invokes `export --format itunes`
- **AND** validates `output_file` and absolute `base_path` before creating the unit

#### Scenario: Enable import service declaratively
- **WHEN** a NixOS configuration enables the import service surface
- **THEN** the module defines a oneshot systemd unit that invokes the packaged CLI import workflow
- **AND** keeps that service distinct from export rather than hiding both behaviors behind one combined abstraction
- **AND** rejects an unsupported import format at Nix evaluation time

### Requirement: Render declarative configuration to TOML
The deployment integration SHALL preserve TOML as the application contract and SHALL render declarative Nix configuration into TOML consumed by the CLI, including the selected format's required section.

#### Scenario: Module renders config for runtime use
- **WHEN** an operator configures the deployment module with supported library and workflow settings
- **THEN** the module renders those settings into a TOML configuration file for the CLI
- **AND** invokes the CLI with an explicit config path rather than bypassing the application’s config model

#### Scenario: Module renders iTunes config
- **WHEN** an operator configures iTunes export through the module
- **THEN** the rendered TOML contains `[itunes]` with `output_file` and `base_path`
- **AND** the config loads through the CLI's current format-specific validation

#### Scenario: Module uses external config file override
- **WHEN** an operator sets a module `configFile` override
- **THEN** the module invokes the CLI with that explicit TOML path
- **AND** does not require the same runtime workflow values to be re-declared through the generated-config option blocks

### Requirement: Keep orchestration policy out of the base deployment change
The base deployment packaging change SHALL provide package, app, and service/module seams without bundling host-specific orchestration policy.

#### Scenario: Downstream wants timers or path triggers
- **WHEN** a downstream environment needs timers, path units, Syncthing hooks, or ordering chains
- **THEN** the repository provides documentation or integration seams for attaching them
- **AND** does not hard-code those policies into the base deployment package or module behavior

### Requirement: Allow downstream service arguments
The NixOS module SHALL expose explicit import and export service argument options so downstream policy can opt into supported CLI operational flags without replacing the generated service command.

#### Scenario: Export service uses extra arguments
- **WHEN** an operator configures export service extra arguments including `--fail-on-warning`
- **THEN** the generated export oneshot appends those arguments after its explicit format and config arguments
- **AND** the module preserves its separate import/export service boundary

#### Scenario: Service arguments preserve external config paths
- **WHEN** an operator configures an external config file path containing spaces or percent characters with service extra arguments
- **THEN** the generated import or export command preserves that path as one config argument
- **AND** appends each extra argument without altering command argument boundaries
