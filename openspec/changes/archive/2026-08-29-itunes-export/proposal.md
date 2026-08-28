# Proposal: itunes-export

## Why

The playlist-store framework (see `playlist-store`) made every export target a single adapter against the frozen `Exporter` contract. The first new modality is iTunes XML: Navidrome M3U playlists imported into the store need to reach DJ software, and Engine DJ (the primary consumer), djay Pro, and VirtualDJ all read Apple's `iTunes Music Library.xml` natively. The format is stdlib-parseable (`plistlib`), so the exporter adds zero dependencies and proves the adapter contract generalizes beyond the NML/M3U pair.

## What Changes

- New `formats/itunes/` adapter package with an `Exporter` implementation: render store state to an iTunes-compatible XML plist (`iTunes Music Library.xml` shape) via stdlib `plistlib`.
- `export --format itunes` command support: reads only the store, fails fast on an empty/uninitialized store, same structured summary/warning surface as other exporters.
- Config: `[itunes]` section (`output_file`, `base_path`) where `base_path` is the library root used to build absolute track `file://` Locations from library-relative track identities.
- NixOS module: export-only iTunes support mirroring the `[itunes]` TOML section; import remains limited to source formats.
- Track Locations are absolute `file://` URIs built from `base_path` + identity with `Path.as_uri()`; `Total Time` in milliseconds; stable generated Track IDs and uppercase 16-hex Persistent IDs derived deterministically from track identity so repeated exports are idempotent.
- Playlist folder hierarchy mirrored: stored folder paths become iTunes folder playlists (`Folder = true`, `All Items = true`, stable folder Persistent IDs, children referencing `Parent Persistent ID`); smart-playlist fields never emitted.
- Referential integrity by construction: every playlist item references a Track ID present in `Tracks`.
- File existence is not required to export: the CLI checks generated Locations against the local filesystem and reports missing files as structured warnings in the summary (supports detached/dev exports; never blocks).
- README/config template/docs updated for the new modality.

## Capabilities

### New Capabilities

- `itunes-export`: the iTunes XML exporter adapter behavior — plist structure, Location URL construction, stable ID generation, folder mirroring, referential integrity, and the existence-check warning policy.

### Modified Capabilities

- `playlist-sync-framework`: the format-based configuration contract gains the `[itunes]` section and the export command surface gains `itunes` as a supported export format.
- `deployment-packaging`: the NixOS module's export surface gains iTunes while retaining separate import/export oneshots.

## Impact

- **Code**: new `src/traktor_m3u_sync/formats/itunes/` (writer + exporter); `config.py` gains `[itunes]` section + CLI override; `cli.py`/`services/` register the new export format.
- **Dependencies**: none (stdlib `plistlib`).
- **Config**: new `[itunes]` section documented in `traktor-m3u-sync.example.toml`.
- **Nix module**: export format/options/rendering and module-eval fixture gain iTunes support; import rejects it at evaluation time.
- **Tests**: synthetic-fixture tests for plist structure, ID stability, URL encoding, folder mirroring, referential integrity, and warning policy.
- **Deferred**: iTunes XML import (reverse direction), Engine DJ direct DB adapter, per-consumer validation against real hardware (Engine DJ import pass is a live-testing follow-up).
