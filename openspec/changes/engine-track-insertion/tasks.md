# Tasks: engine-track-insertion

## 1. Implementation

- [x] 1.1 Insert unknown store tracks visible under `check_base_path` as unanalyzed Engine `Track` rows inside the staged transaction, relying on Engine's triggers for origin and performance data
- [x] 1.2 Link embedded album art by SHA-1 of the first embedded picture (find or insert a hash-only `AlbumArt` row) via `mutagen`
- [x] 1.3 Report `tracks_inserted`, print `track_missing`/duplicate details in original case, and add `mutagen` to `pyproject.toml`, `uv.lock` and the flake package, with local type stubs

## 2. Validation

- [x] 2.1 Fixture uses Engine's live `Track`/`AlbumArt`/`PerformanceData` DDL and triggers; tests cover insertion, absent-file skip, art linking/reuse, same-run reuse and rerun matching
- [x] 2.2 Live check on home-forge: Engine shows art for an externally set `albumArtId` that points at a cached thumbnail
- [ ] 2.3 Live check on home-forge: Engine analyzes and imports tags for rows inserted with NULL title/artist/album (test tracks 2569–2571)
- [ ] 2.4 Live check on home-forge: Engine renders a thumbnail for a new hash-only `AlbumArt` row (504, 505)

## 3. Docs

- [x] 3.1 Update `README.md`, `ARCHITECTURE.md`, `PLAN.md`, `docs/nix-deployment.md`, `traktor-m3u-sync.example.toml` and the module option description
