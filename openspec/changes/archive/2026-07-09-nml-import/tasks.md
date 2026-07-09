## 1. Add import foundations

- [x] 1.1 Extend config loading with an `[import]` section, import-specific overrides, and sandbox/import-path validation.
- [x] 1.2 Add M3U reading support and any shared import-side data models needed for ordered playlist reconstruction.
- [x] 1.3 Extend path translation with the reverse M3U-to-Traktor direction and collection-path normalization for import matching.

## 2. Implement sandbox import behavior

- [x] 2.1 Build collection-entry lookup and matching logic that resolves imported tracks back to existing NML collection entries.
- [x] 2.2 Implement sandbox folder discovery/creation and deterministic rebuild of nested or flat playlist structures under that sandbox.
- [x] 2.3 Implement safe NML write-back with backup-before-write and post-save reload validation.
- [x] 2.4 Implement structured warning and summary reporting for matched tracks, skipped tracks, and playlist counts.
- [x] 2.5 Add the `traktor-m3u-sync import` CLI flow with config loading and CLI override support.

## 3. Validate supported round-trip behavior

- [x] 3.1 Add fixture-driven tests for M3U parsing, reverse path mapping, unmatched-track handling, flat vs nested hierarchy, and sandbox rebuild behavior.
- [x] 3.2 Add supported-scope round-trip tests covering `nml -> m3u -> nml` playlist hierarchy, membership, and ordering.
- [x] 3.3 Update README, example config, and any affected canonical docs to describe import behavior, limits, and safety expectations.
- [x] 3.4 Run relevant project checks and strict OpenSpec validation for the completed import slice.
