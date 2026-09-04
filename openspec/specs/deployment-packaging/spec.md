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
The project SHALL expose a generic NixOS module that declaratively wires named state domains to independently triggerable import and export jobs. Export jobs SHALL support every registered export format, while import jobs SHALL include only registered source formats.

#### Scenario: Enable export service declaratively
- **WHEN** a NixOS configuration declares an export job
- **THEN** the module defines a oneshot systemd template instance that invokes the packaged CLI export workflow
- **AND** allows the job to reference an overridable package output

#### Scenario: Enable iTunes export declaratively
- **WHEN** a NixOS job selects the itunes export format with required iTunes settings
- **THEN** the module renders the `[itunes]` TOML section and invokes `export --format itunes`
- **AND** validates `output_file` and absolute `location_base` before creating the instance

#### Scenario: Enable import service declaratively
- **WHEN** a NixOS configuration declares an import job
- **THEN** the module defines a oneshot systemd template instance that invokes the packaged CLI import workflow
- **AND** keeps that action distinct from export rather than hiding both behaviors behind one command
- **AND** rejects an unsupported import format at Nix evaluation time

### Requirement: Render declarative configuration to TOML
The deployment integration SHALL preserve TOML as the application contract and SHALL render one effective configuration per generated job, containing its referenced store and selected format's required path section.

#### Scenario: Module renders config for runtime use
- **WHEN** an operator configures a job with generated settings
- **THEN** the module renders those settings and the referenced state's store path into a TOML configuration file for the CLI
- **AND** invokes the CLI with that explicit config path rather than bypassing the application's config model

#### Scenario: Module renders iTunes config
- **WHEN** an operator configures an iTunes export job
- **THEN** that job's rendered TOML contains `[itunes]` with `output_file` and `location_base`
- **AND** the config loads through the CLI's current format-specific validation

#### Scenario: Module uses external config file override
- **WHEN** an operator sets a job-level `configFile` override
- **THEN** that job invokes the CLI with the explicit TOML path
- **AND** does not require the same runtime values to be re-declared through generated state and format settings

#### Scenario: Module omits an unselected NML root
- **WHEN** a job selects M3U import or iTunes export without NML
- **THEN** its configuration evaluates and renders without an NML library root

### Requirement: Keep orchestration policy out of the base deployment change
The base deployment module SHALL expose independently triggerable job instances and optional local success links without bundling host-specific trigger or consumer-lifecycle policy.

#### Scenario: Downstream wants timers or path triggers
- **WHEN** a downstream environment needs timers, path units, Syncthing hooks, or consumer ordering
- **THEN** the repository provides documented job-unit seams for attaching them
- **AND** does not hard-code those trigger policies into the module

### Requirement: Allow downstream service arguments
The NixOS module SHALL expose explicit per-job argument options so downstream policy can opt into supported CLI operational flags without replacing the generated job command.

#### Scenario: Export service uses extra arguments
- **WHEN** an operator configures an export job with extra arguments including `--fail-on-warning`
- **THEN** the generated export instance appends those arguments after its explicit format and config arguments
- **AND** preserves the independent job boundary

#### Scenario: Service arguments preserve external config paths
- **WHEN** a job uses an external config path containing spaces or percent characters with extra arguments
- **THEN** the generated import or export command preserves that path as one config argument
- **AND** appends each extra argument without altering command argument boundaries

### Requirement: Run services under a dedicated non-root identity
The NixOS module SHALL run every generated import and export job under a configurable user and group whose default is a dedicated `playlist-sync` system account that the module creates automatically.

#### Scenario: Default service identity
- **WHEN** a NixOS configuration enables at least one job without setting `user` or `group`
- **THEN** the module declares a `playlist-sync` system user and group with no login shell
- **AND** both systemd templates set `User=` and `Group=` to that account

#### Scenario: Operator-managed identity override
- **WHEN** an operator points both `user` and `group` at a non-default account
- **THEN** every generated job runs as that identity
- **AND** the module does not create a conflicting account

#### Scenario: Shared media group access
- **WHEN** an operator configures one or more supplementary groups
- **THEN** both systemd templates add those groups through `SupplementaryGroups=`
- **AND** the module does not hard-code a site-specific group

#### Scenario: Generated config uses a writable explicit store
- **WHEN** a generated job runs under a non-root identity
- **THEN** its referenced state requires an explicit store path
- **AND** the service does not fall back to a home-relative path under `/var/empty`

#### Scenario: Explicit root escape hatch
- **WHEN** an operator sets `user = null`
- **THEN** the module does not create the dedicated account or group
- **AND** both systemd templates omit `User=` and `Group=`

### Requirement: Expose Engine DJ export declaratively
The NixOS module SHALL support Engine DJ for export jobs only and SHALL render selected Engine settings into the TOML contract consumed by the CLI.

#### Scenario: Enable Engine export declaratively
- **WHEN** an export job selects engine with a media database path, track path prefix, and managed-root name
- **THEN** the module renders an `[engine]` TOML section for that job
- **AND** invokes `export --format engine` through the packaged CLI

#### Scenario: Reject Engine import declaratively
- **WHEN** an operator attempts to select engine for an import job
- **THEN** Nix evaluation rejects the unsupported format

#### Scenario: Generated Engine service configuration
- **WHEN** the module generates Engine job configuration rather than using `configFile`
- **THEN** it validates the required Engine fields at evaluation time
- **AND** does not create, chown, schedule, or grant access to the configured database path

### Requirement: Render per-job report file arguments
The NixOS module SHALL support an optional per-job `reportFile` rendered as a `--report-file` argument pair on the generated instance command, preserving argument boundaries for paths containing spaces.

#### Scenario: Job persists its run report
- **WHEN** a job sets `reportFile`
- **THEN** the instance command carries `--report-file` with that path as one argument
- **AND** jobs without `reportFile` carry no such argument
