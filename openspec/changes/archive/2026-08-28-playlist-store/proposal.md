# Proposal: playlist-store

## Why

The project is pivoting from a Traktor-centric NML↔M3U sync tool into a multi-format playlist bridge (Navidrome M3U in, iTunes XML out first; Traktor NML retained as a modality; Engine DJ deferred). The current point-to-point services (`export_service`, `import_service`) hardwire each workflow to one source and one target format, so every new format would add another bespoke pipeline. A neutral internal playlist model plus a persistent, rebuildable store decouples import from export, gives every format a single adapter contract to implement, and makes the two-command (`import`/`export`) model the honest architecture.

## What Changes

- **BREAKING**: Replace the direct `export` (NML→M3U) and `import` (M3U→NML) commands with store-mediated `import --format <fmt>` (source → store) and `export --format <fmt>` (store → target) commands.
- Introduce an internal playlist model (frozen dataclasses: playlists, ordered tracks, track identity) as the hub all adapters read/write.
- Introduce a persistent SQLite store that caches imported playlist state between runs. The store is a rebuildable staging cache, not a source of truth; `import --format <fmt>` performs a wholesale rebuild of the store from that source.
- Introduce an adapter contract (`Importer`/`Exporter` protocols plus a path-mapping contract) that each format modality implements; structured warnings/summaries are part of the shared contract types.
- Refactor the existing NML and M3U capabilities onto the framework as the first adapters: NML importer (library → store), NML exporter (store → sandbox rebuild), M3U importer, M3U exporter. Output behavior (hierarchy, matching, warnings, sandbox safety) is preserved.
- Add track identity normalization: casefolded POSIX library-relative path as primary identity, artist+title fallback with ambiguity warnings, unresolvable tracks stored flagged and excluded from identity dedup.
- Add `[store]` config section (path, with a single-source-of-truth default constant) and store schema versioning that fails fast with a re-import directive on mismatch instead of migrating.
- Align the NixOS module with the new surface: render format-based config sections (`[library]`/`[store]`/`[nml]`/`[m3u]`) and pass `--format` on service exec lines — module-generated configs would otherwise be rejected by the new loader (folded in after review).
- Update canonical docs (PLAN.md pivot, ARCHITECTURE.md architecture section) to record the multi-format bridge direction.

## Capabilities

### New Capabilities

- `playlist-store`: the internal playlist model, SQLite store persistence, track identity normalization, wholesale rebuild semantics, and schema versioning behavior.
- `playlist-sync-framework`: the importer/exporter adapter contract, per-adapter path mapping contract, and the store-mediated `import`/`export` command surface with format selection.

### Modified Capabilities

- `nml-export`: the NML→M3U8 workflow becomes store-mediated — `import --format nml` populates the store from `collection.nml` and `export --format m3u` renders `.m3u8` output from the store. All output-behavior requirements (hierarchy mirroring, smartlist skipping, warnings, summaries, config validation) are preserved.
- `nml-import`: the M3U→NML workflow becomes store-mediated — `import --format m3u` populates the store from `.m3u8` input and `export --format nml` rebuilds the managed sandbox from the store. All behavior requirements (sandbox rebuild, matching, backup/validate, warnings) are preserved.

## Impact

- **Code**: `src/traktor_m3u_sync/` restructured into `model/`, `store/`, `formats/{m3u,nml}/`, `paths/`, `services/`; `export_service.py` and `import_service.py` are decomposed into adapters; `config.py` and `cli.py` gain store config and format flags. Existing tests are adapted to the two-command flow and must stay green.
- **CLI**: breaking command-surface change (`export`/`import` replaced by `import --format`/`export --format`).
- **Nix module**: `nix/modules/traktor-m3u-sync.nix` and the `flake.nix` module-eval check updated to the format-based config and `--format` service surface.
- **Config**: sections restructured to `[library]`/`[store]`/`[nml]`/`[m3u]`, replacing the direction-based `[export]`/`[import]` sections; `traktor-m3u-sync.example.toml` updated.
- **Dependencies**: none added (SQLite via stdlib `sqlite3`).
- **Docs**: PLAN.md, ARCHITECTURE.md, README.md updated for the pivot and new command surface.
- **Deferred**: iTunes XML exporter (next change), Engine DJ adapter, reverse iTunes import, tag enrichment, incremental sync, repo/package rename.
