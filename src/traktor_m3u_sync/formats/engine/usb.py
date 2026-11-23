"""Build a standalone Engine DJ USB library from a closed Engine 3.0.2 media library.

The stick database is a native clone of the source: rows, triggers and performance blobs
are kept as Engine wrote them, so analysis the neutral model does not represent survives.
Track IDs and origins are preserved, which is how Engine resolves playlist membership and
how player edits are later matched back to the source.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import re
import shutil
import sqlite3
import uuid
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ...model.performance import Change, diff
from ...usb import generation
from ...usb.generation import Entry, Generation, HashCache
from .performance import apply_device_edits, capture
from .start_cues import project_main_cues
from .writer import SCHEMA_VERSION, preflight_target, publish

LIBRARY = "Engine Library"
DATABASE = f"{LIBRARY}/Database2/m.db"
_OVERVIEW = "Database2/OverviewData"
_FAT32_MAX = 2**32
_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class EngineUsbError(RuntimeError):
    """Raised when the selected Engine library cannot be staged for a USB stick."""


@dataclass(frozen=True)
class BuildResult:
    generation: Generation
    device: uuid.UUID
    playlists: int
    memberships: int
    tracks: int


def build(library: Path, output_dir: Path, playlist_root: str | None) -> BuildResult:
    library = library.resolve(strict=True)
    source_db = library / "Database2" / "m.db"
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        device = _device_uuid(output_dir / "device.json")
        hashes = HashCache(output_dir / "hashes.json")
        path = generation.start(output_dir)
        try:
            result = _stage(library, source_db, path, device, playlist_root, hashes)
        except BaseException:
            shutil.rmtree(path)
            raise
        hashes.save()
        return result


def _stage(
    library: Path,
    source_db: Path,
    path: Path,
    device: uuid.UUID,
    playlist_root: str | None,
    hashes: HashCache,
) -> BuildResult:
    tree = path / generation.TREE
    staged_db = tree / DATABASE
    staged_db.parent.mkdir(parents=True)
    preflight_target(source_db)
    source_hash = generation.file_sha256(source_db)
    with (
        closing(sqlite3.connect(source_db.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(staged_db)) as db,
    ):
        source.backup(db)
        source_uuid, *version = db.execute(
            "SELECT uuid, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch "
            "FROM Information"
        ).fetchone()
        if tuple(version) != SCHEMA_VERSION:
            raise EngineUsbError(f"Engine schema {tuple(version)!r} is unsupported")
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA recursive_triggers = ON")
        with db:
            _select(db, playlist_root, source_uuid)
            project_main_cues(db)
            files = _assets(db, library, tree / LIBRARY, source_uuid, str(device), hashes)
            db.execute(
                "UPDATE Information SET uuid = ?, lastRekordBoxLibraryImportReadCounter = NULL",
                (str(device),),
            )
            if (
                db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or db.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise EngineUsbError("Staged database failed integrity checks")
        playlists, memberships, tracks = db.execute(
            "SELECT (SELECT count(*) FROM Playlist), (SELECT count(*) FROM PlaylistEntity),"
            " (SELECT count(*) FROM Track)"
        ).fetchone()
    files[DATABASE] = Entry(generation.file_sha256(staged_db), staged_db.stat().st_size)
    if generation.file_sha256(source_db) != source_hash:
        raise EngineUsbError("Engine changed during the USB build; retry with Engine closed")
    (path / "source.sha256").write_text(source_hash)
    published = generation.publish(path, files, (DATABASE,))
    return BuildResult(published, device, playlists, memberships, tracks)


def _select(db: sqlite3.Connection, root: str | None, source_uuid: str) -> None:
    if root is not None:
        roots = db.execute(
            "SELECT id FROM Playlist WHERE parentListId = 0 AND title = ?", (root,)
        ).fetchall()
        if len(roots) != 1:
            raise EngineUsbError(f"Expected one top-level playlist named {root!r}")
        db.execute("DELETE FROM Playlist WHERE parentListId = 0 AND id <> ?", roots[0])
    invalid = db.execute(
        """SELECT e.trackId FROM PlaylistEntity e LEFT JOIN Track t ON t.id = e.trackId
           WHERE t.id IS NULL OR e.databaseUuid IS NOT ?
              OR t.originTrackId IS NOT t.id OR t.originDatabaseUuid IS NOT ? LIMIT 1""",
        (source_uuid, source_uuid),
    ).fetchone()
    if invalid is not None:
        raise EngineUsbError(f"Unresolved or non-local playlist track: {invalid[0]}")
    _prune_tracks(db)
    for table in ("PreparelistEntity", "Smartlist", "Pack"):
        db.execute(f"DELETE FROM {table}")


def _prune_tracks(db: sqlite3.Connection) -> None:
    db.execute("DELETE FROM Track WHERE id NOT IN (SELECT trackId FROM PlaylistEntity)")
    db.execute(
        "DELETE FROM AlbumArt WHERE id NOT IN "
        "(SELECT albumArtId FROM Track WHERE albumArtId IS NOT NULL)"
    )


def _assets(
    db: sqlite3.Connection,
    library: Path,
    target: Path,
    source_uuid: str,
    device_uuid: str,
    hashes: HashCache,
) -> dict[str, Entry]:
    files: dict[str, Entry] = {}
    owners: dict[str, Path] = {}

    def staged(relative: PurePosixPath, source: Path) -> None:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        files[f"{LIBRARY}/{relative}"] = Entry(
            generation.file_sha256(destination), destination.stat().st_size
        )

    tracks = db.execute(
        """SELECT t.id, t.path, t.isAnalyzed, length(p.beatData)
           FROM Track t LEFT JOIN PerformanceData p ON p.trackId = t.id"""
    ).fetchall()
    if not tracks:
        raise EngineUsbError("No tracks in the selected playlists")
    for track_id, path, analyzed, grid_bytes in tracks:
        if not analyzed or not grid_bytes:
            raise EngineUsbError(f"Track {track_id} has no saved beat grid: {path}")
        audio = (library / path.replace("\\", "/")).resolve(strict=True)
        if not audio.is_relative_to(library.parent) or not audio.is_file():
            raise EngineUsbError(f"Track is outside the media drive or not a file: {path}")
        digest, size = hashes.sha256(audio)
        if size >= _FAT32_MAX:
            raise EngineUsbError(f"Track exceeds the FAT32 file size limit: {audio}")
        relative = _stick_path(audio, library.parent)
        if owners.setdefault(str(relative).casefold(), audio) != audio:
            raise EngineUsbError(f"Two different files map to the stick path {relative}")
        files[f"{LIBRARY}/{relative}"] = Entry(digest, size, source=audio)
        db.execute(
            "UPDATE Track SET path = ?, filename = ? WHERE id = ?",
            (str(relative), relative.name, track_id),
        )
        staged(
            PurePosixPath(_OVERVIEW, device_uuid, f"{track_id}.rgb"),
            library / _OVERVIEW / source_uuid / f"{track_id}.rgb",
        )
    for (digest,) in db.execute("SELECT DISTINCT hash FROM AlbumArt WHERE hash IS NOT NULL"):
        name = base64.urlsafe_b64encode(digest).rstrip(b"=").decode() + ".jpg"
        staged(PurePosixPath("Artwork", name), library / "Artwork" / name)
    return files


def _stick_path(audio: Path, root: Path) -> PurePosixPath:
    parts = audio.relative_to(root).parts
    parts = parts[1:] if parts[0] == "library" else parts
    return PurePosixPath("Music", *(_UNSAFE.sub("_", part).rstrip(". ") for part in parts))


def adopt(
    export: Generation,
    stick_database: Path | None,
    work: Path,
    selected: frozenset[tuple[str, ...]] | None = None,
) -> Generation:
    """Point tracks the stick already has at the audio paths it uses, so that audio is kept."""
    existing: dict[tuple[str, int], str] = {}
    if stick_database is not None:
        with closing(sqlite3.connect(stick_database.as_uri() + "?mode=ro", uri=True)) as stick:
            existing.update(
                ((origin, track_id), path)
                for origin, track_id, path in stick.execute(
                    "SELECT originDatabaseUuid, originTrackId, path FROM Track"
                )
            )
    shutil.rmtree(work, ignore_errors=True)
    tree = work / generation.TREE
    database = tree / DATABASE
    database.parent.mkdir(parents=True)
    shutil.copyfile(export.local(DATABASE), database)
    for shared in ("Artwork", "Database2/OverviewData"):
        (tree / LIBRARY / shared).symlink_to(export.tree / LIBRARY / shared)
    renamed: dict[str, str] = {}
    with closing(sqlite3.connect(database)) as db, db:
        names = export.files.keys() - {DATABASE}
        if selected is not None:
            names = _retain_playlists(db, selected)
        for track_id, origin, origin_id, path in db.execute(
            "SELECT id, originDatabaseUuid, originTrackId, path FROM Track"
        ).fetchall():
            old = existing.get((origin, origin_id))
            if old is None or old == path:
                continue
            relative = PurePosixPath(old)
            if (
                not relative.is_relative_to("Music")
                or len(relative.parts) < 2
                or ".." in relative.parts
            ):
                raise EngineUsbError(f"Invalid stick audio path: {old}")
            renamed[f"{LIBRARY}/{path}"] = f"{LIBRARY}/{relative}"
            db.execute(
                "UPDATE Track SET path = ?, filename = ? WHERE id = ?",
                (old, PurePosixPath(old).name, track_id),
            )
    files = {renamed.get(name, name): export.files[name] for name in names}
    if len(files) != len(names):
        raise EngineUsbError("Two tracks would share a stick path")
    files[DATABASE] = Entry(generation.file_sha256(database), database.stat().st_size)
    return Generation(work, files, export.activation)


def _retain_playlists(db: sqlite3.Connection, selected: frozenset[tuple[str, ...]]) -> set[str]:
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA recursive_triggers = ON")
    paths: dict[tuple[str, ...], int] = {}
    for list_id, encoded in db.execute("""
        WITH RECURSIVE tree(id, path) AS (
            SELECT id, json_array(title) FROM Playlist WHERE parentListId = 0
            UNION ALL
            SELECT p.id, json_insert(t.path, '$[#]', p.title)
            FROM Playlist p JOIN tree t ON p.parentListId = t.id
        ) SELECT id, path FROM tree
    """):
        path = tuple(json.loads(encoded))
        if path in paths:
            raise EngineUsbError(f"Ambiguous playlist path: {' / '.join(path)}")
        paths[path] = list_id
    if selected - paths.keys():
        raise EngineUsbError("Playlist selection is not present in the prepared export")
    kept = {path[:i] for path in selected for i in range(1, len(path) + 1)}
    db.executemany(
        "DELETE FROM Playlist WHERE id = ?",
        ((list_id,) for path, list_id in paths.items() if path not in kept),
    )
    db.executemany(
        "DELETE FROM PlaylistEntity WHERE listId = ?",
        ((paths[path],) for path in kept - selected),
    )
    _prune_tracks(db)
    device = db.execute("SELECT uuid FROM Information").fetchone()[0]
    files: set[str] = set()
    for track_id, path in db.execute("SELECT id, path FROM Track"):
        files.update((f"{LIBRARY}/{path}", f"{LIBRARY}/{_OVERVIEW}/{device}/{track_id}.rgb"))
    for (digest,) in db.execute("SELECT DISTINCT hash FROM AlbumArt WHERE hash IS NOT NULL"):
        name = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        files.add(f"{LIBRARY}/Artwork/{name}.jpg")
    return files


def _device_uuid(path: Path) -> uuid.UUID:
    """Kept across builds: overview paths include it, so a new one would resend every file."""
    if path.is_file():
        return uuid.UUID(json.loads(path.read_text())["uuid"])
    device = uuid.uuid4()
    path.write_text(json.dumps({"uuid": str(device)}))
    return device


@dataclass(frozen=True)
class Review:
    changes: tuple[Change, ...]
    approval: str
    engine_sha256: str
    stick_sha256: str

    @property
    def selected(self) -> tuple[Change, ...]:
        return tuple(change for change in self.changes if change.field != "main_cue")


def review(library: Path, device_database: Path) -> Review:
    """Differences between a device's Engine database and the library, with the code that
    approves exactly these two databases."""
    current = capture(library / "Database2" / "m.db")
    device = capture(device_database)
    payload = f"ignore-main-cue:{current.sha256}:{device.sha256}"
    approval = hashlib.sha256(payload.encode()).hexdigest()[:16]
    return Review(diff(current, device), approval, current.sha256, device.sha256)


def apply_review(library: Path, device_database: Path, approval: str) -> Review:
    """Write the device's value of every reviewed difference into the library."""
    result = review(library, device_database)
    if result.approval != approval:
        raise EngineUsbError("The library or the stick changed since the review; review again")
    if result.selected:
        publish(
            library / "Database2" / "m.db",
            lambda connection: apply_device_edits(connection, device_database, result.selected),
        )
    return result
