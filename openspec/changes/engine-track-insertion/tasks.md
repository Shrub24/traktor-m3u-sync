# Tasks: engine-track-insertion

## 1. Implementation

- [x] 1.1 Insert unknown store tracks visible under `check_base_path` as unanalyzed Engine `Track` rows inside the staged transaction, relying on Engine's triggers for origin and performance data
- [x] 1.2 Link embedded album art by SHA-1 of the first embedded picture (find or insert a hash-only `AlbumArt` row) via `mutagen`
- [x] 1.3 Report `tracks_inserted`, print `track_missing`/duplicate details in original case, and add `mutagen` to `pyproject.toml`, `uv.lock` and the flake package, with local type stubs
- [x] 1.4 Write Engine's imported tag columns on inserted rows (`isMetadataImported = 1`); skip files `mutagen` cannot read
- [x] 1.5 Render missing `Artwork/<base64url(hash)>.jpg` thumbnails with Pillow and write them before publishing; keep dry runs inside the sandbox

## 2. Validation

- [x] 2.1 Fixture uses Engine's live `Track`/`AlbumArt`/`PerformanceData` DDL and triggers; tests cover insertion with metadata, absent/unreadable skips, art linking/reuse, thumbnail rendering and publication order, undecodable pictures, rerun matching and dry-run isolation
- [x] 2.2 Live check on home-forge: Engine shows art for an externally set `albumArtId` that points at a cached thumbnail
- [x] 2.3 Live check on home-forge: Engine analyzes inserted rows on start but never imports their tags or renders their thumbnails (40 rows from 2026-11-17); a manual reimport fills tags but still renders no thumbnail for a pre-existing `AlbumArt` row
- [x] 2.4 Live check on home-forge: Engine displays externally written thumbnails in its format (Zero-G, Dust)
- [ ] 2.5 Live check on home-forge: a fresh export inserts tracks that show tags and covers in Engine with no reimport

## 3. Docs

- [x] 3.1 Update `README.md`, `ARCHITECTURE.md`, `PLAN.md`, `docs/nix-deployment.md`, `traktor-m3u-sync.example.toml` and the module option description
