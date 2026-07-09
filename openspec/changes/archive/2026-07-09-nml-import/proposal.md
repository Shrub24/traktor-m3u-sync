## Why

The project can now export Traktor playlists to UTF-8 `.m3u8`, but it still lacks the inverse workflow needed to bring edited playlists back into `collection.nml`. Adding a sandboxed import slice now enables the first practical round-trip toward the supported invertibility goal: an `nml -> m3u -> nml` cycle should recreate the same standard playlist hierarchy, membership, and ordering for the supported scope.

## What Changes

- Add an M3U-to-NML import workflow that reads `.m3u8` playlists and rebuilds a managed sandbox folder inside Traktor's playlist tree.
- Add reverse path translation and collection-entry matching so imported M3U paths resolve back to existing Traktor collection entries.
- Add backup-before-write and reload validation around NML mutation so import remains conservative and deterministic.
- Add import-specific config and CLI wiring, including support for both nested playlist directories and flat M3U directories.
- Add fixture-driven tests for M3U parsing, sandbox rebuild behavior, reverse path mapping, unmatched-track warnings, and supported round-trip behavior.

## Capabilities

### New Capabilities
- `nml-import`: Import `.m3u8` playlists into a managed Traktor sandbox folder while preserving supported playlist structure, membership, and ordering.

### Modified Capabilities
- `path-translation`: Extend path translation requirements to cover the reverse M3U-to-Traktor direction used during import.

## Impact

- Adds new import modules for M3U reading, sandbox rebuild orchestration, and safe NML write-back.
- Expands config parsing and CLI surface with import workflow options.
- Extends path translation beyond export-only behavior.
- Introduces higher-risk NML mutation logic, backup handling, and round-trip validation tests.
