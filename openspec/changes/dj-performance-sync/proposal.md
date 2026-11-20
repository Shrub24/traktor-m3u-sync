# DJ performance sync

## Why

Engine USB delivery works on the SC6000, and a Pioneer USB export plus the return of player edits are next. Both need one representation of performance data (key, beat grid, cues, loops) that every format adapter reads and writes, and that edits can be diffed in. The playlist model and its SQLite cache only carry playlist structure and basic tags.

## What changes

- Add a versioned, serializable performance model: track identity by Engine origin, key, beat grid, main cue, hot cues and saved loops.
- Add an Engine codec that decodes and re-encodes `PerformanceData` blobs without loss, and maps them to the model.
- Capture a performance snapshot from a closed Engine database.

Later phases in this change move the Engine USB spike into the package with systemd wiring, add the Pioneer export, then Engine and Pioneer read-back with a per-slot three-way diff and approved write-back, then the operator UX.

## Non-goals

- The playlist model and store stay unchanged.
- No new database: snapshots are JSON files, and per-stick baselines are the snapshots delivered to that stick.
- Waveforms are not modelled; Pioneer waveforms are generated from audio.
- No playlist or tag edits come back from devices.
- Exporters carry Engine's saved grid as-is; grid correction belongs to the user in Engine.
