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
    db.execute("DELETE FROM Track WHERE id NOT IN (SELECT trackId FROM PlaylistEntity)")
    db.execute(
        "DELETE FROM AlbumArt WHERE id NOT IN "
        "(SELECT albumArtId FROM Track WHERE albumArtId IS NOT NULL)"
    )
    for table in ("PreparelistEntity", "Smartlist", "Pack"):
        db.execute(f"DELETE FROM {table}")


def _assets(
    db: sqlite3.Connection,
    library: Path,
    target: Path,
    source_uuid: str,
    device_uuid: str,
    hashes: HashCache,
) -> dict[str, Entry]:
    files: dict[str, Entry] = {}

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
        name = _UNSAFE.sub("_", audio.name).rstrip(". ")
        # Changed audio gets a new path, so it never replaces a file the installed database uses.
        relative = PurePosixPath("Music", str(track_id), digest, f"{track_id}-{name}")
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
