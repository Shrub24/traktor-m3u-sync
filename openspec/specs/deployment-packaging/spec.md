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

### Requirement: Run services under a dedicated non-root identity
The NixOS module SHALL run the import and export oneshot services under a configurable user and group whose default is a dedicated `playlist-sync` system account that the module creates automatically.

#### Scenario: Default service identity
- **WHEN** a NixOS configuration enables either traktor-m3u-sync service without setting `user` or `group`
- **THEN** the module declares a `playlist-sync` system user and group with no login shell
- **AND** both generated units set `User=` and `Group=` to that account

#### Scenario: Operator-managed identity override
- **WHEN** an operator points both `user` and `group` at a non-default account
- **THEN** the generated units run as that identity
- **AND** the module does not create a conflicting account

#### Scenario: Shared media group access
- **WHEN** an operator configures one or more supplementary groups
- **THEN** both generated units add those groups through `SupplementaryGroups=`
- **AND** the module does not hard-code a site-specific group

#### Scenario: Generated config uses a writable explicit store
- **WHEN** the generated module config runs under a non-root identity
- **THEN** evaluation requires an explicit `store.path`
- **AND** the service does not fall back to a home-relative path under `/var/empty`

#### Scenario: Explicit root escape hatch
- **WHEN** an operator sets `user = null`
- **THEN** the module does not create the dedicated account or group
- **AND** the generated units omit `User=` and `Group=`

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
