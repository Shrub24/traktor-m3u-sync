## Why

The NixOS module currently exposes one singleton import service, one singleton export service, and one shared store. That surface cannot represent independent import-only and export-only triggers, one-import-to-many-export fan-out, or multiple isolated playlist-state domains without duplicating the module.

## What Changes

- **BREAKING**: Replace the singleton `store`, `import`, `export`, and shared format-configuration surface with declarative `states.<name>` and `jobs.<name>` options.
- Define each state as one independently rebuildable SQLite snapshot with an explicit store path.
- Define each job as exactly one import or export action, referencing one state and one supported format.
- Allow zero or one import job and any number of export jobs per state; reject multiple imports targeting one state.
- Allow a job to trigger zero or more named jobs after successful completion, supporting standalone actions, linear chains, and one-import-to-many-export fan-out.
- Generate two shared systemd template units and Nix-declared instance drop-ins so every configured job remains independently triggerable and observable without duplicating runner configuration.
- Keep timers, path units, consumer startup dependencies, and Engine DJ availability coordination as downstream systemd policy.
- Retain one module-wide `playlist-sync` Unix service identity for every generated job instance.

## Capabilities

### New Capabilities

- `nix-job-orchestration`: Named state domains, independently triggerable import/export jobs, success fan-out, and generated systemd template instances.

### Modified Capabilities

- `deployment-packaging`: Replace the singleton import/export NixOS module contract with state/job orchestration while retaining package, config rendering, identity, and format validation guarantees.
- `sync-operations`: Apply dry-run, warning-status, and systemd argument-escaping controls per generated job.

## Impact

- Primary implementation: `nix/modules/traktor-m3u-sync.nix` and the flake's module-evaluation check.
- Documentation: `docs/nix-deployment.md`, `ARCHITECTURE.md`, and `PLAN.md`.
- No Python API or runtime dependency changes are required: each job invokes the existing CLI with a generated TOML file containing its referenced state store and selected adapter settings.
- Existing NixOS deployments using singleton `import`/`export` options must migrate to `states` and `jobs`.
