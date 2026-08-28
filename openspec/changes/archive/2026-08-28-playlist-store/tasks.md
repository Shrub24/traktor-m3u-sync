# Tasks: playlist-store

## 1. Docs and structure

- [x] 1.1 Update PLAN.md with the multi-format bridge pivot and update ARCHITECTURE.md architecture section (hub-and-spoke, store, adapter contract, new command surface)
  - refs: `PLAN.md`, `ARCHITECTURE.md`, proposal.md
  - verify: docs describe the store-mediated import/export model and deferred modalities
- [x] 1.2 Create the new module skeleton (`model/`, `store/`, `formats/nml/`, `formats/m3u/`, `paths/`, `services/`) and verify imports resolve
  - refs: design.md D8
  - verify: `uv run python -c "import traktor_m3u_sync"` succeeds and tree matches design layout

## 2. Model and store

- [x] 2.1 Implement the internal playlist model (frozen dataclasses: playlists, ordered tracks, metadata) and track identity normalization (casefolded POSIX library-relative path primary, artist+title fallback with ambiguity warnings, unresolved flagged)
  - refs: `specs/playlist-store/spec.md`, design.md D4, D9
  - verify: unit tests cover identity normalization, fallback, and unresolved flagging
- [x] 2.2 Implement the SQLite store layer (schema v1, wholesale rebuild, schema-version fail-fast, SSOT default path constant)
  - refs: `specs/playlist-store/spec.md`, design.md D3, D9
  - verify: unit tests cover round-trip persistence, rebuild replacement, and version-mismatch error

## 3. Adapter contract and format adapters

- [x] 3.1 Define the importer/exporter/path-mapping contracts with shared result and structured warning types
  - refs: `specs/playlist-sync-framework/spec.md`, design.md D5
  - verify: contracts importable and typed; warning types shared across adapters
- [x] 3.2 Implement the NML importer (collection.nml → store: playlist tree traversal, smartlist skip with warnings, Traktor path translation to identity)
  - refs: `specs/nml-export/spec.md`, design.md D8
  - verify: fixture test populates the store from a synthetic collection and skips smartlists with warnings
- [x] 3.3 Implement the M3U exporter (store → UTF-8 `.m3u8`: hierarchy mirroring, `$ROOT` omission)
  - refs: `specs/nml-export/spec.md`, design.md D8
  - verify: fixture test renders `.m3u8` output identical in content to the pre-refactor exporter
- [x] 3.4 Implement the M3U importer (`.m3u8` → store: nested/flat layout capture, identity resolution)
  - refs: `specs/nml-import/spec.md`, design.md D8
  - verify: fixture tests cover nested and flat directory layouts
- [x] 3.5 Implement the NML exporter (store → sandbox rebuild: collection matching, `PRIMARYKEY` references, backup + reload validation)
  - refs: `specs/nml-import/spec.md`, design.md D8
  - verify: fixture test rebuilds the sandbox from store state with backup and post-save validation

## 4. Services, config, CLI

- [x] 4.1 Implement import/export orchestration services with structured summaries over the adapter contract
  - refs: `specs/playlist-sync-framework/spec.md`, design.md D6
  - verify: unit tests cover summary counts and warning propagation for both commands
- [x] 4.2 Restructure config to format-based sections (`[library]`, `[store]`, `[nml]`, `[m3u]`) with per-command CLI overrides and update the example config template
  - refs: `specs/playlist-sync-framework/spec.md`, design.md D7
  - verify: unit tests cover section validation, missing-field errors, and override precedence
- [x] 4.3 Replace the CLI with `import --format` / `export --format` commands (pure store-only export, empty-store fail-fast, unknown-format error)
  - refs: `specs/playlist-sync-framework/spec.md`, design.md D6
  - verify: CLI tests cover both commands, empty-store error, and unknown-format error

## 5. Tests, docs, validation

- [x] 5.1 Adapt the existing test suite to the two-command flow and add store round-trip and invertibility tests; full suite green
  - refs: `specs/nml-import/spec.md` (invertibility), `specs/nml-export/spec.md`
  - verify: `uv run pytest` passes with no skipped or removed behavioral coverage
- [x] 5.2 Update README.md for the new command surface, config sections, and store behavior
  - refs: `README.md`, `traktor-m3u-sync.example.toml`
  - verify: README documents `import`/`export --format` usage and the `[store]` section
- [x] 5.3 Run full validation and strict OpenSpec validation
  - refs: `justfile`
  - verify: `nix develop -c bash -lc 'uv sync --dev >/dev/null && just check'` passes and `openspec validate playlist-store --type change --strict` reports zero errors

## 6. Module alignment (folded in after review)

- [x] 6.1 Align the NixOS module with the format-based config and `--format` CLI: render `[library]`/`[store]`/`[nml]`/`[m3u]` sections, per-service format selection with `--format` on exec lines, updated assertions and module-eval fixture, and matching docs
  - refs: `nix/modules/traktor-m3u-sync.nix`, `flake.nix`, `docs/nix-deployment.md`, design.md D7
  - verify: `nix flake check` exercises the new module surface; a module-rendered config loads through the current config loader
