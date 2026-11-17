# Proposal: rekordbox-xml-export

## Why

Pioneer players read a rekordbox USB export, and that export needs per-track analysis files
that only rekordbox (or an external tool such as `baken`) produces. Every route to such a
stick, whether rekordbox itself, `baken expressport`, Lexicon or MIXO, can import playlists
from rekordbox's published XML format. Exporting that XML from the store is the part this
project owns. Building the USB stays a downstream step.

## What

- `export --format rekordbox` writes the store to a rekordbox XML file ("XML file format
  for playlists sharing", `DJ_PLAYLISTS` version 1.0.0).
- `COLLECTION` holds one `TRACK` per resolvable store track, with `TrackID`, `Name`,
  `Artist`, `Album`, `TotalTime` in seconds, and `Location`. `Location` is rendered from
  `[rekordbox].location_base`, a `file:` URI, exactly like iTunes Locations.
- `PLAYLISTS` mirrors the stored folder tree under the required `ROOT` folder node.
  Playlists reference tracks by `TrackID` (`KeyType="0"`) in stored order.
- `[rekordbox]` has the same shape as `[itunes]`: `output_file`, required `location_base`,
  and optional `check_base_path` for `file_missing` warnings. The existing
  `--output-file`, `--location-base` and `--check-base-path` flags apply to whichever of the
  two formats is selected.
- The output is published atomically like the other generated targets. `--dry-run` writes
  into a sandbox.
- The NixOS module accepts `format = "rekordbox"` export jobs with a `rekordbox` settings
  block.
- iTunes and rekordbox share one track-collection step: dedup by identity, stable sorted
  TrackIDs, unresolved and missing-file warnings.

## Non-goals

- No rekordbox USB export (`export.pdb`, OneLibrary, ANLZ analysis files).
- No beat grids, cues, BPM, key or other analysis fields (`TEMPO`, `POSITION_MARK`).
- No rekordbox import.
