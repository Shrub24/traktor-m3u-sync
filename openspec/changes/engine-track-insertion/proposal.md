# Proposal: engine-track-insertion

## Why

Engine export only references tracks Engine has already imported, so every store track
added since the last Engine import is skipped with `track_missing`. On home-forge, new
tracks are spread across many album folders, and importing them in Engine one folder at
a time defeats the purpose of the sync.

A live test on 2026-09-08 showed that Engine DJ 5.0 analyzes a `Track` row inserted by
SQLite on its next start (length, waveform, BPM), but never links album art to it. Two
checks on 2026-11-17 established how art is stored:

- `AlbumArt.hash` is the SHA-1 of the file's embedded picture bytes.
- Engine shows the cached thumbnail once `Track.albumArtId` points at that row, with no
  reimport needed.

## What

- When `[engine].check_base_path` is set and the store track's file exists there, Engine
  export inserts a `Track` row for each store track whose path matches no Engine track.
- The inserted row is unanalyzed and has no explicit `id`. Engine's own triggers fill in
  the origin columns and the `PerformanceData` row. The track's membership is written in
  the same run.
- If the file has embedded art, the exporter finds the `AlbumArt` row with that hash, or
  inserts one with a NULL blob. It then sets `albumArtId` on the new track.
- A new `tracks_inserted` count is reported.
- `track_missing` warnings now print the path in its original case.

## Non-goals

- Existing Engine `Track`, `PerformanceData` and `AlbumArt` rows are never modified.
- Inserted tracks are never deleted. They become part of the Engine library, and later
  runs match them like any other track.
- No analysis, tag, or cue data is written; Engine does the analysis.
- Art is not read from `cover.jpg`, and Ogg/Opus pictures are not read.
- No changes to the L: main library. No new configuration option, because
  `check_base_path` already names the worker-side library mount.
