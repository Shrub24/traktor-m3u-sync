"""SQLite store: one rebuildable snapshot of imported playlist state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..config import DEFAULT_STORE_PATH, StoreConfig
from ..contracts import StoreProvenance
from ..model import Playlist, Track
from ..model.identity import dedup_key

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    schema_version INTEGER NOT NULL,
    source_format TEXT,
    imported_at TEXT
);
CREATE TABLE IF NOT EXISTS tracks (
    id INTEGER PRIMARY KEY,
    identity TEXT UNIQUE,
    rel_path TEXT,
    raw_path TEXT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_seconds INTEGER,
    resolved INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS playlists (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    folder_path TEXT NOT NULL,
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS playlist_tracks (
    playlist_id INTEGER NOT NULL,
    track_id INTEGER NOT NULL,
    position INTEGER NOT NULL
);
"""


class StoreError(RuntimeError):
    """Raised when the store cannot be opened or is unusable."""


class StoreSchemaError(StoreError):
    """Raised when the store file was written with a different schema version."""


class StoreNotPopulatedError(StoreError):
    """Raised when an export runs against an empty store."""


def default_store_path() -> Path:
    return DEFAULT_STORE_PATH.expanduser()


class PlaylistStore:
    """Persistent playlist state, rebuilt wholesale on every import."""

    def __init__(self, path: Path, *, read_only: bool = False) -> None:
        self.path = path.expanduser()
        if self.path.is_dir():
            raise StoreError(f"Store path is a directory, not a database file: {self.path}")
        if read_only:
            if not self.path.is_file():
                raise StoreError(f"Store not found for read-only access: {self.path}")
            target: str | Path = f"{self.path.resolve().as_uri()}?mode=ro"
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            target = self.path
        try:
            # busy_timeout: a wholesale import rebuild holds the write lock for the whole
            # run; 30s covers even a large collection rebuild (sqlite3's 5s default is
            # too tight for that).
            self._conn = sqlite3.connect(target, uri=read_only, timeout=30.0)
        except sqlite3.Error as exc:
            raise StoreError(f"Cannot open store at {self.path}: {exc}") from exc
        if read_only:
            self._check_schema_read_only()
        else:
            self._check_schema()

    @classmethod
    def open(cls, config: StoreConfig) -> PlaylistStore:
        return cls(config.path)

    @classmethod
    def open_readonly(cls, config: StoreConfig) -> PlaylistStore:
        """Inspect an existing store without creating or mutating it."""
        return cls(config.path, read_only=True)

    def __enter__(self) -> PlaylistStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        self._conn.close()

    def count_playlists(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM playlists").fetchone()
        return int(row[0]) if row is not None else 0

    def count_tracks(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM tracks").fetchone()
        return int(row[0]) if row is not None else 0

    def provenance(self) -> StoreProvenance:
        """Return the recorded store origin, rejecting provenance-less stores."""
        try:
            row = self._conn.execute("SELECT source_format, imported_at FROM meta").fetchone()
        except sqlite3.Error as exc:
            raise StoreSchemaError(
                f"Store at {self.path} has no provenance; re-run import to rebuild it"
            ) from exc
        if row is None or row[0] is None or row[1] is None:
            raise StoreSchemaError(
                f"Store at {self.path} has no provenance; re-run import to rebuild it"
            )
        return StoreProvenance(source_format=str(row[0]), imported_at=str(row[1]))

    def rebuild(self, playlists: Sequence[Playlist], *, source_format: str) -> None:
        """Replace all store content with the given playlists, recording their origin."""
        imported_at = datetime.now(UTC).isoformat(timespec="seconds")
        with self._conn:
            self._conn.execute(
                "UPDATE meta SET source_format = ?, imported_at = ?",
                (source_format, imported_at),
            )
            self._conn.execute("DELETE FROM playlist_tracks")
            self._conn.execute("DELETE FROM playlists")
            self._conn.execute("DELETE FROM tracks")
            track_ids: dict[str, int] = {}
            for playlist_position, playlist in enumerate(playlists):
                playlist_id = self._insert_playlist(playlist_position, playlist)
                for track_position, track in enumerate(playlist.tracks):
                    track_id = self._track_id(track_ids, track)
                    self._conn.execute(
                        "INSERT INTO playlist_tracks (playlist_id, track_id, position) "
                        "VALUES (?, ?, ?)",
                        (playlist_id, track_id, track_position),
                    )

    def load_playlists(self) -> tuple[Playlist, ...]:
        rows = self._conn.execute(
            """
            SELECT p.id, p.name, p.folder_path, t.identity, t.rel_path, t.raw_path,
                   t.title, t.artist, t.album, t.duration_seconds, t.resolved
            FROM playlists AS p
            LEFT JOIN playlist_tracks AS pt ON pt.playlist_id = p.id
            LEFT JOIN tracks AS t ON t.id = pt.track_id
            ORDER BY p.position, pt.position
            """
        ).fetchall()

        grouped: dict[int, list[Track]] = {}
        meta: dict[int, tuple[str, str]] = {}
        for (
            playlist_id,
            name,
            folder_path,
            identity,
            rel_path,
            raw_path,
            title,
            artist,
            album,
            duration,
            resolved,
        ) in rows:
            if playlist_id not in meta:
                meta[playlist_id] = (name, folder_path)
                grouped[playlist_id] = []
            if title is None:
                continue
            grouped[playlist_id].append(
                Track(
                    title=title,
                    artist=artist,
                    path=rel_path,
                    identity=identity,
                    raw_path=raw_path,
                    album=album,
                    duration_seconds=duration,
                    resolved=bool(resolved),
                )
            )

        return tuple(
            Playlist(
                name=meta[playlist_id][0],
                folder_path=tuple(json.loads(meta[playlist_id][1])),
                tracks=tuple(grouped[playlist_id]),
            )
            for playlist_id in meta
        )

    def _check_schema_read_only(self) -> None:
        try:
            row = self._conn.execute("SELECT schema_version FROM meta").fetchone()
        except sqlite3.Error as exc:
            raise StoreError(f"Store at {self.path} is not an initialized store: {exc}") from exc
        if row is None or int(row[0]) != SCHEMA_VERSION:
            raise StoreSchemaError(
                f"Store at {self.path} has an unusable schema; re-run import to rebuild it"
            )

    def _check_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)
            row = self._conn.execute("SELECT schema_version FROM meta").fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,)
                )
                return
            if int(row[0]) != SCHEMA_VERSION:
                self._reset_schema()

    def _reset_schema(self) -> None:
        """Drop a stale-version store and re-initialize it in place.

        The store is a disposable cache, never migrated: a version mismatch only
        delays the next wholesale rebuild, so write mode resets instead of raising.
        """
        with self._conn:
            self._conn.executescript(
                "DROP TABLE IF EXISTS playlist_tracks; "
                "DROP TABLE IF EXISTS playlists; "
                "DROP TABLE IF EXISTS tracks; "
                "DROP TABLE IF EXISTS meta;"
            )
            self._conn.executescript(_SCHEMA)
            self._conn.execute("INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,))

    def _insert_playlist(self, position: int, playlist: Playlist) -> int:
        cursor = self._conn.execute(
            "INSERT INTO playlists (name, folder_path, position) VALUES (?, ?, ?)",
            (playlist.name, json.dumps(list(playlist.folder_path)), position),
        )
        return int(cursor.lastrowid or 0)

    def _track_id(self, cache: dict[str, int], track: Track) -> int:
        key = dedup_key(track)
        if key is not None:
            cached = cache.get(key)
            if cached is not None:
                return cached
        cursor = self._conn.execute(
            "INSERT INTO tracks (identity, rel_path, raw_path, title, artist, album, "
            "duration_seconds, resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                track.identity,
                track.path,
                track.raw_path,
                track.title,
                track.artist,
                track.album,
                track.duration_seconds,
                int(track.resolved),
            ),
        )
        track_id = int(cursor.lastrowid or 0)
        if key is not None:
            cache[key] = track_id
        return track_id
