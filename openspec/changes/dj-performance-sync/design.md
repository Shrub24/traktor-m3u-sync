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
- `Snapshot`: the captured library's UUID, the SHA-256 of the captured `m.db`, and each track's reference, Engine path and performance. It also carries the playlist tree in Engine's order and the track metadata an exporter lists (tags, duration, bitrate, sample rate, file size, artwork thumbnail).

Each adapter declares the fields it can represent and its time resolution. A diff compares only fields that both sides represent, at the coarser resolution, so an unsupported field is never read as a deletion and rounding is never read as an edit.

## Engine codec

`beatData`, `quickCues` and `loops` decode into lossless native structures that keep fields the model ignores: the default grid, per-marker counters, the main-cue flags and trailing bytes. Engine compresses with zlib at the default level, and Python's zlib reproduces its bytes, so `encode(decode(blob)) == blob` holds for real data. Write-back will change only the native fields an approved edit touches.

Mapping to the model: the adjusted grid, the adjusted main cue (negative means none), hot cues with a non-negative position, loops with both ends set, and `Track.key` through libdjinterop's key order. `trackData` is not decoded: `Track.key` holds the key even where `trackData` does not.

Capture rejects a database with active SQLite sidecars, reads the file once, and hashes and parses those same bytes, so the snapshot always matches its recorded hash.

## USB publication

Both formats share one source, playlist selection, output root and SFTP destination. `[usb].formats`
defaults to both; repeatable `--format` narrows the run. Generations and stick delivery records
are independent by format. Pioneer uses rbxport's incremental working tree and stages its audio
by hardlink: rbxport publishes new audio by rename, leaving previous generation inodes intact.

Engine replaces one database atomically. Pioneer uploads assets first, then replaces
`exportExt.pdb`, `export.pdb` and `exportLibrary.db` individually. A host-side pending record
recognizes files from an interrupted database switch on retry; it is not a transaction across
the group. Replacing a changed ANLZ file checks for edits to that file first. An interruption
can leave mixed assets or databases; finish a retry before using the stick.

## Rulings

1. The Pioneer exporter writes Engine's main cue as a memory cue and saved loops as memory loops.
2. Pioneer downbeats assume a beat index divisible by 4 starts a bar, until rekordbox desktop confirms it.
3. Exporters carry Engine's saved grid unchanged, even where it disagrees with `bpmAnalyzed`. Pioneer BPM derives from the grid.
4. Read-back compares the stick with current Engine, not with what was delivered, and approved differences take the stick's value. Engine runs headless, so between a delivery and its read-back only the player changes performance data. Revisit with a second writer of performance data (another stick of the same tracks, or enrichment into Engine), where a delivered baseline would be needed to tell which side changed.
5. Rust is limited to the rbxport helper, a separate flake package pinned to an upstream revision. The snapshot JSON is its input, and `tests/fixtures/snapshot.json` is parsed by both test suites.
6. The Pioneer export carries no comments. In this library they are mostly release notes, links and encoder boilerplate, often longer than the roughly 4 KB of strings `export.pdb` holds per track. The `/* a / b */` lists some taggers write into comments become My Tags under one `Tags` category; Mixed In Key key and energy prefixes are dropped, since the key comes from Engine.
