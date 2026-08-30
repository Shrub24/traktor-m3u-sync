## Context

See proposal.md. Track identity is already a library-relative POSIX path in the store, but configuration and one M3U exporter still retain a pairwise NML/M3U mapping. iTunes currently uses a host `Path` both to check files and construct Locations, which cannot express the consumer's URI namespace.

## Goals / Non-Goals

**Goals:**
- Make each adapter own only the root or URI mapping it needs.
- Render RFC 8089-compatible consumer file URIs independently of the worker host.
- Preserve missing-local-file warnings when a local check path is configured.
- Keep a failed or unselected adapter from imposing configuration on another format.

**Non-Goals:**
- Add an Engine DJ database adapter, URI schemes other than `file:`, path-profile selection, or automatic Windows-drive discovery.
- Preserve the retired `[library]` or `[itunes].base_path` configuration contract.
- Change store identity, introduce cross-format merging, or alter export safety controls.

## Decisions

### D1: Roots belong to their format section

`[nml].library_root` is a Windows-native NML mapping root and `[m3u].library_root` is the M3U mapping root; neither is global configuration. The shared `LibraryConfig` and `[library]` table are removed. Per-command validation requires only the selected adapter's fields.

This is preferred over merely making `traktor_root` nullable because it removes the misleading global type and the M3U export's dependency on the NML mapper. It is preferred over retaining a generic root profile because one concrete root per adapter is sufficient today.

### D2: iTunes has separate consumer rendering and worker checking bases

`[itunes].location_base` is a required, complete absolute `file:` URI prefix for consumer Locations and Music Folder. `[itunes].check_base_path` is optional and is a local worker filesystem path used only to issue `file_missing` warnings. A missing check base suppresses that warning rather than guessing consumer reachability.

This replaces the overloaded `base_path`. A full URI value is preferred over independent host/path options: `file://localhost/M:/Music` is self-describing, supports UNC authorities, and has no accidental Linux `Path` interpretation.

### D3: Use a pure file-URI mapper

A small `paths/uri.py` mapper validates a `file:` base with an absolute URI path, appends the stored POSIX relative path, and percent-encodes path text with UTF-8 while preserving `/` and drive-letter `:`. It never calls `Path.as_uri()` and never stats the consumer path.

`file:///srv/music`, `file://localhost/M:/Music`, and `file://server/share/music` are supported. Query, fragment, and non-`file` bases are rejected at the configuration boundary. `Music Folder` is the normalized base with a trailing slash.

### D4: M3U uses its own mapping

`M3uExporter` receives `M3uPathMapping` and uses its forward render method. `TraktorPathMapping.render_for_m3u` is removed. NML import/export remain the only consumers of `TraktorPathMapping`.

### D5: Configuration and Nix are deliberately breaking

The command overrides become `--location-base` and `--check-base-path`; `--base-path` is removed. Nix renders the new format-owned tables and validates selected-format fields only. No compatibility aliases are kept because there is no deployed contract yet and aliases perpetuate the ambiguity.

## Risks / Trade-offs

- [Consumer URI is syntactically valid but Engine-specific behavior differs] → Test the generated XML through Engine DJ's native iTunes integration after homelab deployment.
- [No local check path hides unavailable consumer files] → The option is explicitly named and optional; operators can opt into warnings with their worker mount.
- [Breaking config] → Update example, docs, Nix module, and structured errors together; require explicit migration before any command runs.
- [URI encoding edge cases] → Cover spaces, `#`, `%`, Unicode, drive roots, localhost, and UNC in unit tests.

## Migration Plan

1. Replace `[library]` roots with `[nml].library_root` and `[m3u].library_root` as needed by selected formats.
2. Replace `[itunes].base_path` with `location_base`; optionally add `check_base_path` pointing at the worker's mounted library.
3. Update Nix module options in the same switch; no state migration is required because the SQLite store holds relative paths only.
4. Roll back by returning configuration and package input to the prior revision; exports are atomically published.
