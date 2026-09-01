## 1. Prerequisites and canonical direction

- [x] 1.1 Archive and sync the completed `service-identity` change before editing its shared module/docs surfaces; verify `openspec list` no longer reports it active and all main specs validate strictly.
  - notes: Keep the completed `engine-sqlite-proof` artifacts available as implementation evidence until production promotion is reconciled.

- [x] 1.2 Update `ARCHITECTURE.md` and `PLAN.md` from deferred Engine support to the M-only direct-SQLite production boundary; verify they state existing-track matching, managed-subtree ownership, offline publication, and deferred L mirroring.
  - refs: `proposal.md`, `design.md` D1-D5
  - delegate: `DocWriter`

## 2. Engine adapter and safe publication

- [x] 2.1 Promote the proof writer into production Engine modules implementing schema/integrity gates, configured path matching, managed hierarchy rebuild, linked ordering, orphan checks, and structured skip warnings; verify focused writer tests cover idempotency, missing/ambiguous tracks, duplicate memberships/labels, and rollback without modifying Engine track/performance rows.
  - refs: `specs/engine-export/spec.md`, `design.md` D1-D4 and D9
  - delegate: `CoderAgent`

- [x] 2.2 Implement same-directory staging, one retained adjacent backup, mode-preserving atomic replacement, detectable-active-sidecar rejection, cleanup, post-publication validation, and atomic backup restoration; verify failure-injection tests leave the prior target unchanged or restored at every pre/post-publication failure point.
  - refs: `specs/sync-operations/spec.md`, `design.md` D5
  - delegate: `CoderAgent`, `TestEngineer`

- [x] 2.3 Implement `EngineExporter.write()` with shared `SyncResult` counts and `AdapterWarning` values and remove the argparse proof surface rather than retaining parallel implementations; verify exporter tests report matched tracks, playlists, memberships, and each skip reason.
  - refs: `specs/engine-export/spec.md`, `design.md` D6 and D9
  - delegate: `CoderAgent`

## 3. Application and deployment integration

- [x] 3.1 Add optional `[engine]` config with `database_path`, default `track_path_prefix = ".."`, and default `managed_root = "Playlist Sync"`; wire `--engine-database`, `--engine-track-prefix`, and `--engine-managed-root`, export registry selection, and Engine dry-run copy isolation; verify non-Engine commands require no Engine config and service/CLI tests prove dry-run leaves target, backup, and store unchanged.
  - refs: `specs/playlist-sync-framework/spec.md`, `specs/sync-operations/spec.md`, `design.md` D6-D7
  - delegate: `CoderAgent`, `TestEngineer`

- [x] 3.2 Extend the NixOS module with export-only `engine` selection and `[engine]` rendering/assertions while preserving `configFile`, `extraArgs`, and service identity behavior; verify module evaluation invokes the packaged config loader and rejects Engine import or missing generated Engine settings.
  - refs: `specs/deployment-packaging/spec.md`, `design.md` D8
  - delegate: `OpenDevopsSpecialist`

- [x] 3.3 Update `README.md`, `traktor-m3u-sync.example.toml`, and `docs/nix-deployment.md` with Engine config, M-only scope, adjacent backup, offline Engine DJ requirement, operator-managed permissions, dry-run, and rollback; verify the example TOML loads and no docs claim L mirroring, track insertion, or analysis mutation.
  - refs: `proposal.md`, `design.md` D2-D8
  - delegate: `DocWriter`

## 4. Verification and live acceptance

- [x] 4.1 Run focused review plus the complete local gate (`just check`, runtime package build, module evaluation, `git diff --check`, and strict change/spec validation); verify `CodeReviewer` reports no blocking correctness or data-safety findings.
  - delegate: `CodeReviewer`, `BuildAgent`

- [x] 4.2 With Engine DJ closed (the Windows VM may remain running) and the live M: database backed up, deploy and run dry-run then real export on home-forge; verify Engine DJ 5.0 opens the database and displays one `Playlist Sync` root containing the current twelve playlists with expected hierarchy, membership, and order, then confirm the retained backup can restore the prior DB.
  - depends: 4.1
  - verify: CLI/service summaries, SQLite integrity/reference checks, and user-confirmed Engine DJ UI acceptance

- [x] 4.3 Reconcile any live-test drift into proposal/spec/design/docs, retire `engine-sqlite-proof` with its superseded delta excluded from main specs, rerun `openspec validate engine-export --type change --strict` and `openspec validate --specs --strict`, and verify every task is complete before handoff/archive.
  - depends: 4.2
