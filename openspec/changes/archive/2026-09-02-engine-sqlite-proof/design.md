## Context

The live Engine DJ 5.0.0 media-drive database reports schema 3.0.2. Its native `Agent Fixture` playlist confirms that ordered membership is represented by `PlaylistEntity.nextEntityId`. The current project store contains 874 tracks, 12 playlists, and 1,086 memberships; all 874 store paths match existing Engine tracks as `../<rel_path>`. This experiment decides whether the later Engine adapter needs libdjinterop.

## Goals / Non-Goals

**Goals:**
- Prove direct stdlib SQLite transfer against copies of the real store and Engine database.
- Preserve Engine's generated schema, triggers, UUID, and sequence state.
- Leave one deterministic regression test.

**Non-Goals:**
- CLI, config, service, packaging, or adapter-contract integration.
- Track, cue, loop, beat-grid, waveform, artwork, or metadata-analysis writes.
- Mutation of the live home-forge database.

## Decisions

1. **Mutate an Engine-generated database copy.** Do not create or replay Engine's schema. This keeps exact 3.0.2 tables, views, triggers, UUID, and sequence behavior.
2. **Use stdlib `sqlite3`.** The proof needs only rows in `Track`, `Playlist`, and `PlaylistEntity`; adding C++ or Rust integration would obscure whether direct mutation is actually difficult.
3. **Reference existing media-drive tracks.** Engine already maintains one `Engine Library` database per drive. Match each store path to `../<rel_path>` in the target media database and use its UUID and track IDs. Missing tracks are reported and skipped; this proof does not duplicate or analyze tracks.
4. **Use a single managed root.** Rebuild only `Playlist Sync Proof` and its descendants, preserving unrelated Engine playlists. Folder paths become nested `Playlist` rows; leaf playlists hold memberships.
5. **Validate linked-list order explicitly.** Track order is checked by traversing `nextEntityId` from the unique head rather than assuming row or membership-reference order.

## Risks / Trade-offs

- **Engine may require additional undocumented state despite a valid DB** → validate the copied result in the live Engine DJ VM before promoting this proof into the production adapter.
- **Tracks absent from Engine cannot be referenced safely** → report and skip those memberships; Engine remains responsible for media discovery and analysis.
- **Path mapping may differ between deployments** → the proof takes one explicit Engine path prefix; the real adapter will expose this as format-owned configuration.
- **Engine running during production writes could overwrite changes** → the later adapter must require an offline target plus backup/copy/replace safety; this proof never touches the live file.
