# Tasks: itunes-export

## 1. Adapter implementation

- [x] 1.1 Implement the iTunes XML writer (plist structure per design D2/D4: header keys, Tracks dict with string outer keys + integer Track IDs, Playlists array with item refs) via stdlib `plistlib`
  - refs: `specs/itunes-export/spec.md`, design.md D1, D2, D4
  - verify: unit tests assert exact plist structure for a synthetic store state
- [x] 1.2 Implement collision-safe deterministic ID generation (integer Track IDs from sorted identity order; uppercase 16-hex Persistent IDs from lossless identity/folder-path serialization)
  - refs: design.md D3
  - verify: unit tests prove stability across repeated renders and uniqueness across distinct identities, delimiter-like folder paths, and duplicate playlist names
- [x] 1.3 Implement Location construction (`base_path` join + `as_uri()` percent-encoding) with unresolvable-track skip-and-warn, and Total Time seconds→milliseconds conversion
  - refs: design.md D5
  - verify: unit tests cover URL encoding (spaces, `#`, unicode), unresolved skips with warnings, and ms conversion
- [x] 1.4 Implement folder mirroring (folder playlist entries with `Folder`/`All Items`/`Parent Persistent ID`, root playlists without parent ref)
  - refs: design.md D6
  - verify: unit test renders a nested folder hierarchy and asserts parent-child Persistent ID linkage
- [x] 1.5 Implement the existence check (post-render local filesystem check producing structured warnings, never blocking)
  - refs: design.md D7
  - verify: unit test with missing files emits warnings and still completes the export
- [x] 1.6 Implement the iTunes `Exporter` adapter wiring the above behind the shared contract, registered for `export --format itunes`
  - refs: `specs/itunes-export/spec.md`, design.md D8
  - verify: end-to-end test: import synthetic M3U → store → export itunes → parse output with `plistlib.load` and assert referential integrity + playlist contents

## 2. Config and CLI

- [x] 2.1 Add `[itunes]` config section (`output_file`, absolute `base_path`) with per-command validation and CLI overrides; update `traktor-m3u-sync.example.toml`
  - refs: `specs/playlist-sync-framework/spec.md`, design.md D8
  - verify: unit tests cover required-field and relative-base-path errors, override precedence, and M3U-only configs still loading without `[itunes]`
- [x] 2.2 Register the itunes export format in the CLI and update README/docs for the new modality
  - refs: design.md D8
  - verify: CLI test runs `export --format itunes` end-to-end; README documents the `[itunes]` section and command
- [x] 2.3 Extend the NixOS module with export-only iTunes support: separate import/export format enums, `[itunes]` options/rendering/assertions, module-eval fixture, and deployment docs
  - refs: `specs/deployment-packaging/spec.md`, design.md D9, `nix/modules/traktor-m3u-sync.nix`, `flake.nix`, `docs/nix-deployment.md`
  - verify: `nix flake check` validates an `export.format = "itunes"` module fixture and rejects iTunes as an import format

## 3. Validation

- [x] 3.1 Run full validation and strict OpenSpec validation
  - refs: `justfile`
  - verify: `nix develop -c bash -lc 'uv sync --dev >/dev/null && just check'` passes and `openspec validate itunes-export --type change --strict` reports zero errors
