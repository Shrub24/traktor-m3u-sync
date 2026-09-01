## Why

Before choosing direct SQLite mutation over libdjinterop, prove that the existing format-neutral store can populate an Engine DJ 5.0.0 database using only Python's stdlib while preserving Engine's native schema and ordering invariants.

## What Changes

- Add a proof-only store-to-Engine SQLite writer that operates on a copied Engine-generated `m.db`.
- Gate the write to Engine schema 3.0.2 and verify database integrity before and after mutation.
- Match store tracks against the media drive's Engine database and add ordered playlists without writing track, analysis, cue, waveform, or artwork data.
- Add one runnable regression test and run the proof against copies of the live home-forge databases.
- Do not add CLI, config, NixOS module, or runtime dependency integration.

## Capabilities

### New Capabilities
- `engine-sqlite-proof`: Demonstrate direct SQLite transfer from the internal playlist store to an Engine DJ 5.0.0 database copy.

### Modified Capabilities

None.

## Impact

Adds a small proof module and regression test. It uses only `sqlite3`, consumes the existing store model, and never mutates the live Engine database. The proof targets an Engine media-drive database, where tracks and playlists share one database UUID. The result decides whether the later `engine-export` change uses direct SQLite or libdjinterop.
