## Why

The repository is now bootstrapped, but it still has no functional sync behavior. The next highest-value slice is a safe export path from Traktor `collection.nml` to UTF-8 `.m3u8` playlists so users can materialize playlist state outside Traktor and validate path translation, playlist traversal, and reporting before tackling the riskier NML write/import path.

## What Changes

- Add the first functional export workflow that reads Traktor `collection.nml` and writes UTF-8 `.m3u8` playlists.
- Add typed NML loading using `traktor-nml-utils` and export-oriented playlist tree traversal.
- Add path translation from Traktor `PRIMARYKEY` or reconstructed `LOCATION` into M3U-side paths using TOML-configured library roots.
- Add export-specific configuration and CLI wiring with config + CLI overrides for `collection_path` and `output_dir`.
- Add structured warning/summary output for skipped smartlists and export anomalies.
- Add synthetic-fixture tests for export behavior, path translation, naming sanitization, and playlist hierarchy handling.

## Capabilities

### New Capabilities
- `nml-export`: Export Traktor playlists from `collection.nml` to UTF-8 `.m3u8` files, including playlist traversal, output hierarchy, and export reporting.
- `path-translation`: Translate track paths between Traktor NML path structures and M3U-side library roots for export behavior.

### Modified Capabilities
- None.

## Impact

- Adds runtime dependency on `traktor-nml-utils` and its transitive XML model stack.
- Expands the Python package beyond the bootstrap CLI placeholder with export, config, and path translation modules.
- Adds new CLI surface for export operations and new tests/fixtures for functional coverage.
- Establishes the first domain-level behavior future import and reporting changes will build on.
