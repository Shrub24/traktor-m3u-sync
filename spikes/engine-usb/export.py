"""Stage a standalone Engine USB tree from a closed Engine 3.0.2 media library."""

import argparse
import base64
import re
import shutil
import sqlite3
import tempfile
import uuid
from contextlib import closing
from pathlib import Path

from review import checksum


def select_tracks(db: sqlite3.Connection, root: str | None, source_uuid: str) -> None:
    if root is not None:
        roots = db.execute(
            "SELECT id FROM Playlist WHERE parentListId = 0 AND title = ?", (root,)
        ).fetchall()
        if len(roots) != 1:
            raise ValueError(f"Expected one top-level playlist named {root!r}")
        db.execute("DELETE FROM Playlist WHERE parentListId = 0 AND id <> ?", roots[0])

    invalid = db.execute(
        """SELECT e.trackId FROM PlaylistEntity e LEFT JOIN Track t ON t.id = e.trackId
           WHERE t.id IS NULL OR e.databaseUuid IS NOT ?
              OR t.originTrackId IS NOT t.id OR t.originDatabaseUuid IS NOT ? LIMIT 1""",
        (source_uuid, source_uuid),
    ).fetchone()
    if invalid is not None:
        raise ValueError(f"Unresolved or non-local playlist track: {invalid[0]}")
    db.execute("DELETE FROM Track WHERE id NOT IN (SELECT trackId FROM PlaylistEntity)")
    db.execute(
        "DELETE FROM AlbumArt WHERE id NOT IN "
        "(SELECT albumArtId FROM Track WHERE albumArtId IS NOT NULL)"
    )
    for table in ("PreparelistEntity", "Smartlist", "Pack"):
        db.execute(f"DELETE FROM {table}")


def copy_assets(
    db: sqlite3.Connection, source: Path, target: Path, source_uuid: str, device_uuid: str
) -> None:
    overview = Path("Database2/OverviewData")
    (target / overview / device_uuid).mkdir(parents=True)
    (target / "Music").mkdir()
    (target / "Artwork").mkdir()
    tracks = db.execute(
        """SELECT t.id, t.path, t.isAnalyzed, length(p.beatData)
           FROM Track t LEFT JOIN PerformanceData p ON p.trackId = t.id"""
    ).fetchall()
    if not tracks:
        raise ValueError("No tracks in selected playlists")
    for track_id, path, analyzed, grid_bytes in tracks:
        if not analyzed or not grid_bytes:
            raise ValueError(f"Track {track_id} has no saved grid: {path}")
        audio = (source / path.replace("\\", "/")).resolve(strict=True)
        if not audio.is_relative_to(source.parent) or not audio.is_file():
            raise ValueError(f"Track path is outside the media drive or not a file: {path}")
        if audio.stat().st_size >= 2**32:
            raise ValueError(f"Track exceeds the FAT32 file size limit: {audio}")
        filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", audio.name).rstrip(". ")
        directory = Path("Music") / str(track_id)
        (target / directory).mkdir()
        copied = target / directory / "audio.part"
        shutil.copyfile(audio, copied)
        relative = directory / checksum(copied) / f"{track_id}-{filename}"
        (target / relative).parent.mkdir()
        copied.rename(target / relative)
        shutil.copyfile(
            source / overview / source_uuid / f"{track_id}.rgb",
            target / overview / device_uuid / f"{track_id}.rgb",
        )
        db.execute(
            "UPDATE Track SET path = ?, filename = ? WHERE id = ?",
            (relative.as_posix(), relative.name, track_id),
        )

    for (digest,) in db.execute("SELECT DISTINCT hash FROM AlbumArt WHERE hash IS NOT NULL"):
        name = base64.urlsafe_b64encode(digest).rstrip(b"=").decode() + ".jpg"
        shutil.copyfile(source / "Artwork" / name, target / "Artwork" / name)


def stage(source: Path, output: Path, root: str | None) -> None:
    source = source.resolve(strict=True)
    if output.exists() or output.is_symlink():
        raise FileExistsError(output)
    if output.resolve().is_relative_to(source):
        raise ValueError("Output must not be inside the source library")
    with tempfile.TemporaryDirectory(prefix=".engine-usb-", dir=output.parent) as tmp:
        tree = Path(tmp) / "tree"
        library = tree / "Engine Library"
        database = library / "Database2/m.db"
        database.parent.mkdir(parents=True)
        uri = (source / "Database2/m.db").as_uri() + "?mode=ro"
        with (
            closing(sqlite3.connect(uri, uri=True)) as original,
            closing(sqlite3.connect(database)) as db,
        ):
            original.backup(db)
            source_uuid, major, minor, patch = db.execute(
                "SELECT uuid, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch "
                "FROM Information"
            ).fetchone()
            if (major, minor, patch) != (3, 0, 2):
                raise ValueError(f"Unsupported Engine schema: {major}.{minor}.{patch}")
            uuid.UUID(source_uuid)
            device_uuid = str(uuid.uuid4())
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA recursive_triggers = ON")
            with db:
                select_tracks(db, root, source_uuid)
                copy_assets(db, source, library, source_uuid, device_uuid)
                db.execute(
                    "UPDATE Information SET uuid = ?, lastRekordBoxLibraryImportReadCounter = NULL",
                    (device_uuid,),
                )
                if (
                    db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                    or db.execute("PRAGMA foreign_key_check").fetchone()
                ):
                    raise ValueError("Staged database failed integrity checks")
            playlists, memberships, tracks = db.execute(
                "SELECT (SELECT count(*) FROM Playlist), "
                "(SELECT count(*) FROM PlaylistEntity), (SELECT count(*) FROM Track)"
            ).fetchone()
        tree.rename(output)
    print(
        f"{output}: {playlists} playlist nodes, {memberships} memberships, "
        f"{tracks} tracks, device {device_uuid}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="source Engine Library directory (Engine closed)")
    parser.add_argument("output", type=Path, help="new output directory (parent must exist)")
    parser.add_argument("--root", help="export only this top-level playlist and its descendants")
    args = parser.parse_args()
    stage(args.source, args.output, args.root)


if __name__ == "__main__":
    main()
