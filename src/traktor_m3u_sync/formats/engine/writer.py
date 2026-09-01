"""Direct-SQLite Engine DJ 5.0 media-database writer with safe atomic publication.

The writer mutates only one managed playlist subtree inside an existing schema 3.0.2
media database in rollback-journal (``DELETE``) mode, never creating the database,
replaying Engine DDL, or touching ``Track``/``PerformanceData`` rows. Publication is
database-specific and intentionally stronger than generated-file publication: the target
is validated read-only first, a mode-preserving same-directory copy is rebuilt in one
transaction and re-validated, an adjacent backup is refreshed from the validated prior
target, the stage is published with ``os.replace``, and a post-publication validation
failure restores that backup. The validated source is fsynced before it is copied into the
stage or backup, so the retained prior generation is always read from durable on-disk state.
Every replacement fsyncs the complete staged/copied file before ``os.replace`` and its
containing directory after it, because the target is a user-owned database that cannot be
regenerated after a crash. The single exception is the directory sync that follows the final
publish rename: once that rename returns the target is committed, so on shared storage a
directory fsync failure there is treated as best-effort and never reported as an unpublished
write.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import sqlite3
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Final

from ...contracts import AdapterWarning, playlist_label
from ...model import Playlist, Track

SCHEMA_VERSION: Final[tuple[int, int, int]] = (3, 0, 2)
BACKUP_SUFFIX: Final[str] = ".playlist-sync.bak"
ACTIVE_EXPORT_MESSAGE: Final[str] = (
    "Engine database has active write sidecars; stop Engine DJ before export"
)

_REQUIRED_TABLES: Final[frozenset[str]] = frozenset(
    {"Information", "Track", "Playlist", "PlaylistEntity"}
)


class EngineWriteError(RuntimeError):
    """Raised when the Engine target is incompatible or publication cannot complete."""


@dataclass(frozen=True)
class WriteOutcome:
    playlists_written: int
    tracks_matched: int
    memberships_written: int
    skipped_unresolved: int
    skipped_missing: int
    skipped_ambiguous: int
    skipped_duplicate: int
    warnings: tuple[AdapterWarning, ...]


def write_database(
    database_path: Path,
    playlists: Sequence[Playlist],
    *,
    managed_root: str,
    track_path_prefix: str,
) -> WriteOutcome:
    """Rebuild one managed subtree and publish the result atomically, retaining a backup."""
    database_path = Path(database_path)
    preflight_target(database_path)
    _validate_target(database_path)

    mode = os.stat(database_path).st_mode & 0o777
    backup_path = database_path.with_name(database_path.name + BACKUP_SUFFIX)
    stage = _create_stage(database_path, mode)
    published = False
    try:
        outcome = _rebuild_stage(stage, playlists, managed_root, track_path_prefix)
        _validate_staged(stage)
        _refresh_backup(database_path, backup_path, mode)
        _publish_stage(stage, database_path)
        published = True
        try:
            _validate_published(database_path)
        except Exception:
            # The target is already the new stage; any post-publish validation failure
            # (not just a known write error) must roll back to the retained backup.
            _restore_backup(backup_path, database_path, mode)
            raise
        return outcome
    finally:
        # BaseException-safe (KeyboardInterrupt included); never swallow the cause.
        if not published:
            _unlink(stage)


def preflight_target(database_path: Path) -> None:
    """Reject an absent or actively-written target before any read or copy.

    Sidecars are rejected before any SQLite open: reading a live WAL database can
    checkpoint recovery frames back into a target that has not been staged yet.
    """
    if not database_path.is_file():
        raise EngineWriteError(f"Engine database does not exist: {database_path}")
    journal = database_path.with_name(database_path.name + "-journal")
    if journal.exists() and journal.stat().st_size > 0:
        raise EngineWriteError(f"{ACTIVE_EXPORT_MESSAGE}: {journal}")
    for suffix in ("-wal", "-shm"):
        sidecar = database_path.with_name(database_path.name + suffix)
        if sidecar.exists():
            raise EngineWriteError(f"{ACTIVE_EXPORT_MESSAGE}: {sidecar}")


def _create_stage(database_path: Path, mode: int) -> Path:
    # Rebuild the stage from durable state: fsync the validated source before reading it.
    _fsync(database_path)
    handle, temp_name = tempfile.mkstemp(
        dir=database_path.parent, prefix=f".{database_path.name}.", suffix=".stage.tmp"
    )
    os.close(handle)
    stage = Path(temp_name)
    try:
        shutil.copyfile(database_path, stage)
        os.chmod(stage, mode)
    except BaseException:
        _unlink(stage)
        raise
    return stage


def _rebuild_stage(
    stage: Path,
    playlists: Sequence[Playlist],
    managed_root: str,
    track_path_prefix: str,
) -> WriteOutcome:
    connection = _connect(stage)
    try:
        _validate_database(connection)
        connection.execute("BEGIN IMMEDIATE")
        outcome = rebuild_managed_subtree(
            connection, playlists, managed_root=managed_root, track_path_prefix=track_path_prefix
        )
        _validate_database(connection)
        connection.commit()
        return outcome
    except Exception:
        # A failed rollback must not mask the original staging error; closing the
        # connection below still discards the uncommitted transaction.
        with contextlib.suppress(sqlite3.Error):
            connection.rollback()
        raise
    finally:
        connection.close()


def _refresh_backup(database_path: Path, backup_path: Path, mode: int) -> None:
    _atomic_copy(database_path, backup_path, mode)


def _restore_backup(backup_path: Path, database_path: Path, mode: int) -> None:
    _atomic_copy(backup_path, database_path, mode)


def _publish_stage(stage: Path, database_path: Path) -> None:
    # Pre-rename file fsync is strict: if it fails the rename never runs, so the target is
    # genuinely unpublished and the caller must see the error and drop the stage.
    _fsync(stage)
    os.replace(stage, database_path)
    # ponytail: once os.replace returns the target is committed. On shared storage a directory
    # fsync can fail without undoing that rename, so the post-rename sync is best-effort rather
    # than surfacing a durability error as a false "write failed"; the retained backup still
    # holds the prior generation and post-publish validation still guards the committed state.
    with contextlib.suppress(OSError):
        _fsync(database_path.parent)


def _atomic_copy(source: Path, destination: Path, mode: int) -> None:
    # Fsync the source before reading it so a retained backup or a restore copies durable bytes.
    _fsync(source)
    handle, temp_name = tempfile.mkstemp(
        dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
    )
    os.close(handle)
    temp = Path(temp_name)
    try:
        shutil.copyfile(source, temp)
        os.chmod(temp, mode)
        _fsync(temp)
        os.replace(temp, destination)
        _fsync(destination.parent)
    except BaseException:
        _unlink(temp)
        raise


def _fsync(path: Path) -> None:
    """Persist a file's (or a directory entry's) data before it can be assumed durable."""
    handle = os.open(path, os.O_RDONLY)
    try:
        os.fsync(handle)
    finally:
        os.close(handle)


# ponytail: the three aliases below are deliberate one-line wrappers of _validate_file. Each
# names a distinct lifecycle phase (pre-open, staged, published) and is the seam tests use to
# inject phase-specific failures; collapsing them into _validate_file would drop those hooks.
def _validate_target(database_path: Path) -> None:
    _validate_file(database_path)


def _validate_staged(database_path: Path) -> None:
    _validate_file(database_path)


def _validate_published(database_path: Path) -> None:
    _validate_file(database_path)


def _validate_file(database_path: Path) -> None:
    connection = _connect(database_path, read_only=True)
    try:
        _validate_database(connection)
    finally:
        connection.close()


def _connect(database_path: Path, *, read_only: bool = False) -> sqlite3.Connection:
    target: str | Path = (
        f"{database_path.resolve().as_uri()}?mode=ro" if read_only else database_path
    )
    connection = sqlite3.connect(target, uri=read_only)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA recursive_triggers = ON")
    return connection


def _validate_database(connection: sqlite3.Connection) -> None:
    # Gate the header property first: a WAL-mode database copied without its sidecars
    # is an inconsistent snapshot, so reject it before any content validation and
    # never attempt to normalize the journal mode of a user-owned database.
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).casefold()
    if journal_mode != "delete":
        raise EngineWriteError(
            f"Engine journal mode {journal_mode!r} is unsupported; expected "
            "rollback-journal (delete) mode"
        )

    tables = {
        str(row["name"])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }
    missing = _REQUIRED_TABLES - tables
    if missing:
        raise EngineWriteError(f"Engine database lacks required structures: {sorted(missing)}")

    row = connection.execute(
        "SELECT schemaVersionMajor, schemaVersionMinor, schemaVersionPatch FROM Information"
    ).fetchone()
    version = tuple(int(value) for value in row) if row is not None else ()
    if version != SCHEMA_VERSION:
        raise EngineWriteError(f"Engine schema {version!r} is unsupported; expected 3.0.2")

    integrity = connection.execute("PRAGMA integrity_check").fetchone()
    if integrity is None or integrity[0] != "ok":
        raise EngineWriteError(f"Engine database integrity check failed: {integrity!r}")
    foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_keys:
        raise EngineWriteError(f"Engine database has broken foreign keys: {foreign_keys!r}")
    _reject_orphans(connection)


def _reject_orphans(connection: sqlite3.Connection) -> None:
    entities = connection.execute(
        "SELECT COUNT(*) FROM PlaylistEntity WHERE listId NOT IN (SELECT id FROM Playlist)"
    ).fetchone()
    if entities is None or int(entities[0]) != 0:
        raise EngineWriteError("Engine database has orphaned playlist entities")
    lists = connection.execute(
        "SELECT COUNT(*) FROM Playlist "
        "WHERE parentListId != 0 AND parentListId NOT IN (SELECT id FROM Playlist)"
    ).fetchone()
    if lists is None or int(lists[0]) != 0:
        raise EngineWriteError("Engine database has orphaned playlists")


def rebuild_managed_subtree(
    connection: sqlite3.Connection,
    playlists: Sequence[Playlist],
    *,
    managed_root: str,
    track_path_prefix: str,
) -> WriteOutcome:
    """Delete and rebuild exactly one managed subtree within an open transaction."""
    information = connection.execute("SELECT uuid FROM Information").fetchone()
    if information is None or not information[0]:
        raise EngineWriteError("Engine database has no UUID")
    database_uuid = str(information[0])
    track_ids = _engine_track_ids(connection)

    existing = connection.execute(
        "SELECT id FROM Playlist WHERE parentListId = 0 AND title = ?", (managed_root,)
    ).fetchall()
    if len(existing) > 1:
        raise EngineWriteError(f"Multiple top-level playlists are named {managed_root!r}")
    if existing:
        connection.execute("DELETE FROM Playlist WHERE id = ?", (int(existing[0][0]),))
        _reject_orphans(connection)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    root_id = _insert_playlist(connection, managed_root, 0, timestamp)
    node_ids: dict[tuple[str, ...], int] = {(): root_id}
    children: dict[int, list[int]] = {root_id: []}
    leaf_orders: dict[int, list[int]] = {}
    matched: set[str] = set()
    warnings: list[AdapterWarning] = []
    skipped = {"unresolved": 0, "missing": 0, "ambiguous": 0, "duplicate": 0}
    memberships = 0

    for playlist in playlists:
        label = playlist_label(playlist.folder_path, playlist.name)
        parent_path: tuple[str, ...] = ()
        parent_id = root_id
        for segment in playlist.folder_path:
            path = (*parent_path, segment)
            if path not in node_ids:
                folder_id = _insert_playlist(connection, segment, parent_id, timestamp)
                node_ids[path] = folder_id
                children.setdefault(parent_id, []).append(folder_id)
                children[folder_id] = []
            parent_path = path
            parent_id = node_ids[path]

        leaf_id = _insert_playlist(connection, playlist.name, parent_id, timestamp)
        children.setdefault(parent_id, []).append(leaf_id)
        children[leaf_id] = []
        order: list[int] = []
        seen: set[int] = set()
        previous_entity_id: int | None = None
        for track in playlist.tracks:
            engine_path = _resolve_engine_path(track, track_path_prefix, label, warnings, skipped)
            if engine_path is None:
                continue
            track_id = track_ids.get(engine_path)
            if track_id is None:
                ambiguous = engine_path in track_ids
                skipped["ambiguous" if ambiguous else "missing"] += 1
                warnings.append(
                    _skip_warning(
                        "track_ambiguous" if ambiguous else "track_missing",
                        "Store path matches multiple Engine tracks"
                        if ambiguous
                        else "No Engine track matches the store path",
                        label,
                        engine_path,
                    )
                )
                continue
            matched.add(engine_path)
            if track_id in seen:
                skipped["duplicate"] += 1
                warnings.append(
                    _skip_warning(
                        "track_duplicate_membership",
                        "Track repeats within one playlist; Engine cannot store the duplicate",
                        label,
                        engine_path,
                    )
                )
                continue
            seen.add(track_id)
            entity_id = _insert_entity(connection, leaf_id, track_id, database_uuid)
            if previous_entity_id is not None:
                connection.execute(
                    "UPDATE PlaylistEntity SET nextEntityId = ? WHERE id = ?",
                    (entity_id, previous_entity_id),
                )
            previous_entity_id = entity_id
            order.append(track_id)
            memberships += 1
        leaf_orders[leaf_id] = order

    top_level = connection.execute(
        "SELECT id, nextListId FROM Playlist WHERE parentListId = 0"
    ).fetchall()
    _validate_chain(top_level, None, "top-level playlist")
    _validate_managed_tree(connection, root_id, children, leaf_orders, database_uuid)
    return WriteOutcome(
        playlists_written=len(playlists),
        tracks_matched=len(matched),
        memberships_written=memberships,
        skipped_unresolved=skipped["unresolved"],
        skipped_missing=skipped["missing"],
        skipped_ambiguous=skipped["ambiguous"],
        skipped_duplicate=skipped["duplicate"],
        warnings=tuple(warnings),
    )


def _resolve_engine_path(
    track: Track,
    track_path_prefix: str,
    label: str,
    warnings: list[AdapterWarning],
    skipped: dict[str, int],
) -> str | None:
    if not track.resolved or track.path is None:
        skipped["unresolved"] += 1
        warnings.append(
            _skip_warning(
                "track_unresolved",
                "Skipping track without a library-relative path",
                label,
                track.raw_path or f"{track.artist} - {track.title}",
            )
        )
        return None
    relative = PurePosixPath(track.path)
    if relative.is_absolute() or ".." in relative.parts:
        skipped["unresolved"] += 1
        warnings.append(
            _skip_warning(
                "track_unresolved",
                "Skipping track with an absolute or escaping store path",
                label,
                track.path,
            )
        )
        return None
    return _normalize_key(_engine_path(track_path_prefix, track.path))


def _skip_warning(code: str, message: str, label: str, detail: str) -> AdapterWarning:
    return AdapterWarning(code=code, message=message, playlist=label, detail=detail)


def _engine_track_ids(connection: sqlite3.Connection) -> dict[str, int | None]:
    paths: dict[str, int | None] = {}
    for track_id, path in connection.execute("SELECT id, path FROM Track WHERE path IS NOT NULL"):
        key = _normalize_key(str(path))
        paths[key] = None if key in paths else int(track_id)
    return paths


def _normalize_key(path_text: str) -> str:
    return path_text.replace("\\", "/").casefold()


def _engine_path(prefix: str, relative_path: str) -> str:
    return str(PurePosixPath(prefix) / PurePosixPath(relative_path))


def _insert_playlist(
    connection: sqlite3.Connection, title: str, parent_id: int, timestamp: str
) -> int:
    try:
        cursor = connection.execute(
            "INSERT INTO Playlist "
            "(title, parentListId, isPersisted, nextListId, lastEditTime, isExplicitlyExported) "
            "VALUES (?, ?, 1, 0, ?, 1)",
            (title, parent_id, timestamp),
        )
    except sqlite3.IntegrityError as exc:
        raise EngineWriteError(
            f"Engine rejected playlist {title!r} under parent {parent_id}: {exc}"
        ) from exc
    playlist_id = int(cursor.lastrowid or 0)
    if playlist_id == 0:
        raise EngineWriteError(f"Engine did not allocate a playlist ID for {title!r}")
    return playlist_id


def _insert_entity(
    connection: sqlite3.Connection, list_id: int, track_id: int, database_uuid: str
) -> int:
    cursor = connection.execute(
        "INSERT INTO PlaylistEntity "
        "(listId, trackId, databaseUuid, nextEntityId, membershipReference) "
        "VALUES (?, ?, ?, 0, 0)",
        (list_id, track_id, database_uuid),
    )
    entity_id = int(cursor.lastrowid or 0)
    if entity_id == 0:
        raise EngineWriteError(f"Engine did not allocate an entity ID for track {track_id}")
    return entity_id


def _validate_managed_tree(
    connection: sqlite3.Connection,
    root_id: int,
    children: dict[int, list[int]],
    leaf_orders: dict[int, list[int]],
    database_uuid: str,
) -> None:
    for parent_id, expected in children.items():
        rows = connection.execute(
            "SELECT id, nextListId FROM Playlist WHERE parentListId = ?", (parent_id,)
        ).fetchall()
        _validate_chain(rows, expected, "playlist")
    for list_id, expected_tracks in leaf_orders.items():
        rows = connection.execute(
            "SELECT id, nextEntityId, trackId, databaseUuid FROM PlaylistEntity WHERE listId = ?",
            (list_id,),
        ).fetchall()
        ordered = _validate_chain(rows, None, "playlist entity")
        actual_tracks = [int(row["trackId"]) for row in ordered]
        if actual_tracks != expected_tracks:
            raise EngineWriteError(f"Playlist {list_id} membership order is invalid")
        if any(str(row["databaseUuid"]) != database_uuid for row in ordered):
            raise EngineWriteError(f"Playlist {list_id} references another Engine database")
    root = connection.execute(
        "SELECT parentListId FROM Playlist WHERE id = ?", (root_id,)
    ).fetchone()
    if root is None or int(root[0]) != 0:
        raise EngineWriteError("Managed root hierarchy is invalid")


def _validate_chain(
    rows: list[sqlite3.Row], expected_ids: list[int] | None, label: str
) -> list[sqlite3.Row]:
    if not rows:
        if expected_ids:
            raise EngineWriteError(f"Missing {label} rows")
        return []
    by_id = {int(row["id"]): row for row in rows}
    successors = {int(row[1]) for row in rows if int(row[1]) != 0}
    heads = set(by_id) - successors
    if len(heads) != 1:
        raise EngineWriteError(f"Invalid {label} chain heads: {sorted(heads)}")
    ordered: list[sqlite3.Row] = []
    current = heads.pop()
    while current:
        if current not in by_id or any(int(row["id"]) == current for row in ordered):
            raise EngineWriteError(f"Broken or cyclic {label} chain")
        row = by_id[current]
        ordered.append(row)
        current = int(row[1])
    actual_ids = [int(row["id"]) for row in ordered]
    if len(ordered) != len(rows) or (expected_ids is not None and actual_ids != expected_ids):
        raise EngineWriteError(f"Disconnected or reordered {label} chain")
    return ordered


def _unlink(path: Path) -> None:
    with contextlib.suppress(OSError):
        path.unlink()
