## 1. Provenance and reports

- [x] 1.1 Record `source_format` + `imported_at` (UTC) in store `meta` on every rebuild; fail fast on provenance-less stores; surface both in export summaries and reports
  - refs: `src/traktor_m3u_sync/store/`, `src/traktor_m3u_sync/services/__init__.py`
  - verify: old store without provenance rows fails with re-import directive; export summary shows origin
- [x] 1.2 Add `--report-file PATH` to import/export writing the JSON run report; warn-only on write failure; never change exit status
  - verify: report counts/warnings match stdout; unwritable path warns without failing
- [x] 1.3 Emit `empty_import_source` warning when a non-empty source yields zero playlists
  - verify: strict mode exits `2`; empty-dir import stays silent-success

## 2. Robustness and failure hooks

- [x] 2.1 Set `busy_timeout` on store connections for concurrent rebuild-vs-read
  - verify: concurrent import/export no longer raises immediate `SQLITE_BUSY`
- [x] 2.2 Add per-job `onFailure` Nix option rendered as `OnFailure=`, validated like `onSuccess`, plus per-job `reportFile` rendered as `--report-file`
  - verify: `nix flake check` fixture proves wiring + invalid refs fail eval
- [x] 2.3 Add Engine `check_base_path` (config, `--engine-check-base-path`, Nix `engine.check_base_path`, warn-only `file_missing` mirroring iTunes) and lock absolute-prefix matching with a regression test
  - verify: absent file warns without skipping; `M:/library` + `../library` prefixes match

## 3. Docs and validation

- [x] 3.1 Document report file, provenance fields, `onFailure`, and Engine `check_base_path` in example TOML + `docs/nix-deployment.md`; reconcile PLAN.md
  - verify: examples match implementation; no canonical doc describes removed behavior as current
- [x] 3.2 Run `just check`, `nix flake check`, runtime package build, focused review with no unresolved high-severity findings, and `openspec validate sync-reporting --strict`
  - verify: all green
