# Tasks: rekordbox-xml-export

## 1. Implementation

- [x] 1.1 Extract the iTunes track-collection step (identity dedup, sorted TrackIDs, unresolved and missing-file warnings) into a shared `formats/collection.py`
- [x] 1.2 Add the `rekordbox` exporter: `DJ_PLAYLISTS` 1.0.0 with `COLLECTION` and the `ROOT` playlist tree, published atomically
- [x] 1.3 Share one `LibraryXmlConfig` shape across `[itunes]` and `[rekordbox]`; apply `--output-file`/`--location-base`/`--check-base-path` to the selected format only; sandbox dry runs
- [x] 1.4 Accept `format = "rekordbox"` export jobs in the NixOS module

## 2. Validation

- [x] 2.1 Tests: document structure, URI encoding, nested folder counts, stored order with repeats, unresolved and missing-file warnings, byte-stable reruns, config errors, override scoping, dry run
- [x] 2.2 Module eval fixture renders a rekordbox job's TOML and the packaged CLI accepts it
- [ ] 2.3 Live check: rekordbox loads the exported XML and shows the playlist tree with every track found

## 3. Docs

- [x] 3.1 Update `README.md`, `ARCHITECTURE.md`, `PLAN.md`, `docs/nix-deployment.md` and `traktor-m3u-sync.example.toml`
