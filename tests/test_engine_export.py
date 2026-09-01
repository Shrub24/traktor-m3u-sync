"""Production tests for the Engine DJ direct-SQLite export adapter.

Covers schema/journal-mode/integrity gates, existing-track matching, managed subtree
rebuild using Engine's own linked-list triggers, structured skip warnings, idempotency,
Engine-owned row immutability, fsync-wrapped replacements, source-fsync-before-copy
ordering, the best-effort post-publish directory sync, and the full
stage/backup/validate/atomic-publish failure matrix. Also covers application
integration: optional [engine] configuration with defaults and CLI overrides,
export-only registry routing, and dry-run temporary-copy isolation.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.config import (
    ConfigError,
    EngineConfig,
    apply_export_overrides,
    load_config,
)
from traktor_m3u_sync.contracts import SyncResult
from traktor_m3u_sync.formats.engine import exporter as engine_exporter
from traktor_m3u_sync.formats.engine import writer as engine_writer
from traktor_m3u_sync.formats.engine.exporter import EngineExporter
from traktor_m3u_sync.formats.engine.writer import EngineWriteError, write_database
from traktor_m3u_sync.model import Playlist, Track
from traktor_m3u_sync.services import (
    SUPPORTED_EXPORT_FORMATS,
    SUPPORTED_IMPORT_FORMATS,
    run_export,
    run_import,
)
from traktor_m3u_sync.store import PlaylistStore

RUNNER = CliRunner()

ENGINE_DB = "m.db"
BACKUP = ENGINE_DB + engine_writer.BACKUP_SUFFIX
MANAGED_ROOT = "Playlist Sync"
ARGS: dict[str, str] = {"managed_root": MANAGED_ROOT, "track_path_prefix": ".."}

# Mirrors Engine 5.0 media schema 3.0.2 playlist primitives closely enough to exercise the
# authoritative linked-list maintenance triggers, plus a PerformanceData table to prove
# Engine-owned analysis rows are never touched.
_ENGINE_SCHEMA = """
CREATE TABLE Information (
  uuid TEXT NOT NULL,
  schemaVersionMajor INTEGER NOT NULL,
  schemaVersionMinor INTEGER NOT NULL,
  schemaVersionPatch INTEGER NOT NULL
);
CREATE TABLE Track (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE);
CREATE TABLE PerformanceData (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  durationMeasurements TEXT
);
CREATE TABLE Playlist (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT,
  parentListId INTEGER,
  isPersisted BOOLEAN,
  nextListId INTEGER,
  lastEditTime DATETIME,
  isExplicitlyExported BOOLEAN,
  UNIQUE (parentListId, nextListId)
);
CREATE UNIQUE INDEX playlist_title ON Playlist (title, parentListId);
CREATE TABLE PlaylistEntity (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  listId INTEGER,
  trackId INTEGER,
  databaseUuid TEXT,
  nextEntityId INTEGER,
  membershipReference INTEGER,
  UNIQUE (listId, databaseUuid, trackId),
  FOREIGN KEY (listId) REFERENCES Playlist (id) ON DELETE CASCADE
);
CREATE TRIGGER trigger_before_insert_List BEFORE INSERT ON Playlist
BEGIN
  UPDATE Playlist SET nextListId = -(1 + nextListId)
  WHERE nextListId = NEW.nextListId AND parentListId = NEW.parentListId;
END;
CREATE TRIGGER trigger_after_insert_List AFTER INSERT ON Playlist
BEGIN
  UPDATE Playlist SET nextListId = NEW.id
  WHERE nextListId = -(1 + NEW.nextListId) AND parentListId = NEW.parentListId;
END;
CREATE TRIGGER trigger_after_delete_List AFTER DELETE ON Playlist
BEGIN
  UPDATE Playlist SET nextListId = OLD.nextListId WHERE nextListId = OLD.id;
  DELETE FROM Playlist WHERE parentListId = OLD.id;
END;
CREATE TRIGGER trigger_before_delete_PlaylistEntity BEFORE DELETE ON PlaylistEntity
WHEN OLD.trackId > 0
BEGIN
  UPDATE PlaylistEntity SET nextEntityId = OLD.nextEntityId
  WHERE nextEntityId = OLD.id AND listId = OLD.listId;
