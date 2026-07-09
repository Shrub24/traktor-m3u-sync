# Plan

## Current focus

**Phases 0–2 are complete.** The repo has a working Nix-first Python 3.14 environment, NML→M3U8 export, and M3U8→NML sandbox import.

Next up: **Phase 3 — Refinement and operational polish**.

## Phase plan

### Phase 0 — Repo bootstrap ✓

- establish root docs and agent directives
- create the Nix-first workspace (`flake.nix`, `treefmt-nix`, direnv)
- wire the Python package, CLI entry point, and tests
- standardize format, lint, type, and test workflows
- keep automation lightweight (`just`, `lefthook`)

**Status:** Complete (`openspec/changes/repo-bootstrap`)

### Phase 1 — NML export foundation ✓

**Intent:** Read a Traktor `collection.nml` and export playlists to standard UTF-8 `.m3u8` files on disk, preserving the Traktor folder hierarchy.

**OpenSpec change:** `nml-export`

Sub-areas:
1. **NML loading** — use `traktor-nml-utils` to parse `collection.nml` into typed models
2. **Playlist tree traversal** — walk `PLAYLISTS` nodes, extract playlist entries, skip `SMARTLIST` nodes
3. **Track metadata extraction** — read `LOCATION`/`DIR`/`FILE`, `ENTRY` title/artist, `INFO` duration
4. **Path translation (export direction)** — convert Traktor `VOLUME`/`DIR`/`FILE` with `/:` separators into clean Unix paths using configurable path mappings
5. **M3U8 generation** — write `#EXTM3U` + `#EXTINF` per track, one `.m3u8` per playlist
6. **Directory hierarchy** — mirror Traktor playlist folder structure as subdirectories on disk
7. **CLI wiring** — `traktor-m3u-sync export --collection <nml> --output-dir <dir>`
8. **Config** — TOML config for path mappings and export settings

### Phase 2 — Sandbox import foundation ✓

**Intent:** Read incoming `.m3u8` playlists and rebuild a designated sandbox folder node inside Traktor `collection.nml`, using a strict overwrite model.

**OpenSpec change:** `nml-import`

Sub-areas:
1. **M3U8 reading** — parse `.m3u8` files, extract track paths and `#EXTINF` metadata
2. **Track matching** — match M3U tracks to NML collection entries by filename + relative path
3. **Path translation (import direction)** — reverse-mapping from Unix paths back to Traktor Windows `VOLUME`/`DIR`/`FILE` format
4. **Sandbox node rebuild** — locate or create the designated sandbox `NODE TYPE="FOLDER"` in the playlist tree, clear its children, rebuild from M3U state
5. **Unmatched track handling** — skip and log unmatched tracks; produce an import report file
6. **Safe NML write-back** — use `traktor-nml-utils` save with backup-before-write, validate output round-trips
7. **CLI wiring** — `traktor-m3u-sync import --m3u-dir <dir> --collection <nml>`
8. **Import report** — structured summary: matched, skipped, warnings

### Phase 3 — Refinement and operational polish

**Intent:** Harden configuration, improve reporting, and add operational niceties for automated/scheduled use.

**Planned OpenSpec changes:** `sync-config`, `sync-reporting` (split as needed)

Sub-areas:
- config ergonomics: path mapping profiles, CLI overrides, validation
- reporting improvements: JSON/text report formats, log verbosity
- operational polish: exit codes, dry-run mode, verbosity flags
- selective CI additions when the project is stable enough to benefit

### Phase 4 — Future expansion (deferred)

These are explicitly out of scope until Phases 1–3 prove the core loop:

- Smartlist export (read-only; writing smartlists is poorly tested)
- Bidirectional sync beyond sandbox overwrite (fine-grained merge/conflict)
- Navidrome-specific automation
- Traktor history file handling
- Cue point / analysis metadata in custom M3U tags
- Watch mode (inotify / systemd path units)
- Cross-platform import targets (macOS)

## Working assumptions

- Traktor import target is Windows-first for now.
- Linux/NixOS is the expected operating environment for the sync worker itself.
- Path mappings are configurable in design, even if the first real deployment uses a fixed mapping.
- Smartlists are out of scope for import; export of smartlists deferred until Phase 4+.
- `traktor-nml-utils` (v4.0.0+) is the primary NML parsing library. If xsdata write round-tripping proves fragile, fall back to direct `lxml` writes using the same models as reference.
- TOML is the config format.
- Package: `traktor_m3u_sync`, CLI: `traktor-m3u-sync`.

## Change discipline

- Keep changes narrow and sequential.
- Make architectural decisions explicit in docs when they become durable.
- Avoid bundling bootstrap, export, and import work into a single implementation change.
- Each phase maps to one primary OpenSpec change; split further if scope warrants it.
