## Why

Engine DJ 5.0 imports the generated iTunes XML track collection but does not expose its playlists. The completed `engine-sqlite-proof` change demonstrated that the existing store can instead rebuild ordered playlists directly in the real Engine 5.0 media database using stdlib `sqlite3`, matching all 874 current tracks without a native dependency.

## What Changes

- Add an export-only Engine DJ adapter selected with `export --format engine`.
- Read playlists only from the populated internal store and match tracks against existing rows in one configured Engine DJ media-drive `m.db`.
- Support Engine DJ schema 3.0.2 only, failing before writes on an unsupported schema, failed integrity check, or incompatible playlist structures.
- Rebuild one configured managed playlist subtree while preserving unrelated Engine playlists, track records, analysis data, artwork, cues, and other metadata.
- Preserve playlist hierarchy, membership, and order through Engine's `Playlist` and `PlaylistEntity` linked structures; warn and skip missing, ambiguous, or duplicate memberships.
- Publish safely only while Engine DJ is offline: mutate and validate a same-directory staged copy, retain an adjacent backup of the prior database, atomically replace the target, and restore the backup if post-publication validation fails.
- Add `[engine]` configuration and CLI overrides for the media database path, Engine track-path prefix, and managed-root name.
- Extend export dry-run, structured summaries, `--fail-on-warning`, documentation, tests, and the NixOS export service to support Engine DJ.
- Keep L: main-library mirroring, track insertion/discovery, Engine import, performance-data mutation, metadata enrichment, and libdjinterop/endjine runtime integration out of scope.

## Capabilities

### New Capabilities

- `engine-export`: Engine DJ 5.0 media-database matching, managed playlist rebuild, validation, warning, and publication behavior.

### Modified Capabilities

- `playlist-sync-framework`: Register Engine DJ as an export-only format with format-owned configuration.
- `sync-operations`: Rehearse Engine export against an isolated database copy and safely publish a validated mutable database target.
- `deployment-packaging`: Expose Engine DJ through the NixOS export service and rendered TOML configuration without enabling it for import.

## Impact

- Python: `formats/engine/`, configuration, export registry/service dry-run routing, CLI overrides, and production tests; proof-only code is promoted or removed rather than duplicated.
- Nix: export format enum, `[engine]` option rendering/assertions, module-evaluation coverage, and runtime path-permission documentation.
- Operations: the configured media database must already contain Engine track rows and must be offline and writable by the service identity; the application does not coordinate the Windows VM or hard-code host paths/groups.
- Dependencies: no new runtime dependency; stdlib `sqlite3`, `shutil`, temporary files, and `os.replace` are sufficient. Implementation should follow archival/sync of the completed `service-identity` change because both touch the module and deployment documentation.
