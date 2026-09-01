## 1. Direct SQLite Proof

- [x] 1.1 Implement a proof-only Engine module that reads the store, gates an Engine media database copy to schema 3.0.2 with integrity checks, matches `../<rel_path>` tracks, rebuilds one managed playlist subtree, and validates hierarchy and `nextEntityId` ordering in one transaction.
  - refs: `proposal.md`, `design.md`, `specs/engine-sqlite-proof/spec.md`
  - delegate: `CoderAgent`
  - verify: focused regression test passes

## 2. Regression Check

- [x] 2.1 Add one synthetic regression test covering path matching, nested playlists, ordered linked entries, a missing track, a duplicate membership, UUID references, and rollback on an incompatible schema.
  - depends: 1.1
  - delegate: `CoderAgent`
  - verify: `uv run pytest tests/test_engine_proof.py`

## 3. Real Database Proof

- [x] 3.1 Run the proof against copies of the current home-forge store and `M:\Engine Library\Database2\m.db`; verify 874/874 track matching, 12 managed playlists, valid membership chains, unchanged source hashes, and `PRAGMA integrity_check = ok`.
  - depends: 2.1
  - verify: proof command output plus before/after hashes

- [x] 3.2 Run scoped project checks, focused review, and strict OpenSpec validation.
  - depends: 3.1
  - delegate: `CodeReviewer`
  - verify: `just check`, `git diff --check`, and `openspec validate engine-sqlite-proof --type change --strict`
