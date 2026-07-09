## Context

The repository now supports NML-to-M3U export, path translation in the export direction, and structured operational reporting. The next change is the first write-capable workflow: reading `.m3u8` playlists and rebuilding a managed sandbox folder inside Traktor `collection.nml`.

This change is riskier than export because it mutates Traktor state. The design therefore needs to stay deliberately conservative: modify only one managed subtree, back up before write, validate after save, and scope invertibility to standard playlist hierarchy, membership, and ordering rather than full NML metadata fidelity.

Constraints already established by the repo:
- Traktor is Windows-first on the import side.
- `traktor-nml-utils` is the primary NML model and serializer.
- Smartlists and non-playlist metadata are out of scope.
- Structured stdout/stderr reporting is the current operational reporting style.

## Goals / Non-Goals

**Goals:**
- Import `.m3u8` playlists into a managed sandbox folder in `collection.nml`.
- Support both nested M3U directory structures and flat M3U directories.
- Match tracks back to existing collection entries using reversible path translation and collection lookup.
- Preserve supported playlist hierarchy, membership, and ordering across the round-trip path.
- Ensure safe write behavior through backup-before-write and reload validation.
- Reuse as much of the existing config, path, CLI, and warning/reporting shape as practical.

**Non-Goals:**
- Sync or reconstruct cues, grids, analysis, ratings, or other non-playlist metadata.
- Perform fine-grained merges outside the managed sandbox.
- Import or synthesize smartlists.
- Guarantee byte-identical or metadata-complete NML round-trips.
- Add deployment automation, systemd wiring, or live homelab orchestration in this change.

## Decisions

### 1. Use a strict sandbox rebuild model
- **Decision:** Import will locate or create one configured sandbox folder under `$ROOT`, clear its children, and rebuild it entirely from current M3U state.
- **Rationale:** This is deterministic, idempotent, and aligns with the previously agreed overwrite model.
- **Alternatives considered:**
  - Fine-grained merge into existing playlists: rejected as too risky and ambiguous for a first write path.
  - Writing playlists outside a sandbox: rejected because it broadens blast radius.

### 2. Support nested and flat M3U layouts with explicit semantics
- **Decision:** Nested M3U directories map directly to nested Traktor folder nodes under the sandbox. Flat M3U directories import playlists directly under the sandbox root with no inferred hierarchy.
- **Rationale:** This supports both exported mirror layouts and externally managed flat playlist directories without hidden conventions.
- **Alternatives considered:**
  - Require nested layouts only: rejected because flat directories are a reasonable real-world source.
  - Infer hierarchy from filenames: rejected as fragile and non-obvious.

### 3. Match tracks through normalized collection-entry lookup
- **Decision:** Import will reverse-map each M3U path from `m3u_root` back into the Traktor library space, then match against a prebuilt collection index keyed by normalized `PRIMARYKEY`, with fallback to reconstructed `LOCATION` paths.
- **Rationale:** This keeps the import contract symmetric with export and avoids filename-only ambiguity until necessary.
- **Alternatives considered:**
  - Filename-only matching: rejected because collisions are too likely.
  - Direct filesystem probing only: rejected because import should operate against collection state first.

### 4. Write playlist entries as PRIMARYKEY references only
- **Decision:** Imported playlist entries will reference matched collection tracks by `PRIMARYKEY` and will not duplicate broader track metadata inside playlist nodes.
- **Rationale:** This is the smallest safe write surface and matches Traktor’s natural model of collection-owned track metadata.
- **Alternatives considered:**
  - Duplicating LOCATION/INFO/TITLE into playlist entries: rejected as unnecessary and higher risk.

### 5. Add backup-before-write and reload validation as mandatory workflow steps
- **Decision:** Before saving, import will write a timestamped backup next to `collection.nml`. After saving, it will reload the NML and verify that the sandbox subtree parses and has the expected playlist count.
- **Rationale:** The write path needs explicit safety rails because malformed NML can invalidate the collection.
- **Alternatives considered:**
  - Backup optional or manual: rejected for v1 import safety.
  - Parse-only reload validation: rejected because the sandbox structure also matters.

### 6. Keep sanitized-name mismatch as a documented limitation
- **Decision:** If exported playlist or folder names were sanitized for filesystem compatibility, import will use the on-disk names as-is and emit a warning where relevant rather than attempting heuristic reversal.
- **Rationale:** The user has accepted this as a low-priority limitation, and heuristic reversal would add ambiguity to the deterministic round-trip model.
- **Alternatives considered:**
  - Sidecar metadata files for original names: deferred.
  - Heuristic unsanitization: rejected as error-prone.

### 7. Extend the current config and CLI shape rather than introducing a second style
- **Decision:** Add an `[import]` TOML section and import CLI overrides while preserving the current config-loading and structured output conventions.
- **Rationale:** This keeps the operator experience symmetric with export and reuses proven bootstrap choices.
- **Alternatives considered:**
  - A separate import-only config file: rejected as needless fragmentation.

## Risks / Trade-offs

- **[NML mutation fragility]** → Mitigation: keep writes sandbox-local, use `traktor-nml-utils.save()`, add backup-before-write, and reload-validate immediately.
- **[Reverse path mapping edge cases]** → Mitigation: define normalization rules explicitly, build deterministic collection indexes, and treat mismatches as warnings where safe.
- **[Name round-trip loss for sanitized exports]** → Mitigation: document it as a limitation and emit warnings rather than guessing.
- **[False confidence from synthetic fixtures]** → Mitigation: include round-trip tests now and leave room for later anonymized real-NML fixtures.
- **[Blast radius from wrong sandbox targeting]** → Mitigation: default to a single explicit sandbox name, keep it configurable, and never mutate outside that subtree.

## Migration Plan

1. Add import config, M3U reader, reverse path translation, and sandbox rebuild modules.
2. Add the `import` CLI flow with backup and reload validation.
3. Add fixture-driven tests, especially export-to-import round-trip checks for supported scope.
4. Validate with project checks and strict OpenSpec validation.

Rollback remains straightforward at the code level, and runtime rollback is aided by the per-run backup file written before mutation.

## Open Questions

- Whether warning output should distinguish between sanitized-name limitations and track-match failures with separate codes.
- Whether the first import summary should also count playlists skipped because they contained zero matched tracks, or simply report them as written empty playlists.
- Whether later packaging/deployment work should also standardize a backup-directory convention instead of same-directory backup files.
