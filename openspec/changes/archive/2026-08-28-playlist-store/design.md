# Design: playlist-store

## Context

The repo currently implements two point-to-point workflows: `export_service` (NML→M3U8) and `import_service` (M3U8→NML sandbox rebuild), with format logic, path translation, and orchestration fused in each service. The project is pivoting to a multi-format playlist bridge (see proposal.md — Why), which requires a neutral internal model, a persistent store, and a per-format adapter contract. Existing behavior (hierarchy mirroring, matching, sandbox safety, warnings) is protected by 47 passing tests and must survive the refactor.

## Goals / Non-Goals

**Goals:**

- Hub-and-spoke architecture: internal model at the center, one adapter package per format.
- Persistent SQLite store caching imported playlist state between runs; import and export are independent processes.
- Adapter contract that makes adding a format (iTunes XML next, Engine DJ later) a single-package job.
- Behavior-preserving refactor of the NML and M3U capabilities onto the framework.

**Non-Goals:**

- iTunes XML exporter, Engine DJ adapter, reverse iTunes import (separate changes).
- Incremental/diff-based sync — wholesale rebuild only.
- Multi-source store accumulation (merging NML and M3U imports into one store) — v1 store holds a single source snapshot.
- Tag enrichment (tinytag), schema migrations, repo/package rename.

## Decisions

### D1: Hub-and-spoke with an internal model (vs point-to-point)

Every adapter converts between one external format and the internal model; no adapter talks to another adapter. Alternative (extending point-to-point) rejected: adapter count grows quadratically with formats and the store-mediated two-command model becomes impossible.

### D2: SQLite store (vs JSON file, vs in-memory)

SQLite via stdlib `sqlite3`. Rationale: track dedup across playlists is a relational problem; beets proves the pattern for exactly this domain; Engine DJ's own library is SQLite, so prior art aligns. JSON rejected: weak querying/dedup at library scale. In-memory rejected: does not decouple import from export across processes.

### D3: Store is a cache, not truth — wholesale rebuild, no migrations

The store holds one source's snapshot. `import --format <fmt>` wipes and rebuilds the store from that source. A `meta` table carries `schema_version`; on open, a version mismatch fails fast with a structured error directing the user to re-run import. No migration machinery — the store is always rebuildable from sources, so schema changes are handled by re-import. Consequence: no speculative columns (e.g. BPM/key) are added ahead of need.

### D4: Track identity = casefolded POSIX library-relative path

Primary identity is the library-relative path normalized to POSIX separators and casefolded — stable across machines and library roots, and it is exactly the value both directions already compute (NML paths relative to `traktor_root`, M3U paths relative to `m3u_root`). Original casing is preserved for rendering. Fallback identity (artist+title, casefolded/whitespace-collapsed) applies only to entries with no resolvable path; ambiguous fallback matches warn instead of silently merging. Unresolvable tracks are stored flagged with their raw path, excluded from identity dedup, and handled by per-target warning policy.

### D5: Adapter contract

Two protocols plus a path-mapping contract, with shared result/warning types:

- `Importer.read(source) -> ImportResult` — parse external format, resolve identities, return model objects plus warnings.
- `Exporter.write(playlists, target) -> ExportResult` — render model objects to the external format plus warnings.
- `PathMapping` — per-adapter normalization to/from library-relative identity (Traktor `VOLUME`/`DIR`/`FILE`/`PRIMARYKEY` ↔ identity; M3U relative/absolute ↔ identity; iTunes `file://` later).

Formatting quirks (Traktor explicit close tags, plist structure later) live inside adapters; the contract deals only in the internal model.

### D6: Command surface — `import`/`export` with format flag

- `traktor-m3u-sync import --format nml|m3u` — source → store (wholesale rebuild).
- `traktor-m3u-sync export --format m3u|nml` — store → target. Pure store-only: export never reads a source directly; it fails fast on an empty/uninitialized store. A future single-command wrapper just runs both in sequence.

Direction naming is store-relative (import = into store, export = out of store), so the old M3U→NML "import" becomes `export --format nml`.

### D7: Format-based config sections

The direction-based `[export]`/`[import]` sections no longer fit the command surface (both commands need `collection_path`, in opposite directions). Config is restructured per format:

```toml
[library]
traktor_root = "C:/Music"
m3u_root = "/music"

[store]
path = "~/.local/state/traktor-m3u-sync/store.db"   # default from SSOT constant

[nml]
collection_path = "/path/to/collection.nml"
sandbox_name = "Imported Playlists"

[m3u]
output_dir = "/path/to/exported"
import_dir = "/path/to/navidrome"
```

`[store] path` defaults from a single source-of-truth constant in the config module. CLI overrides remain per-command for the fields each command uses. The example config template is updated accordingly.

### D8: Module layout

```text
src/traktor_m3u_sync/
├── model/        # internal IR (frozen dataclasses) + identity normalization
├── store/        # SQLite persistence (schema v1, rebuild, version check)
├── formats/      # one package per format modality
│   ├── nml/      # importer (library → store) + exporter (store → sandbox)
│   └── m3u/      # importer (files → store) + exporter (store → files)
├── paths/        # path mapping contract + per-format implementations
├── services/     # import/export orchestration + summaries
├── config.py
└── cli.py
```

Refactor mapping: `nml_reader`/`playlist_tree`/`collection_matcher` → `formats/nml` importer and exporter internals; `m3u_reader`/`m3u_writer` → `formats/m3u`; `pathmap` → `paths/`; `export_service`/`import_service` decompose into the adapters plus `services/` orchestration.

### D9: Store schema (v1)

```sql
meta(schema_version)
tracks(id, identity UNIQUE, rel_path, raw_path, title, artist, album, duration_seconds, resolved)
playlists(id, name, folder_path, position)
playlist_tracks(playlist_id, track_id, position)
```

`identity` is the casefolded normalized key (NULL for unresolved tracks, which are deduped by `raw_path` instead). Duration is stored in seconds; adapters convert at the boundary (Traktor is milliseconds).

## Risks / Trade-offs

- [Refactor regressions in the working NML/M3U flows] → existing tests are adapted to the two-command flow and must stay green; behavior-preserving mapping is reviewed per adapter (CodeReviewer gate).
- [Store staleness vs changing sources] → wholesale rebuild policy; store is documented as a cache; export fails fast on an empty store rather than rendering stale or partial state.
- [Case-insensitive identity false merges] → casefolded identity merges tracks differing only by case; accepted trade-off (cross-platform case drift is the common failure, case-distinguished duplicates are rare), warnable later if it materializes.
- [Single-source store limits multi-source bridging] → deliberate v1 simplification; upgrade path is provenance columns plus per-source scoped rebuilds, without contract changes.
- [Breaking CLI/config change] → pre-release project, pivot is user-driven; README, example config, and specs updated in the same change.

## Migration Plan

Single-repo change, no deployment migration. Order: docs → model/identity → store → contracts → adapters → services → config/CLI → tests adapted green → strict validation. Rollback is git revert; the store file is disposable state.

## Open Questions

None — all design decisions were resolved with the user during exploration.
