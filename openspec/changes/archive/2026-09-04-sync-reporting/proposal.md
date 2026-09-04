# Proposal: sync-reporting

## Why

The functional loop (M3U import → store → Engine/iTunes export) works on
home-forge, but unattended operation is still blind in four places:

1. Summaries live only in journald. Nothing persists what a run did, so a later
   "why did the Engine DB change?" has no durable answer.
2. The store is opaque about its origin. An export can consume a stale snapshot
   and nothing distinguishes it.
3. A non-empty import source yielding zero playlists still exits `0` (the exact
   `.m3u`/`.m3u8` failure mode, structurally).
4. Jobs fan out `OnSuccess=` only; failures notify nobody.

## What

- JSON run report per command via `--report-file PATH` (plus per-job
  `reportFile` Nix option): command, format, timestamps, counts, warnings,
  store provenance, exit status.
- Store provenance: `meta` records `source_format` + `imported_at` (UTC) at
  every rebuild; export summaries surface them.
- `empty_import_source` warning when a non-empty import dir yields zero
  playlists (trips `--fail-on-warning`).
- Job-level `onFailure` list → systemd `OnFailure=`, symmetric with
  `onSuccess`.
- `busy_timeout` on store connections (concurrent import-rebuild vs export-read
  waits instead of erroring).
- Engine `check_base_path` (folded in from the dropped `engine-check-base`
  splinter): optional worker-side mount for warn-only `file_missing` checks,
  mirroring iTunes; absolute `track_path_prefix` (`M:/library`, `../library`)
  locked by test.
- PLAN.md reconciliation (prior changes marked complete).

## Non-goals

- No metrics exporters, no `doctor` command, no in-module timers/retries/path
  units (downstream policy, unchanged boundary).
- No Engine-running detection (not reliably detectable; stays operational
  discipline).
- No matching-semantics change (exact normalized equality only), no Engine
  import, no two-way sync.
- No filesystem permission management.
