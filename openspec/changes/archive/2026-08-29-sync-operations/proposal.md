## Why

The completed format pipeline is ready for downstream automation, but generated M3U and iTunes files are overwritten directly, no export can be rehearsed without writing, and warnings are invisible to callers unless they parse logs. Harden the job primitives before adding scheduling or report formats.

## What Changes

- Write M3U and iTunes export targets atomically from a same-directory temporary file, preserving the old complete target until replacement succeeds.
- Add export-only `--dry-run` preflight: validate configuration and store state, render and summarize results, but never alter a target (including an NML sandbox).
- Add opt-in `--fail-on-warning`, producing a distinct non-zero status after a completed command emits warnings; default behavior remains compatible.
- Expose explicit per-service NixOS `extraArgs` so downstream systemd policy can opt into the operational flags.
- Document the operational flags and downstream-systemd usage boundary.

## Capabilities

### New Capabilities
- `sync-operations`: safe generated-output writes and explicit automation controls for export jobs.

### Modified Capabilities
- `playlist-sync-framework`: export command behavior gains dry-run and opt-in warning failure semantics.
- `deployment-packaging`: NixOS oneshots gain an explicit argument override seam.

## Impact

- **Code**: CLI, service orchestration, shared result handling, M3U/iTunes exporters, and tests.
- **CLI**: adds `--dry-run` and `--fail-on-warning`; existing invocations retain their current success behavior by default.
- **Dependencies**: none; atomic replacement uses the Python standard library.
- **Operations**: downstream systemd services can opt into warning-sensitive outcomes without introducing timers, chains, or a combined worker.
- **NixOS module**: export and import services gain documented `extraArgs` options.
- **Deferred**: JSON report artifacts, import dry-run, backup retention policy, scheduler/path-unit wiring, and Engine DJ DB integration.
