# Proposal: engine-analysis-lifecycle

## Why

Tracks the Engine exporter inserts stay unanalyzed until Engine DJ opens and analyzes them.
Automating that in a downstream deployment needs two pieces that depend on Engine itself
rather than on any one host: how to tell from the database that the analysis has been saved
(observed on Engine 5.0 while Engine is still open), and a Windows-side task that starts and
cleanly closes Engine on request. Both belong with the Engine adapter. VM boot and shutdown,
dialog handling for a specific guest, and triggers stay downstream.

## What

- `traktor-m3u-sync engine-analysis` prints JSON mapping each track in the managed Engine
  subtree to whether its analysis (`isAnalyzed` and a saved beat grid) is saved. It is
  read-only, safe while Engine holds the database, takes the same `--engine-database` and
  `--engine-managed-root` flags as the export, and exits 75 when the database stays locked.
- The flake exposes `packages.engine-analysis-guest`: a PowerShell script that registers a
  logon task in the DJ user's interactive session. On a file-based request it launches
  Engine, reports when it is running, and on a quit request closes it with a normal window
  close (never a forced kill), reporting completion or failure.

## Non-goals

- Booting or shutting down the VM, screenshots, clicking Engine's dialogs, and triggers.
- Deciding when analysis is complete beyond the per-track check above.
- Any change to the exporter or to the NixOS module.
