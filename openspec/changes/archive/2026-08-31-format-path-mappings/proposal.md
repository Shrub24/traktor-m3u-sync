## Why

The store-mediated bridge still requires a global Traktor root for M3U-only and iTunes-only workflows, and iTunes export conflates the worker's local filesystem path with the consumer's file-URI path. A Linux worker therefore cannot render the Windows-style `file://localhost/M:/...` locations required by the iTunes/Engine consumer.

## What Changes

- **BREAKING** Remove the global `[library]` root table. Move NML and M3U roots into their owning format sections so unselected adapters impose no configuration requirement.
- Make NML's `library_root` required only for NML import or export; make M3U's `library_root` required only for M3U import or export.
- Remove the M3U export dependency on `TraktorPathMapping`; each adapter owns its own mapping.
- **BREAKING** Replace `[itunes].base_path` with required consumer-facing `location_base` (a full absolute `file:` URI) and optional worker-facing `check_base_path` for missing-file warnings.
- Add a pure URI mapping that safely appends library-relative paths with RFC-compatible percent encoding and supports empty, `localhost`, and UNC authorities.
- Render the same URI mapping for iTunes track Locations and Music Folder; update NixOS options, CLI overrides, examples, docs, and tests.

## Capabilities

### New Capabilities
- `format-path-mappings`: Adapter-owned path rendering and consumer-facing file-URI mapping.

### Modified Capabilities
- `path-translation`: Replace direct global-root translation requirements with format-owned library-root normalization.
- `itunes-export`: Configure independent local checking and consumer URI rendering for iTunes locations.
- `playlist-sync-framework`: Load format-owned path configuration without a required global library-root table.
- `deployment-packaging`: Render and validate format-owned roots and iTunes URI mapping through the NixOS module.

## Impact

- **Code:** config dataclasses/loading, NML and M3U path mappings, M3U and iTunes exporters, service factories, CLI overrides, and URI helper.
- **Nix:** module option tree, TOML rendering, assertions, and module-eval fixture.
- **Configuration:** existing `[library]`, `[nml]`, `[m3u]`, and `[itunes]` path fields are replaced as described above.
- **Documentation/tests:** example TOML, README, deployment guide, architecture/plan, capability specs, and cross-platform URI/config regression coverage.
