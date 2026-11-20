# Design

## Roles

- **Engine** is the source of truth for performance data. **Navidrome** remains the source of truth for playlists.
- The **performance model** is the contract between adapters and the unit of semantic diffing. It is not an authoritative store.
- **Native Engine → Engine USB** clones the database and keeps its blobs, so data the model does not represent survives.
- **File manifests** decide what to copy to a stick. **Performance snapshots** decide what changed on it. The two diffs are separate.

## Model

Frozen dataclasses serialized as JSON with a version number, validated where JSON is read. Times are seconds from the start of the audio; slots are numbered from 1.

- `TrackRef`: Engine origin database UUID and origin track ID — preserved across Engine USB exports.
- `Performance`: key (pitch class and mode), beat grid markers (position, beat index; constant tempo between markers), main cue, hot cues by slot, saved loops by slot.
- `Snapshot`: the captured library's UUID, the SHA-256 of the captured `m.db`, and each track's reference, Engine path and performance. Playlists join the snapshot with the Pioneer export, its first consumer.

Each adapter declares the fields it can represent and its time resolution. A diff compares only fields that both sides represent, at the coarser resolution, so an unsupported field is never read as a deletion and rounding is never read as an edit.

## Engine codec

`beatData`, `quickCues` and `loops` decode into lossless native structures that keep fields the model ignores: the default grid, per-marker counters, the main-cue flags and trailing bytes. Engine compresses with zlib at the default level, and Python's zlib reproduces its bytes, so `encode(decode(blob)) == blob` holds for real data. Write-back will change only the native fields an approved edit touches.

Mapping to the model: the adjusted grid, the adjusted main cue (negative means none), hot cues with a non-negative position, loops with both ends set, and `Track.key` through libdjinterop's key order. `trackData` is not decoded: `Track.key` holds the key even where `trackData` does not.

Capture rejects a database with active SQLite sidecars, reads the file once, and hashes and parses those same bytes, so the snapshot always matches its recorded hash.

## Rulings

1. The Pioneer exporter writes Engine's main cue as a memory cue and saved loops as memory loops.
2. Pioneer downbeats assume a beat index divisible by 4 starts a bar, until rekordbox desktop confirms it.
3. Exporters carry Engine's saved grid unchanged, even where it disagrees with `bpmAnalyzed`. Pioneer BPM derives from the grid.
4. Conflicting edits are blocked by default; a run may choose USB or source precedence explicitly.
5. Rust is limited to the rbxport helper, a separate flake package pinned to an upstream revision. The snapshot JSON is its input.
