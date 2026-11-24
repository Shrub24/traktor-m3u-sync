# Design

## Ownership

The application sequences DJ operations and owns their outcomes, progress, retry eligibility, and confirmations. It calls the same operations the standalone CLI uses. The Sync Manager TUI renders and responds to application decisions; it does not implement a second workflow.

The deployment supplies the playlist fetch and Engine-offline operations. In homelab, these are Navidrome and Windows/libvirt, respectively. Keep VM start/stop, guest coordination, credentials, time limits and policy downstream; keep Engine library checks and writes in the application. Start with the configured fetch and guest runner as the only external operations; no plugin registry or arbitrary command graph. Preserve exclusive access to the Engine write window, including against standalone writers. A fixture runner can exercise the workflow without systemd or a Windows VM.

Systemd supervises the invocation, controls the identity and resources, and routes logs and terminal failure notifications. The generic import/export jobs and their success fan-out remain available. For the downstream DJ refresh, replace the operator-facing success chain with one supervised workflow, not a second entry point executing the same chain in parallel.

Refresh sequences the existing units rather than running their writes in-process: `refresh` starts each configured unit in order with `systemctl start`, under a polkit rule limited to exactly those units, and stops at the first failure. Each unit keeps its identity and its conflict with the Engine VM, so the write window stays exclusive even against a manual VM start. A unit's own JSON report, when it wrote one during this run, is attached to its step; a USB build report marks the step `partial` when only some formats published. Rejected: in-process writes (the app would own VM exclusion) and a reporter over the `OnSuccess=` chain (outcomes stay split across unit runs).

## Actions

- **Refresh exports:** fetch → import playlists → update Engine → analyze pending tracks if needed → verify Engine is closed → build selected formats. There is no stick I/O. Skipping guest analysis does not skip export: playlist membership or order may still have changed.
- **Sync Manager:** the operator supplies an explicit stick target. Browse one format at a time; export Engine, rekordbox, or both. Each format has its own selection, initialized from the actual stick library (empty for a blank stick), not the delivery cache.
- **← Import player edits:** open the existing Engine diff in a confirmation popup. The playlist selection does not filter this operation. It writes approved edits to Engine only, not playlists, audio or the stick. Pioneer import is unavailable.
- **Export playlists →:** preview the selected playlist set and transfer per format in a confirmation popup. Show playlist changes, audio reuse and transfer bytes, and database replacements. Unchecking a playlist removes it from the exported library, not its audio from the stick. Skipping import does not authorize replacement of an unknown or edited database.

### Playlist tree

```text
Engine DJ · Lexar USB
▾ Sets
  [x]   Dub Set
  [x] ^ Peak Time
  [x] + Afterhours
  [ ] - Warmup

[← Import player edits]   [Export playlists →]
```

The checkbox shows desired membership; the adjacent marker shows the change relative to the stick: add `+`, remove `-`, update `^`, blank if unchanged. Update means the selected playlist's exported content differs, not merely that it was selected. Color and Nerd Font icons can supplement the markers but must not be needed to read them.

Playlist sync prepares the full library on the host. Stick export assembles the selected libraries from prepared artifacts without fetching playlists, launching Engine, or generating waveforms. Benchmark subset assembly with rbxport before making a latency claim. Approved player edits invalidate affected prepared outputs; refresh those from Engine before previewing an export, rather than offering a plan from stale data.

## Reporting and recovery

A run has a versioned report with a run ID, current stage, stage outcomes and timestamps or durations, requested formats, published generation IDs, structured issues, and any pending decision or retry. Persist the report at meaningful transitions on the host; render terminal updates from the same data. Reference existing JSON edit reports instead of duplicating them. Report progress in real units (tracks, files, bytes); for an unmeasured wait, show its reason and elapsed time, not a percentage.

Treat harmless duplicates as warnings. Unsupported or unreadable audio makes only its affected format fail: report the offending file and a remedy. A partial result is not overall success: name what published, what failed, and whether there is an older usable output. Integrity failures, stale approvals and unsafe publication are hard stops for the affected operation. A network interruption may resume the same delivery after checking the stick, generation and database again; surface an interrupted Pioneer switch as needing retry before use. Do not auto-retry writes or promise whole-stick rollback. Reuse existing generation and delivery state; the run report describes what happened and is not authority to skip safety checks.

## Alternatives

1. **Application workflow + Linux Sync Manager (recommended):** one execution model with progress and approvals that can be reused by other surfaces. Costs a small reporting and composition layer.
2. **Keep chaining units and aggregate journals:** least change to deployment, but stage outcomes and recovery still have to be inferred from multiple unit runs.
3. **Web-first workflow service:** easiest way to reattach from another device, but adds authentication and service state before the workflow contract is proven. Keep OliveTin as a possible refresh launcher and Tasker as a bridge launcher; neither owns approvals or retries. Defer a web UI until the Linux Sync Manager proves the workflow.

## Performance baseline

Record wall time and measured work for cold, unchanged, and one-track runs; distinguish guest wait, audio hash/cache work, waveform generation, transfer and publication. Compare before and after on the same fixture and environment. Candidate improvements are early format validation and reuse of verified artifacts, not new parallelism or weaker guards.
