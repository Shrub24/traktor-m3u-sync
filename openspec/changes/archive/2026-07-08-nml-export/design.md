## Context

`traktor-m3u-sync` has completed repository bootstrap but has no functional sync behavior yet. The first implementation slice should prove that the project can safely read Traktor `collection.nml`, traverse playlist state, translate Traktor paths into M3U-side paths, and materialize `.m3u8` files with clear operational feedback.

This change introduces the first external domain dependency (`traktor-nml-utils`) and the first non-trivial domain modules in the Python package. It also establishes the export-oriented config model that later import work can build on without prematurely designing a full bidirectional sync engine.

Constraints and prior decisions already captured in canonical docs:
- Export is Phase 1 and should stay narrower than import.
- Smartlists are out of scope for this change and must be skipped with warnings.
- Library roots are singular per side: one Traktor library root and one M3U library root.
- Workflow I/O paths are direction-specific.
- Config is TOML with CLI override support.
- Export should omit `$ROOT`, preserve the remaining playlist hierarchy, and minimally sanitize filesystem-invalid names.
- Reporting should be structured in stdout/stderr with a clear summary, designed so later changes can extend it into file-based machine-ingestible reports.

## Goals / Non-Goals

**Goals:**
- Add a reliable export command that reads Traktor `collection.nml` and writes UTF-8 `.m3u8` playlists.
- Establish a minimal but explicit module layout for config loading, NML reading, playlist traversal, path translation, M3U writing, export orchestration, and CLI reporting.
- Use `PRIMARYKEY` as the preferred export path source, with reconstructed `LOCATION` as fallback.
- Support TOML config plus CLI overrides for `collection_path` and `output_dir`.
- Provide synthetic-fixture tests for the export path, including skipped smartlists, path mapping, hierarchy, and filename sanitization.

**Non-Goals:**
- Writing back to `collection.nml` or implementing any import logic.
- Supporting smartlist export semantics.
- Adding report files on disk, backup directories, or notification integrations.
- Adding real-world/anonymized smoke fixtures in this change.
- Designing a generalized rule engine for path mapping.

## Decisions

### 1. Keep the Phase 1 implementation modular but shallow
Use a small set of explicit modules rather than a deep package hierarchy:
- `config.py`
- `nml_reader.py`
- `playlist_tree.py`
- `pathmap.py`
- `m3u_writer.py`
- `export_service.py`
- CLI integration in `cli.py`

**Rationale:** This matches the documented architecture layers while keeping the first functional slice readable and easy to refactor.

**Alternatives considered:**
- A nested `domain/` and `services/` package tree: rejected as too much ceremony for the first feature.
- A single-file export implementation: rejected because path translation and reporting concerns would become tangled quickly.

### 2. Use singular library roots plus export-specific I/O paths
Config shape for this change:
```toml
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/path/to/collection.nml"
output_dir = "/path/to/playlists"
```
CLI flags MAY override `collection_path` and `output_dir`.

**Rationale:** Track-path translation and workflow I/O are different concerns. Singular library roots keep path mapping simple, while export-specific paths allow later import configuration without redesigning the model.

**Alternatives considered:**
- Shared path config for everything: rejected because it mixes track roots with workflow I/O.
- Separate import/export roots now: rejected as premature for Phase 1.

### 3. Prefer `PRIMARYKEY`, fall back to reconstructed `LOCATION`
For each track reference:
1. use `PRIMARYKEY.KEY` when present
2. otherwise reconstruct from `LOCATION.VOLUME` + `DIR` + `FILE`
3. normalize into the M3U-side path using configured roots

**Rationale:** `PRIMARYKEY` is the most direct full-path representation and reduces reconstruction ambiguity. `LOCATION` remains necessary as a fallback because NML data can vary.

**Alternatives considered:**
- Always use `LOCATION`: rejected because it increases separator and reconstruction risk.
- Hard fail when `PRIMARYKEY` is absent: rejected because export should be resilient when fallback data exists.

### 4. Skip smartlists with structured warnings
`SMARTLIST` nodes are excluded from Phase 1 export. The CLI SHALL emit structured warnings and include skipped smartlists in the final export summary.

**Rationale:** Silent skipping would be surprising, and full smartlist support is intentionally deferred.

**Alternatives considered:**
- Silent skip: rejected because it hides real omissions.
- Attempt export of smartlist contents: rejected because semantics are unclear and out of scope.

### 5. Use structured CLI reporting without a file report yet
Export output SHALL distinguish:
- success summary
- warning entries (e.g., skipped smartlists, unresolved path translations)
- per-run counts such as playlists written, tracks exported, warnings emitted

Warnings should be easy to ingest later by automated notification or recovery tooling, but Phase 1 does not write JSON/CSV report files.

**Rationale:** This keeps Phase 1 operationally useful while avoiding premature report format commitments.

**Alternatives considered:**
- Human-only freeform logs: rejected because later automation would be harder.
- JSON or CSV report files now: rejected because file-based reporting is a separate refinement concern.

### 6. Minimize filename sanitization
Playlist and folder names SHALL preserve source names as much as possible while sanitizing filesystem-invalid characters and omitting `$ROOT`.

**Rationale:** Users expect the exported structure to resemble Traktor closely, but the exporter must still produce valid files and directories.

**Alternatives considered:**
- Fail on invalid names: rejected because common characters should not block export.
- Aggressive normalization: rejected because it would make exported names drift too far from Traktor.

## Risks / Trade-offs

- **[`traktor-nml-utils` on Python 3.14]** → Verify compatibility early in implementation and adjust dependency pinning only if a real incompatibility is found.
- **[Path mapping ambiguity]** → Keep mapping simple in Phase 1 and cover representative edge cases with synthetic fixtures.
- **[Export reporting shape may evolve]** → Keep an internal summary model so future JSON/CSV output can build on it without rewriting the exporter.
- **[Playlist tree fidelity]** → Preserve folder hierarchy exactly except for omitting `$ROOT`; validate with fixture-based tests.
- **[Future import needs may differ]** → Separate library roots from export I/O now to reduce future redesign pressure.

## Migration Plan

1. Add the new dependency and functional modules.
2. Introduce export config loading and CLI command wiring.
3. Add synthetic fixtures and tests that lock in path translation, hierarchy, sanitization, and warning behavior.
4. Update user-facing docs to describe the new export command and its limitations.

Rollback is straightforward: revert the change before any later import work depends on the new export modules.

## Open Questions

- Whether `traktor-nml-utils` requires any Python 3.14 compatibility workaround in practice.
- Whether future reporting should first standardize on JSON or CSV once file-based reports are introduced.