END;
"""

_TRACK_PATHS = (
    "../Music/One.mp3",
    "../Music/Two.mp3",
    "../Music/Dup.MP3",
    "../music/dup.mp3",
    "../Music/Three.mp3",
)

# Expected outcomes for the shared two-playlist fixture built from _TRACK_PATHS.
_FULL_COUNTS = {
    "playlists_written": 2,
    "tracks_matched": 3,
    "memberships_written": 3,
    "memberships_skipped": 4,
    "skipped_unresolved": 1,
    "skipped_missing": 1,
    "skipped_ambiguous": 1,
    "skipped_duplicate": 1,
    "warnings_emitted": 4,
}


def _boom(*args: object, **kwargs: object) -> None:
    raise RuntimeError("injected failure")


def _boom_restore(*args: object, **kwargs: object) -> None:
    raise RuntimeError("injected restore failure")


def _interrupt(*args: object, **kwargs: object) -> None:
    raise KeyboardInterrupt


def _residues(directory: Path) -> list[Path]:
    """Every staging/copy temporary is dot-prefixed and ends in .tmp."""
    return [p for p in directory.iterdir() if p.name.endswith(".tmp")]


def _track(path: str, *, resolved: bool = True) -> Track:
    return Track(
        title=Path(path).stem,
        artist="",
        path=path if resolved else None,
        identity=path.casefold() if resolved else None,
        raw_path=None if resolved else path,
        resolved=resolved,
    )


def _engine_db(path: Path, *, version: tuple[int, int, int] = (3, 0, 2)) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(_ENGINE_SCHEMA)
        connection.execute("INSERT INTO Information VALUES ('engine-uuid', ?, ?, ?)", version)
        connection.executemany("INSERT INTO Track (path) VALUES (?)", [(p,) for p in _TRACK_PATHS])
        connection.execute("INSERT INTO PerformanceData VALUES (NULL, 'analysis-a')")
        connection.execute("INSERT INTO PerformanceData VALUES (NULL, 'analysis-b')")
        connection.execute("INSERT INTO Playlist VALUES (NULL, 'Unrelated', 0, 1, 0, '', 1)")
        unrelated = _scalar(connection, "SELECT id FROM Playlist WHERE title = 'Unrelated'")
        connection.execute(
            "INSERT INTO PlaylistEntity (listId, trackId, databaseUuid, nextEntityId, "
            "membershipReference) VALUES (?, 1, 'engine-uuid', 0, 0)",
            (unrelated,),
        )


def _playlists() -> tuple[Playlist, ...]:
    return (
        Playlist(
            "Ordered",
            ("Folder",),
            (
                _track("Music/Two.mp3"),
                _track("Music/One.mp3"),
                _track("Music/One.mp3"),
                _track("Music/Dup.mp3"),
                _track("Music/Missing.mp3"),
                _track("raw-text", resolved=False),
            ),
        ),
        Playlist("Flat", (), (_track("Music/Three.mp3"),)),
    )


def _scalar(connection: sqlite3.Connection, sql: str, *params: object) -> int:
    return int(connection.execute(sql, params).fetchone()[0])


def _rows(connection: sqlite3.Connection, sql: str, *params: object) -> list[dict[str, Any]]:
    cursor = connection.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _managed_root_id(connection: sqlite3.Connection) -> int:
    return _scalar(
        connection,
        "SELECT id FROM Playlist WHERE parentListId = 0 AND title = ?",
        MANAGED_ROOT,
    )


def _child_id(connection: sqlite3.Connection, parent_id: int, title: str) -> int:
    return _scalar(
        connection,
        "SELECT id FROM Playlist WHERE parentListId = ? AND title = ?",
        parent_id,
        title,
    )


def _sibling_order(connection: sqlite3.Connection, parent_id: int) -> list[int]:
    rows = _rows(
        connection, "SELECT id, nextListId FROM Playlist WHERE parentListId = ?", parent_id
    )
    by_id = {int(r["id"]): r for r in rows}
    successors = {int(r["nextListId"]) for r in rows if int(r["nextListId"]) != 0}
    heads = [rid for rid in by_id if rid not in successors]
    assert len(heads) == 1
    ordered: list[int] = []
    current: int | None = heads[0]
    while current:
        assert current in by_id and current not in ordered
        ordered.append(current)
        nxt = int(by_id[current]["nextListId"])
        current = nxt or None
    assert len(ordered) == len(by_id)
    return ordered


def _open(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


# ── validation gates ─────────────────────────────────────────────────────


def test_rejects_missing_database(tmp_path: Path) -> None:
    missing = tmp_path / "absent.db"

    with pytest.raises(EngineWriteError, match="does not exist"):
        write_database(missing, _playlists(), **ARGS)

    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []


def test_rejects_unsupported_schema_without_writing(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine, version=(3, 1, 0))
    before = engine.read_bytes()

    with pytest.raises(EngineWriteError, match="expected 3.0.2"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert not (tmp_path / BACKUP).exists()


def test_rejects_missing_required_structure(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    with sqlite3.connect(engine) as connection:
        connection.execute(
            "CREATE TABLE Information (uuid TEXT, schemaVersionMajor INT, "
            "schemaVersionMinor INT, schemaVersionPatch INT)"
        )
        connection.execute("INSERT INTO Information VALUES ('u', 3, 0, 2)")
        connection.execute("CREATE TABLE Track (id INTEGER PRIMARY KEY, path TEXT UNIQUE)")

    with pytest.raises(EngineWriteError, match="lacks required structures"):
        write_database(engine, _playlists(), **ARGS)


def test_rejects_detectable_active_sidecars(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()
    journal = tmp_path / (ENGINE_DB + "-journal")
    journal.write_bytes(b"pending")

    with pytest.raises(EngineWriteError, match="stop Engine DJ"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert _residues(tmp_path) == []


@pytest.mark.parametrize("suffix", ["-wal", "-shm"])
def test_rejects_active_wal_sidecars(tmp_path: Path, suffix: str) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()
    (tmp_path / (ENGINE_DB + suffix)).write_bytes(b"active")

    with pytest.raises(EngineWriteError, match="stop Engine DJ"):
        write_database(engine, _playlists(), **ARGS)

    # Rejection runs before any SQLite open or staging: the target is untouched and the
    # only new entry is the injected sidecar itself, with no backup or temporary residue.
    assert engine.read_bytes() == before
    assert not (tmp_path / BACKUP).exists()
    assert _residues(tmp_path) == []


def test_rejects_wal_journal_mode_before_staging(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    connection = _open(engine)
    assert connection.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
    connection.execute("INSERT INTO Track (path) VALUES ('../Music/Wal.mp3')")
    connection.commit()
    connection.close()
    # A clean close checkpoints and removes the sidecars: only the persistent WAL
    # header remains, so this must fail on the journal-mode gate, not the sidecar gate.
    assert sorted(p.name for p in tmp_path.iterdir()) == [ENGINE_DB]
    before = engine.read_bytes()

    with pytest.raises(EngineWriteError, match="journal mode"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert not (tmp_path / BACKUP).exists()
    assert _residues(tmp_path) == []


def test_empty_rollback_journal_is_not_treated_as_active(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    (tmp_path / (ENGINE_DB + "-journal")).write_bytes(b"")

    result = EngineExporter(database_path=engine).write(_playlists())

    assert result.counts["tracks_matched"] == 3


# ── matching, hierarchy, ordering, warnings ──────────────────────────────


def test_reports_matched_playlists_and_each_skip_reason(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)

    result = EngineExporter(database_path=engine).write(_playlists())

    assert isinstance(result, SyncResult)
    assert result.counts == _FULL_COUNTS
    assert {w.code for w in result.warnings} == {
        "track_unresolved",
        "track_missing",
        "track_ambiguous",
        "track_duplicate_membership",
    }
    assert all(w.playlist and w.detail for w in result.warnings)


def test_rebuild_matches_hierarchy_membership_and_linked_order(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)

    EngineExporter(database_path=engine).write(_playlists())

    connection = _open(engine)
    assert _scalar(connection, "SELECT COUNT(*) FROM Playlist WHERE title = ?", MANAGED_ROOT) == 1
    root = _managed_root_id(connection)
    folder = _child_id(connection, root, "Folder")
    flat = _child_id(connection, root, "Flat")
    ordered = _child_id(connection, folder, "Ordered")

    assert _sibling_order(connection, root) == [folder, flat]

    entities = _rows(
        connection,
        "SELECT id, trackId, databaseUuid, nextEntityId FROM PlaylistEntity "
        "WHERE listId = ? ORDER BY id",
        ordered,
    )
    assert [(e["trackId"], e["databaseUuid"]) for e in entities] == [
        (2, "engine-uuid"),
        (1, "engine-uuid"),
    ]
    assert entities[0]["nextEntityId"] == entities[1]["id"]
    assert entities[1]["nextEntityId"] == 0


def test_duplicate_playlist_label_fails_staged_write(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()
    one = _track("Music/One.mp3")
    playlists = (Playlist("Clash", ("Folder",), (one,)), Playlist("Clash", ("Folder",), (one,)))

    with pytest.raises(EngineWriteError, match="Engine rejected playlist"):
        write_database(engine, playlists, **ARGS)

    assert engine.read_bytes() == before
    assert _residues(tmp_path) == []


def test_duplicate_managed_root_fails_staged_write(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    with _open(engine) as connection:
        # Seed an ownership ambiguity Engine's own uniqueness rules would normally
        # prevent: two top-level playlists claiming the managed root.
        connection.execute("DROP INDEX playlist_title")
        connection.execute("DROP TRIGGER trigger_before_insert_List")
        connection.execute("DROP TRIGGER trigger_after_insert_List")
        for next_id in (2, 3):
            connection.execute(
                "INSERT INTO Playlist (title, parentListId, isPersisted, nextListId, "
                "lastEditTime, isExplicitlyExported) VALUES (?, 0, 1, ?, '', 1)",
                (MANAGED_ROOT, next_id),
            )
    before = engine.read_bytes()

    with pytest.raises(EngineWriteError, match="Multiple top-level playlists"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert not (tmp_path / BACKUP).exists()
    assert _residues(tmp_path) == []


def test_malformed_store_paths_skip_per_membership(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    playlists = (
        Playlist(
            "Escapes",
            (),
            (
                _track("/Absolute.mp3"),
                _track("../Escape.mp3"),
                _track("Music/One.mp3"),
            ),
        ),
    )

    result = EngineExporter(database_path=engine).write(playlists)

    assert result.counts["memberships_written"] == 1
    assert result.counts["tracks_matched"] == 1
    assert result.counts["skipped_unresolved"] == 2
    assert result.counts["memberships_skipped"] == 2
    assert [w.code for w in result.warnings] == ["track_unresolved", "track_unresolved"]
    assert [w.detail for w in result.warnings] == ["/Absolute.mp3", "../Escape.mp3"]


# ── Engine-owned immutability + unrelated preservation ───────────────────


def test_preserves_tracks_performance_data_and_unrelated_playlists(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    with _open(engine) as connection:
        tracks_before = _rows(connection, "SELECT id, path FROM Track ORDER BY id")
        performance_before = _rows(
            connection, "SELECT id, durationMeasurements FROM PerformanceData ORDER BY id"
        )

    EngineExporter(database_path=engine).write(_playlists())

    with _open(engine) as connection:
        assert _rows(connection, "SELECT id, path FROM Track ORDER BY id") == tracks_before
        assert (
            _rows(connection, "SELECT id, durationMeasurements FROM PerformanceData ORDER BY id")
            == performance_before
        )
        unrelated = _scalar(connection, "SELECT id FROM Playlist WHERE title = 'Unrelated'")
        assert (
            _scalar(connection, "SELECT COUNT(*) FROM PlaylistEntity WHERE listId = ?", unrelated)
            == 1
        )
        assert _sibling_order(connection, 0)[0] == unrelated


# ── idempotency ──────────────────────────────────────────────────────────


def test_repeated_run_is_idempotent(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    exporter = EngineExporter(database_path=engine)

    exporter.write(_playlists())
    second = exporter.write(_playlists())

    assert second.counts == _FULL_COUNTS
    connection = _open(engine)
    assert _scalar(connection, "SELECT COUNT(*) FROM Playlist WHERE title = ?", MANAGED_ROOT) == 1
    # 3 managed memberships + 1 unrelated membership retained.
    assert _scalar(connection, "SELECT COUNT(*) FROM PlaylistEntity") == 4
    assert (
        _scalar(
            connection,
            "SELECT COUNT(*) FROM PlaylistEntity WHERE listId NOT IN (SELECT id FROM Playlist)",
        )
        == 0
    )
    assert (
        _scalar(
            connection,
            "SELECT COUNT(*) FROM Playlist WHERE parentListId != 0 "
            "AND parentListId NOT IN (SELECT id FROM Playlist)",
        )
        == 0
    )


# ── publication: success path ────────────────────────────────────────────


def test_publishes_atomically_and_retains_one_backup(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    original = engine.read_bytes()

    EngineExporter(database_path=engine).write(_playlists())

    backup = tmp_path / BACKUP
    assert backup.read_bytes() == original
    assert engine.read_bytes() != original
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([ENGINE_DB, BACKUP])


def test_preserves_target_and_backup_file_mode(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    os.chmod(engine, 0o600)

    EngineExporter(database_path=engine).write(_playlists())

    backup = tmp_path / BACKUP
    assert stat.S_IMODE(engine.stat().st_mode) == 0o600
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600


def test_backup_refreshes_to_prior_generation_each_run(tmp_path: Path) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    exporter = EngineExporter(database_path=engine)
    backup = tmp_path / BACKUP

    exporter.write(_playlists())
    generation_two = engine.read_bytes()
    exporter.write(_playlists())

    assert backup.read_bytes() == generation_two
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted([ENGINE_DB, BACKUP])


# ── publication: pre-publication failures leave target unchanged ─────────


@pytest.mark.parametrize(
    "seam",
    ["_create_stage", "_rebuild_stage", "_validate_staged", "_refresh_backup", "_publish_stage"],
)
def test_pre_publication_failure_leaves_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seam: str
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()
    monkeypatch.setattr(engine_writer, seam, _boom)

    with pytest.raises(RuntimeError, match="injected failure"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert _residues(tmp_path) == []
    backup = tmp_path / BACKUP
    # A backup only ever exists if the failure happened at/after its refresh, and then it
    # must hold the unchanged prior generation.
    assert not backup.exists() or backup.read_bytes() == before


def test_rebuild_failure_rolls_back_without_touching_engine_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()

    def fail_tree(*args: object, **kwargs: object) -> None:
        raise EngineWriteError("invalid generated state")

    monkeypatch.setattr(engine_writer, "_validate_managed_tree", fail_tree)

    with pytest.raises(EngineWriteError, match="invalid generated state"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert _residues(tmp_path) == []
    with _open(engine) as connection:
        assert (
            _scalar(connection, "SELECT COUNT(*) FROM Playlist WHERE title = ?", MANAGED_ROOT) == 0
        )
        assert _scalar(connection, "SELECT COUNT(*) FROM PlaylistEntity") == 1


# ── publication: post-publication failure restores backup ────────────────


def test_post_publication_validation_failure_restores_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    original = engine.read_bytes()
    monkeypatch.setattr(engine_writer, "_validate_published", _boom)

    with pytest.raises(RuntimeError, match="injected failure"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == original
    assert _residues(tmp_path) == []
    assert (tmp_path / BACKUP).read_bytes() == original


def test_failed_restore_surfaces_and_retains_validated_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    original = engine.read_bytes()
    monkeypatch.setattr(engine_writer, "_validate_published", _boom)
    monkeypatch.setattr(engine_writer, "_restore_backup", _boom_restore)

    with pytest.raises(RuntimeError, match="injected restore failure"):
        write_database(engine, _playlists(), **ARGS)

    # The published bad state remains, but the operator's only recovery copy must be
    # exactly the validated original and every temporary must be gone.
    assert (tmp_path / BACKUP).read_bytes() == original
    assert engine.read_bytes() != original
    assert _residues(tmp_path) == []


def test_failed_restore_preserves_validation_error_as_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    monkeypatch.setattr(engine_writer, "_validate_published", _boom)
    monkeypatch.setattr(engine_writer, "_restore_backup", _boom_restore)

    with pytest.raises(RuntimeError, match="injected restore failure") as exc_info:
        write_database(engine, _playlists(), **ARGS)

    # The restore failure surfaces, but it must chain the original post-publish validation
    # error as context so the real cause is never lost from the traceback.
    context = exc_info.value.__context__
    assert isinstance(context, RuntimeError)
    assert "injected failure" in str(context)
    assert exc_info.value.__cause__ is None or "injected failure" in str(exc_info.value.__cause__)


def test_keyboard_interrupt_cleans_stage_without_swallowing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    before = engine.read_bytes()
    monkeypatch.setattr(engine_writer, "_rebuild_stage", _interrupt)

    with pytest.raises(KeyboardInterrupt):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == before
    assert _residues(tmp_path) == []


def test_every_replacement_is_fsync_wrapped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    events: list[tuple[str, str]] = []
    real_fsync = getattr(engine_writer, "_fsync")
    real_replace = os.replace

    def record_fsync(path: Path) -> None:
        events.append(("fsync", str(path)))
        real_fsync(path)

    def record_replace(source: Path, destination: Path) -> None:
        events.append(("replace", str(source)))
        real_replace(source, destination)

    monkeypatch.setattr(engine_writer, "_fsync", record_fsync)
    monkeypatch.setattr(engine_writer.os, "replace", record_replace)

    EngineExporter(database_path=engine).write(_playlists())
    after_first_run = engine.read_bytes()
    monkeypatch.setattr(engine_writer, "_validate_published", _boom)
    with pytest.raises(RuntimeError, match="injected failure"):
        write_database(engine, _playlists(), **ARGS)

    # Backup refresh + stage publish per run, plus the failed second run's restore copy.
    replace_indexes = [i for i, event in enumerate(events) if event[0] == "replace"]
    assert len(replace_indexes) == 5
    for i in replace_indexes:
        assert events[i - 1] == ("fsync", events[i][1])
        assert events[i + 1] == ("fsync", str(tmp_path))
    assert engine.read_bytes() == after_first_run


def test_publish_tolerates_post_rename_directory_fsync_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    original = engine.read_bytes()
    real_fsync = getattr(engine_writer, "_fsync")
    real_replace = os.replace
    renamed = {"done": False}

    def spy_replace(source: Path, destination: Path) -> None:
        if Path(destination) == engine:
            renamed["done"] = True
        real_replace(source, destination)

    def fail_dir_after_rename(path: Path) -> None:
        # Only the directory sync that follows the publish rename fails; every pre-rename
        # file sync and the backup refresh's own directory sync still run normally.
        if renamed["done"] and Path(path) == tmp_path:
            raise OSError("injected post-rename directory fsync failure")
        real_fsync(path)

    monkeypatch.setattr(engine_writer.os, "replace", spy_replace)
    monkeypatch.setattr(engine_writer, "_fsync", fail_dir_after_rename)

    # The rename committed, so the write must report success instead of a false failure.
    outcome = write_database(engine, _playlists(), **ARGS)

    assert outcome.tracks_matched == _FULL_COUNTS["tracks_matched"]
    assert engine.read_bytes() != original
    assert (tmp_path / BACKUP).read_bytes() == original
    assert _residues(tmp_path) == []


def test_publish_surfaces_pre_rename_fsync_failure_and_leaves_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    original = engine.read_bytes()
    real_fsync = getattr(engine_writer, "_fsync")

    def fail_stage_fsync(path: Path) -> None:
        if str(path).endswith(".stage.tmp"):
            raise OSError("injected pre-rename fsync failure")
        real_fsync(path)

    monkeypatch.setattr(engine_writer, "_fsync", fail_stage_fsync)

    # A pre-rename fsync failure is meaningful: the rename never ran, so the error must
    # propagate and the target must stay on its prior generation with the stage dropped.
    with pytest.raises(OSError, match="pre-rename fsync failure"):
        write_database(engine, _playlists(), **ARGS)

    assert engine.read_bytes() == original
    assert _residues(tmp_path) == []


def test_source_target_is_fsynced_before_being_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = tmp_path / ENGINE_DB
    _engine_db(engine)
    engine_str = str(engine)
    events: list[tuple[str, str]] = []
    real_fsync = getattr(engine_writer, "_fsync")
    real_replace = os.replace

    def record_fsync(path: Path) -> None:
        events.append(("fsync", str(path)))
        real_fsync(path)

    def record_replace(source: Path, destination: Path) -> None:
        events.append(("replace", str(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(engine_writer, "_fsync", record_fsync)
    monkeypatch.setattr(engine_writer.os, "replace", record_replace)

    EngineExporter(database_path=engine).write(_playlists())

    source_syncs = [i for i, event in enumerate(events) if event == ("fsync", engine_str)]
    backup_replaces = [
        i for i, event in enumerate(events) if event == ("replace", str(tmp_path / BACKUP))
    ]
    # The first fsync of the whole run is the source target, taken before the stage copy.
    assert events[0] == ("fsync", engine_str)
    # The source is synced again before it is copied into the retained backup.
    assert backup_replaces and source_syncs and min(source_syncs) < backup_replaces[0]


def test_exporter_defaults_and_writer_invariants_match_design() -> None:
    assert engine_exporter.FORMAT == "engine"
    exporter = EngineExporter(database_path=Path("unused.db"))
    assert exporter.track_path_prefix == ".."
    assert exporter.managed_root == MANAGED_ROOT
    assert engine_writer.SCHEMA_VERSION == (3, 0, 2)
    assert engine_writer.BACKUP_SUFFIX == ".playlist-sync.bak"


# ── application integration: config, registry, CLI, dry-run isolation ───


def test_load_config_applies_engine_defaults_without_table(tmp_path: Path) -> None:
    config = load_config(_write_toml(tmp_path))

    assert config.engine == EngineConfig(None, "..", MANAGED_ROOT)


def test_load_config_parses_engine_table(tmp_path: Path) -> None:
    config = load_config(
        _write_toml(
            tmp_path,
            f'[engine]\ndatabase_path = "{tmp_path / ENGINE_DB}"\n'
            'track_path_prefix = "M:"\nmanaged_root = "Mixes"\n',
        )
    )

    assert config.engine == EngineConfig(tmp_path / ENGINE_DB, "M:", "Mixes")


def test_engine_export_requires_database_path(tmp_path: Path) -> None:
    config_path = _write_toml(tmp_path)

    with pytest.raises(ConfigError, match="database_path is required for Engine export"):
        apply_export_overrides(load_config(config_path), format="engine")

    result = RUNNER.invoke(app, ["export", "--format", "engine", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


def test_unrelated_commands_require_no_engine_config(tmp_path: Path) -> None:
    config = load_config(_write_toml(tmp_path))

    overridden = apply_export_overrides(config, format="m3u", output_dir=tmp_path / "out")

    assert overridden.engine.database_path is None
    assert overridden.m3u.output_dir == tmp_path / "out"


def test_engine_cli_overrides_take_precedence(tmp_path: Path) -> None:
    config = load_config(
        _write_toml(
            tmp_path,
            f'[engine]\ndatabase_path = "{tmp_path / "a.db"}"\n'
            'track_path_prefix = "P"\nmanaged_root = "R"\n',
        )
    )

    kept = apply_export_overrides(config, format="engine")
    overridden = apply_export_overrides(
        config,
        format="engine",
        engine_database=tmp_path / "b.db",
        engine_track_prefix="Q",
        engine_managed_root="S",
    )

    assert kept.engine == EngineConfig(tmp_path / "a.db", "P", "R")
    assert overridden.engine == EngineConfig(tmp_path / "b.db", "Q", "S")


def test_engine_is_export_only_in_registries(tmp_path: Path) -> None:
    assert "engine" in SUPPORTED_EXPORT_FORMATS
    assert "engine" not in SUPPORTED_IMPORT_FORMATS
    with pytest.raises(ValueError, match="Unsupported format 'engine' for import"):
        run_import(load_config(_write_toml(tmp_path)), "engine")


def test_engine_export_cli_routes_overrides_into_database(tmp_path: Path) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database)
    config_path = _write_toml(
        tmp_path,
        f'[engine]\ndatabase_path = "{tmp_path / "wrong.db"}"\nmanaged_root = "Configured Root"\n',
    )
    _seed_store(tmp_path)

    result = RUNNER.invoke(
        app,
        [
            "export",
            "--format",
            "engine",
            "--config",
            str(config_path),
            "--engine-database",
            str(database),
            "--engine-managed-root",
            "CLI Root",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "SUMMARY playlists_written=2 tracks_matched=3" in result.stdout
    with _open(database) as connection:
        roots = {
            str(row[0])
            for row in connection.execute("SELECT title FROM Playlist WHERE parentListId = 0")
        }
    assert "CLI Root" in roots
    assert "Configured Root" not in roots


def test_engine_dry_run_rehearses_copy_without_configured_writes(tmp_path: Path) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database)
    config = load_config(_write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n'))
    _seed_store(tmp_path)
    original = database.read_bytes()
    mode = stat.S_IMODE(os.stat(database).st_mode)
    store_path = tmp_path / "store.db"
    store_bytes = store_path.read_bytes()

    dry = run_export(config, "engine", dry_run=True)

    assert dry.counts == _FULL_COUNTS
    assert not (tmp_path / BACKUP).exists()
    assert database.read_bytes() == original
    assert stat.S_IMODE(os.stat(database).st_mode) == mode
    assert store_path.read_bytes() == store_bytes

    real = run_export(config, "engine")
    assert real.counts == dry.counts
    assert real.warnings == dry.warnings
    assert database.read_bytes() != original
    assert (tmp_path / BACKUP).is_file()


def test_engine_dry_run_failure_leaves_configured_state_unchanged(tmp_path: Path) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database, version=(9, 9, 9))
    config = load_config(_write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n'))
    _seed_store(tmp_path)
    original = database.read_bytes()
    store_bytes = (tmp_path / "store.db").read_bytes()

    with pytest.raises(EngineWriteError, match="schema"):
        run_export(config, "engine", dry_run=True)

    assert database.read_bytes() == original
    assert not (tmp_path / BACKUP).exists()
    assert (tmp_path / "store.db").read_bytes() == store_bytes
    assert _residues(tmp_path) == []


@pytest.mark.parametrize("suffix", ["-journal", "-wal", "-shm"])
def test_engine_dry_run_aborts_on_active_configured_sidecars(tmp_path: Path, suffix: str) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database)
    config = load_config(_write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n'))
    _seed_store(tmp_path)
    original = database.read_bytes()
    store_bytes = (tmp_path / "store.db").read_bytes()
    sidecar = tmp_path / (ENGINE_DB + suffix)
    sidecar.write_bytes(b"active")

    with pytest.raises(EngineWriteError, match="stop Engine DJ"):
        run_export(config, "engine", dry_run=True)

    # The guard runs against the configured target before any sandbox copy, so dry-run
    # keeps the same offline gate as a real export and touches nothing.
    assert database.read_bytes() == original
    assert (tmp_path / "store.db").read_bytes() == store_bytes
    assert not (tmp_path / BACKUP).exists()
    assert _residues(tmp_path) == []
    assert sidecar.read_bytes() == b"active"


def test_engine_dry_run_allows_empty_configured_journal(tmp_path: Path) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database)
    config = load_config(_write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n'))
    _seed_store(tmp_path)
    original = database.read_bytes()
    (tmp_path / (ENGINE_DB + "-journal")).write_bytes(b"")

    dry = run_export(config, "engine", dry_run=True)

    assert dry.counts == _FULL_COUNTS
    assert database.read_bytes() == original
    assert not (tmp_path / BACKUP).exists()


def test_engine_dry_run_missing_database_names_configured_path(tmp_path: Path) -> None:
    database = tmp_path / "absent" / ENGINE_DB
    config = load_config(_write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n'))
    _seed_store(tmp_path)

    with pytest.raises(EngineWriteError) as excinfo:
        run_export(config, "engine", dry_run=True)

    assert str(excinfo.value) == f"Engine database does not exist: {database}"
    assert "dry-run" not in str(excinfo.value)


def test_engine_export_cli_dry_run_preserves_state_and_matches_real_summary(
    tmp_path: Path,
) -> None:
    database = tmp_path / ENGINE_DB
    _engine_db(database)
    config_path = _write_toml(tmp_path, f'[engine]\ndatabase_path = "{database}"\n')
    _seed_store(tmp_path)
    original = database.read_bytes()
    store_bytes = (tmp_path / "store.db").read_bytes()

    dry = RUNNER.invoke(
        app,
        [
            "export",
            "--format",
            "engine",
            "--dry-run",
            "--fail-on-warning",
            "--config",
            str(config_path),
        ],
    )

    assert dry.exit_code == 2
    assert "WARNING code=track_unresolved" in dry.stderr
    assert not (tmp_path / BACKUP).exists()
    assert database.read_bytes() == original
    assert (tmp_path / "store.db").read_bytes() == store_bytes

    real = RUNNER.invoke(app, ["export", "--format", "engine", "--config", str(config_path)])

    assert real.exit_code == 0
    assert real.stdout == dry.stdout
    assert (tmp_path / BACKUP).is_file()


def _write_toml(tmp_path: Path, engine_text: str | None = None) -> Path:
    text = (
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[m3u]\nlibrary_root = "../music"\noutput_dir = "{tmp_path / "out"}"\n'
    )
    if engine_text:
        text += f"\n{engine_text}"
    path = tmp_path / "traktor-m3u-sync.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _seed_store(tmp_path: Path) -> None:
    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild(_playlists())
