## 1. Add export foundations

- [x] 1.1 Add `traktor-nml-utils` to project dependencies and confirm the dependency set works in the existing Python 3.14 / Nix workflow.
- [x] 1.2 Create the Phase 1 export module layout (`config.py`, `nml_reader.py`, `playlist_tree.py`, `pathmap.py`, `m3u_writer.py`, `export_service.py`) and wire package exports as needed.
- [x] 1.3 Add export config models and loading for `[library]` and `[export]` TOML sections, with CLI-overridable `collection_path` and `output_dir` fields.

## 2. Implement export behavior

- [x] 2.1 Implement NML loading through `traktor-nml-utils` and extract playlist/tree structures needed for standard playlist export.
- [x] 2.2 Implement path translation that prefers `PRIMARYKEY`, falls back to reconstructed `LOCATION`, and supports absolute or relative `m3u_root` mappings.
- [x] 2.3 Implement playlist hierarchy export that omits `$ROOT`, minimally sanitizes filesystem-invalid names, and skips smartlists with structured warnings.
- [x] 2.4 Implement UTF-8 `.m3u8` writing with ordered entries and `#EXTM3U` / `#EXTINF` output.
- [x] 2.5 Add the `traktor-m3u-sync export` CLI flow and structured stdout/stderr summary output.

## 3. Validate and document the export slice

- [x] 3.1 Add synthetic-fixture tests covering config loading, path translation, playlist hierarchy, smartlist skipping, and M3U8 output behavior.
- [x] 3.2 Update README and any affected canonical docs so the new export command, config model, and current phase limitations are documented.
- [x] 3.3 Run the relevant project checks and `openspec validate --strict` for the completed change.
