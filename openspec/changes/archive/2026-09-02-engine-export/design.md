## Context

See `proposal.md` for motivation. `engine-sqlite-proof` established the exact transferable core against copies of the home-forge Engine DJ 5.0 databases: schema 3.0.2, 874/874 matches from store paths to `M:\Engine Library\Database2\m.db` as `../<rel_path>`, twelve playlists, 1,085 representable memberships, and Engine-native linked ordering. The Windows VM maps the main Engine library as L: and canonical media as M:. Engine mirrored the manual `Agent Fixture` into both databases, but v1 deliberately targets only M:.

The target database contains user-owned Engine metadata and is not disposable generated output. Engine DJ and the Linux exporter must never write it concurrently. The default non-root service identity also needs downstream group or ACL access; the generic module must not encode home-forge paths or permissions.

## Goals / Non-Goals

**Goals:**

- Promote the proven SQLite playlist writer into the shared exporter contract without duplicating proof logic.
- Preserve Engine-owned data and unrelated playlists while making one managed subtree idempotent.
- Give every real and dry-run write the same validation and warning behavior.
- Leave a known prior database beside the target and make publication recoverable.

**Non-Goals:**

- Mirroring L: and M: databases or providing a multi-target transaction.
- Discovering or inserting tracks, scanning media, or mutating analysis, waveform, cue, beat-grid, artwork, or tag data.
- Supporting Engine schemas other than 3.0.2, importing from Engine, or integrating libdjinterop/endjine.
- Starting, stopping, or locking the Windows VM; timers and ordering remain downstream policy.

## Decisions

### D1: Keep direct SQLite as the production implementation

The adapter uses stdlib `sqlite3` and Engine's existing schema and triggers. It never creates an Engine database or replays schema DDL. The proof already exercises the exact playlist primitives against the real schema, whereas libdjinterop requires an unreleased post-0.27.1 revision plus a C++ bridge and endjine has no complete playlist-creation CLI or Python API. `libdjinterop` and endjine remain reference implementations; neither becomes a runtime dependency.

### D2: Target only the M: media database in v1

`[engine].database_path` names one media-drive `m.db`. That database contains the 874 Engine track rows and is the artifact consumed with the media drive; the proof works against it directly. L: mirroring would add a second mutable file, foreign UUID references, and a non-atomic cross-file publication boundary before live behavior proves it necessary.

### D3: Match existing tracks and never synthesize them

`[engine].track_path_prefix` defaults to `..`. The path mapper normalizes separators and compares casefolded `<prefix>/<store-relative-path>` values to existing `Track.path` rows. Missing, unresolved, ambiguous, and duplicate memberships warn and skip. This keeps track discovery and all analysis ownership inside Engine DJ.

### D4: Own one explicit playlist subtree

`[engine].managed_root` defaults to `Playlist Sync`. Export deletes and rebuilds only that top-level subtree. Engine's own playlist IDs and linking triggers remain authoritative; the writer constructs and validates sibling `nextListId` and membership `nextEntityId` chains, UUID references, hierarchy, counts, and orphan absence before commit. A duplicate configured root or unrepresentable duplicate playlist label fails the staged write rather than guessing ownership.

### D5: Stage, back up, validate, and atomically publish one database

The exporter first validates the configured target read-only, requires Engine's verified rollback-journal (`DELETE`) mode, and rejects detectable active sidecars. WAL mode fails before staging rather than being copied without its sidecars or silently normalized. It creates a same-directory temporary copy preserving mode, mutates that copy in one `BEGIN IMMEDIATE` transaction, closes and syncs it, and reopens it read-only for structural and integrity validation. It then atomically refreshes `<database-name>.playlist-sync.bak` from the validated current target and uses `os.replace` to publish the stage, syncing the containing directory after replacements. The replacement inode is owned by the worker identity and gets its group from the target directory, so downstream SGID/group/ACL policy must keep it accessible to Engine. The backup remains after success. A post-publication validation failure restores the backup through another same-directory staged replacement.

This is intentionally stronger than the proof's caller-owned-copy contract and distinct from M3U/iTunes generated-file publication. No application-level check can prove Engine DJ is closed, so closing the application remains an explicit operator precondition in addition to sidecar checks; stopping the VM is sufficient but not required.

### D6: Reuse the shared export controls

`EngineExporter.write(playlists)` returns `SyncResult` and structured `AdapterWarning` values. `--fail-on-warning` works without Engine-specific exit logic. `_dry_run_config` copies the configured database into an isolated temporary directory and points a replaced `EngineConfig` at it; the same exporter then executes normally without touching the configured database or backup.

### D7: Keep Engine configuration format-owned

`EngineConfig` is optional at config-load time and required only for `export --format engine`:

- `database_path`: existing M: media `m.db` path, required;
- `track_path_prefix`: Engine path prepended to store-relative paths, default `..`;
- `managed_root`: owned top-level playlist name, default `Playlist Sync`.

CLI overrides use `--engine-database`, `--engine-track-prefix`, and `--engine-managed-root`. No backup-path or schema-version knobs are exposed because both are invariants, not operator policy.

### D8: Extend the existing NixOS export surface, not service topology

The module adds `engine` only to the export enum and renders `[engine]` with matching options/assertions. The existing oneshot, `extraArgs`, `configFile`, service identity, and downstream orchestration seams remain unchanged. Documentation tells operators to grant the configured service identity write access through their own group/ACL policy and to close Engine DJ before export.

### D9: Promote and retire proof-only surfaces

Reusable matching, writing, and validation move from `proof.py` into production Engine modules. The argparse proof entry point and proof-specific defaults are removed; focused tests remain and expand to publication, dry-run, adapter-result, and failure-injection coverage. The proof change remains historical evidence rather than a parallel implementation.

## Risks / Trade-offs

- **Engine opens the DB during export** → document an offline precondition, reject detectable journal/WAL activity, stage all writes, retain a backup, and fail fast; the module does not attempt VM lifecycle control.
- **Atomic replace crosses a Windows/shared-filesystem boundary with surprising semantics** → stage in the target directory, require `os.replace`, preserve mode, and make the home-forge live acceptance test a completion gate.
- **M-only output is not reflected in L:** → treat M as the v1 deliverable; add paired mirroring only after verified consumer need and a separately designed recovery model.
- **Schema 3.0.2 changes in a future Engine release** → reject the new schema and require an explicit adapter update backed by a fresh fixture; never guess compatibility.
- **Engine has not discovered a source track** → warn and skip rather than inserting incomplete track or performance rows.
- **Backup retention is one generation** → sufficient immediate rollback without accumulating unbounded database copies; downstream backup policy may retain more history.

## Migration Plan

1. Archive and sync the completed `service-identity` change before editing the shared Nix module and deployment guide.
2. Deploy the package and module config with `[engine].database_path` pointing at the M: media database and `playlist-sync` granted operator-managed write access.
3. Close Engine DJ (or stop the Windows VM), run dry-run, then run export; retain the generated adjacent backup.
4. Open Engine DJ and verify the managed root, twelve playlists, hierarchy, memberships, and order against the source M3Us.
5. If acceptance fails, stop Engine, restore the retained backup atomically, and keep the adapter disabled while artifacts are reconciled.
