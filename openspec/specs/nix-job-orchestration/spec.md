# nix-job-orchestration Specification

## Purpose
Define declarative NixOS state domains and independently triggerable import/export jobs that compose safely through explicit success fan-out.

## Requirements

### Requirement: Declare isolated playlist states
The NixOS module SHALL expose named states, each backed by one explicit writable store path, and SHALL keep independent state snapshots isolated.

#### Scenario: Configure two state domains
- **WHEN** an operator declares two states with distinct store paths
- **THEN** jobs referencing each state receive that state's store path
- **AND** imports into one state do not replace the other state's snapshot

#### Scenario: Reject duplicate store ownership
- **WHEN** two states declare the same store path
- **THEN** Nix evaluation rejects the configuration

### Requirement: Declare independently triggerable action jobs
The NixOS module SHALL expose named jobs where each job performs exactly one import or export action against one declared state and one action-compatible format.

#### Scenario: Configure an import-only job
- **WHEN** an operator declares an import job with no success targets
- **THEN** the module exposes an independently triggerable import oneshot
- **AND** successful completion does not automatically start an export

#### Scenario: Configure an export-only job
- **WHEN** an operator declares an export job referencing a populated state
- **THEN** the module exposes an independently triggerable export oneshot
- **AND** the job does not refresh the state before exporting

#### Scenario: Reject an incompatible action format
- **WHEN** a job selects a format unsupported for its action, including Engine DJ import
- **THEN** Nix evaluation rejects the configuration

### Requirement: Enforce one import authority per state
The NixOS module SHALL permit at most one import job to reference a state and SHALL permit multiple export jobs to read that state.

#### Scenario: Fan one importer out to multiple consumers
- **WHEN** one import job and multiple export jobs reference the same state
- **THEN** Nix evaluation accepts the configuration
- **AND** every export reads the snapshot produced for that state

#### Scenario: Reject multiple imports into one state
- **WHEN** more than one import job references the same state
- **THEN** Nix evaluation rejects the configuration before units are generated

### Requirement: Trigger configured jobs after successful completion
A job SHALL allow zero or more configured jobs to be named as success targets, and the module SHALL validate the resulting local success graph. A job SHALL also allow a symmetric `onFailure` list rendered as systemd `OnFailure=`, validated the same way.

#### Scenario: One import triggers multiple exports
- **WHEN** an import job names two export jobs in `onSuccess`
- **THEN** successful import completion activates both export jobs
- **AND** either export remains independently triggerable

#### Scenario: Failed source job does not fan out
- **WHEN** a source job exits unsuccessfully
- **THEN** none of its configured success targets are activated

#### Scenario: Reject invalid success graph
- **WHEN** a job names a missing target, itself, or participates in a success cycle
- **THEN** Nix evaluation rejects the configuration

#### Scenario: Failure fan-out triggers
- **WHEN** a job lists `onFailure` targets and the instance fails
- **THEN** systemd activates the listed units
- **AND** invalid references fail at Nix evaluation like `onSuccess`

#### Scenario: Downstream failure remains independent
- **WHEN** a success target starts and then fails
- **THEN** that target reports failure through its own systemd unit
- **AND** the already-completed source job's result is not changed

### Requirement: Keep job instances observable under one service identity
Every configured job SHALL have a stable systemd unit identity and SHALL inherit the module-wide service user, group, and supplementary groups.

#### Scenario: Inspect one job
- **WHEN** an operator queries one configured job through systemd or the journal
- **THEN** its status and logs are addressable independently by its generated unit name
- **AND** it runs as the shared configured service account rather than a per-job Unix user

### Requirement: Leave external triggers composable
The module SHALL expose job units as trigger seams without creating timers, path units, application lifecycle hooks, or implicit Engine DJ scheduling.

#### Scenario: Attach a downstream path trigger
- **WHEN** downstream configuration attaches a systemd path unit to an import job
- **THEN** the path unit can start that job directly
- **AND** the base module does not impose another trigger

#### Scenario: Export before a consumer starts
- **WHEN** downstream configuration orders a consumer after an export job
- **THEN** the consumer can require that export independently of any import job
