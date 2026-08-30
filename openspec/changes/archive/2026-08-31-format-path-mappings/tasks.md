## 1. Format-owned configuration and mappings

- [x] 1.1 Replace the global `[library]` configuration with `[nml].library_root` and `[m3u].library_root`; add selected-format validation and `--location-base` / `--check-base-path` overrides, verified by config and CLI regression tests.
- [x] 1.2 Route M3U import and export through `M3uPathMapping` only, retain NML roots only in NML mapping, and remove the cross-format render helper; verify M3U-to-iTunes succeeds with no NML configuration.

## 2. Consumer URI rendering

- [x] 2.1 Add a pure `file:` URI mapping that validates an absolute configured base and appends library-relative paths with correct UTF-8 percent encoding; verify POSIX, `localhost` drive, UNC, spaces, `%`, `#`, and Unicode cases.
- [x] 2.2 Render iTunes Locations and Music Folder from `location_base` while using optional `check_base_path` only for worker-side warnings; verify divergent `/srv` check and `file://localhost/M:/` output bases plus omitted-check behavior.

## 3. NixOS and documentation

- [x] 3.1 Move NixOS options and TOML rendering to format-owned roots and iTunes URI/check fields; verify module evaluation supports M3U-to-iTunes without NML settings and validates selected-format requirements.
- [x] 3.2 Update the example TOML, README, deployment guide, architecture, plan, and path-translation guidance with the breaking configuration migration and Engine/iTunes URI form.

## 4. Validation

- [x] 4.1 Add end-to-end M3U import to iTunes export regression coverage for a Linux worker check root and `file://localhost/M:/...` consumer Locations.
- [x] 4.2 Run `nix develop -c bash -lc 'uv sync --dev >/dev/null && just check'`, `nix flake check`, runtime package build, and `openspec validate format-path-mappings --type change --strict`.
