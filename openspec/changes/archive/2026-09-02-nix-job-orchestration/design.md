## Context

The worker already accepts one command action, one format, and one TOML path per invocation. The NixOS module currently renders one shared TOML file and two singleton oneshots, while Engine export has added another independently schedulable consumer with an offline-only publication constraint. The store remains a wholesale-rebuilt cache, so orchestration must isolate independent import authorities rather than pretending they can merge into one database.

## Goals / Non-Goals

**Goals:**

- Keep the Python CLI unchanged and express multiplicity entirely through generated TOML files and systemd units.
- Make import-only, export-only, chained, and one-import-to-many-export deployments independently triggerable.
- Preserve Nix evaluation-time validation and the existing shared service identity.
- Deduplicate runner and service-policy configuration through systemd templates.

**Non-Goals:**

- Merging multiple imports into one state.
- Adding timers, path watches, consumer lifecycle hooks, or Engine DJ shutdown policy to the base module.
- Aggregating downstream job results into the initiating job's exit status.
- Cross-host job fan-out or a general workflow engine.
- Changing the CLI, store schema, adapter contracts, or Python configuration model.

## Decisions

### D1: Separate state domains from action jobs

`states.<name>` owns an explicit store path. `jobs.<name>` references one state and defines exactly one action (`import` or `export`), one compatible format, per-job adapter settings or an external config file, optional extra arguments, and `onSuccess` references.

This supports one imported snapshot feeding multiple consumers without forcing an import/export pair. A state permits at most one import job because every import replaces the entire snapshot; multiple imports would produce last-writer-wins behavior without merge semantics. Any number of export jobs may read the state.

Alternative rejected: a job as an import→export pipeline. That prevents independent path-triggered imports, consumer-startup exports, and fan-out.

### D2: Generate one effective TOML file per job

The module renders each generated job's state store path plus only the selected adapter's format settings into a TOML file consumed by the existing CLI. This keeps TOML as the application contract and requires no Python changes.

Format settings live under each job because multiple jobs may select the same format with different sources or targets. A job-level `configFile` remains an alternative to generated settings; when used, the external file owns the store and adapter configuration for that job.

Alternative rejected: one TOML per state. Jobs sharing a state may need different settings for the same format or different target instances, which one format table cannot represent.

### D3: Use two systemd templates with declared instance drop-ins

The module defines shared import and export templates containing the package command shape, shared `playlist-sync` identity, supplementary groups, oneshot behavior, and common service policy. Each declared job generates a template instance drop-in with its exact format, config path, extra arguments, and success fan-out.

This is an implementation detail; the stable user interface is `jobs.<name>`. Template instances remain ordinary systemd units with per-job status, cgroups, and journals, while avoiding duplicated runner definitions. Instances are known and validated at Nix evaluation time; arbitrary runtime instances are unsupported.

Alternative rejected: fully generated standalone service bodies. Safe but needlessly duplicates common unit content. Alternative rejected: targets as workflow runners. Targets do not carry configuration, sequence dependencies by themselves, or naturally rerun completed oneshots.

### D4: Use job names as declared systemd instance identities

Job option keys SHALL use a restricted systemd-safe identifier grammar rather than silently slugging arbitrary labels. The same deterministic mapping is used for generated instance names and `onSuccess` references. Human descriptions may preserve the original key.

This avoids ambiguous collisions and mismatched drop-in paths. The exact allowed grammar will be documented with the option.

### D5: Model fan-out with systemd success activation

A job's `onSuccess` list names other configured jobs. The module validates every reference, rejects self-reference and cycles, and renders explicit instance unit names into `OnSuccess=`. A successful standalone job with an empty list simply becomes inactive.

Fan-out is asynchronous: downstream failures are visible on their own units and do not retroactively fail the source job. This preserves composability. If aggregate workflow status becomes required, it will be a separate explicit workflow capability rather than overloaded fan-out semantics.

### D6: Preserve orchestration-policy boundaries

The module generates triggerable job instances and success links only. Timers, path units, consumer `Requires=`/`After=` links, and Engine DJ availability coordination remain downstream configuration. In particular, the module never schedules Engine export automatically merely because the format is configured.

### D7: Keep one module-wide Unix identity

Every job instance inherits the existing configurable `playlist-sync` user, group, and supplementary groups. Template instances do not create per-job Unix accounts. State directories and adapter targets remain operator-provisioned and permissioned.

### D8: Replace the singleton module surface

This change removes the provisional singleton `store`, `import`, `export`, and shared format options. Retaining both APIs would double assertion, rendering, and unit-generation paths while the module is still experimental. Existing deployments migrate to one state and two jobs for equivalent behavior.

## Risks / Trade-offs

- **[Success fan-out does not aggregate downstream failures]** → Document per-unit monitoring and reserve workflow services for a future demonstrated need.
- **[A success graph can loop indefinitely]** → Reject missing references, self-links, and graph cycles during Nix evaluation.
- **[Engine export can start while Engine DJ is open]** → Keep consumer lifecycle coordination downstream; the exporter fails its existing preflight and the Engine job enters failed state.
- **[Many configured jobs create many visible systemd instances]** → They are inactive oneshots sharing one Unix identity; templates deduplicate definitions while per-job journals improve observability.
- **[External config files can contradict their declared state]** → Treat the file as authoritative for that job and prohibit mixing it with generated state/adapter settings; document that state sharing cannot be verified inside external TOML.
- **[Breaking module migration]** → Provide a direct singleton-to-state/jobs migration example and keep the Python command contract unchanged.

## Migration Plan

1. Define one named state for the existing store.
2. Convert the current import surface into one import job referencing that state.
3. Convert each export surface into an independent export job referencing the same state.
4. Add `onSuccess` only where automatic fan-out is desired; otherwise attach existing downstream timers, path units, or consumer dependencies directly to job instances.
5. Rebuild NixOS and verify each instance independently before enabling success links.
6. Roll back by pinning the prior flake revision and restoring the singleton option block.
