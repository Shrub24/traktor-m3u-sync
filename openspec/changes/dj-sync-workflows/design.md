# Design

## Ownership

The application sequences DJ operations and owns their outcomes, progress, retry eligibility, and confirmations. It calls the same operations the standalone CLI uses. The guided CLI renders and responds to application decisions; it does not implement a second workflow.

The deployment supplies the playlist fetch and Engine-offline operations. In homelab, these are Navidrome and Windows/libvirt, respectively. Keep VM start/stop, guest coordination, credentials, time limits and policy downstream; keep Engine library checks and writes in the application. Start with the configured fetch and guest runner as the only external operations; no plugin registry or arbitrary command graph. Preserve exclusive access to the Engine write window, including against standalone writers. A fixture runner can exercise the workflow without systemd or a Windows VM.

Systemd supervises the invocation, controls the identity and resources, and routes logs and terminal failure notifications. The generic import/export jobs and their success fan-out remain available. For the downstream DJ refresh, replace the operator-facing success chain with one supervised workflow, not a second entry point executing the same chain in parallel.

## Actions

- **Refresh exports:** fetch → import playlists → update Engine → analyze pending tracks if needed → verify Engine is closed → build selected formats. There is no stick I/O. Skipping guest analysis does not skip export: playlist membership or order may still have changed.
- **Sync this stick:** the operator starts it from the device holding the stick and supplies an explicit target. Inspect → optionally review and approve Engine edits → rebuild outputs affected by accepted edits → preview delivery → confirm → deliver. Reuse the existing edit report and confirmation guards. Skipping import is not permission to replace an unknown or edited database. Never resume by applying stale approval.

## Reporting and recovery

A run has a versioned report with a run ID, current stage, stage outcomes and timestamps or durations, requested formats, published generation IDs, structured issues, and any pending decision or retry. Persist the report at meaningful transitions on the host; render terminal updates from the same data. Reference existing JSON edit reports instead of duplicating them. Report progress in real units (tracks, files, bytes); for an unmeasured wait, show its reason and elapsed time, not a percentage.

Treat harmless duplicates as warnings. Unsupported or unreadable audio makes only its affected format fail: report the offending file and a remedy. A partial result is not overall success: name what published, what failed, and whether there is an older usable output. Integrity failures, stale approvals and unsafe publication are hard stops for the affected operation. A network interruption may resume the same delivery after checking the stick, generation and database again; surface an interrupted Pioneer switch as needing retry before use. Do not auto-retry writes or promise whole-stick rollback. Reuse existing generation and delivery state; the run report describes what happened and is not authority to skip safety checks.

## Alternatives

1. **Application workflow + guided CLI (recommended):** one execution model with progress and approvals that can be reused by other surfaces. Costs a small reporting and composition layer.
2. **Keep chaining units and aggregate journals:** least change to deployment, but stage outcomes and recovery still have to be inferred from multiple unit runs.
3. **Web-first workflow service:** easiest way to reattach from another device, but adds authentication and service state before the workflow contract is proven. Keep OliveTin as a possible refresh launcher and Tasker as a bridge launcher; neither owns approvals or retries. Defer a web UI and TUI until the guided CLI proves the workflow.

## Performance baseline

Record wall time and measured work for cold, unchanged, and one-track runs; distinguish guest wait, audio hash/cache work, waveform generation, transfer and publication. Compare before and after on the same fixture and environment. Candidate improvements are early format validation and reuse of verified artifacts, not new parallelism or weaker guards.
