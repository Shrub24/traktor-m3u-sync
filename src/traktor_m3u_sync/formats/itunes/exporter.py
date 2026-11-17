"""iTunes exporter: store playlists to an iTunes Music Library XML plist."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from ...contracts import SyncResult
from ...fs import write_atomic
from ...model import Playlist
from ...paths.uri import FileUriMapping
from ..collection import Collection, collect_tracks
from .writer import ItunesPlaylistEntry, ItunesTrack, build_document, render_document

FORMAT: Final[str] = "itunes"
LIBRARY_PERSISTENT_SEED: Final[str] = "traktor-m3u-sync:library"
MASTER_PLAYLIST_SEED: Final[str] = "traktor-m3u-sync:master-playlist"


def _seed(kind: str, *parts: str) -> str:
    """Lossless canonical serialization: kind prefix plus length-prefixed parts.

    Never delimiter-joins, so ("A/B",) and ("A", "B") produce distinct seeds.
    """
    return "".join(f"{len(part)}:{part}" for part in (kind, *parts))


def _persistent_id(seed: str) -> str:
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16].upper()


class _IdPool:
    """Allocates collision-safe unique 16-hex Persistent IDs within one document.

    Each allocation of a seed consumes the next ``#n`` candidate, so equal seeds
    (duplicate playlist names) never yield equal IDs, and a truncated-hash
    collision with any already-issued ID is resolved by advancing the counter.
    Unchanged store state allocates in the same order, so IDs stay stable.
    """

    def __init__(self) -> None:
        self._next_attempt: dict[str, int] = {}
        self._taken: set[str] = set()

    def allocate(self, seed: str) -> str:
        attempt = self._next_attempt.get(seed, 0)
        persistent_id = _persistent_id(f"{seed}#{attempt}")
        while persistent_id in self._taken:
            attempt += 1
            persistent_id = _persistent_id(f"{seed}#{attempt}")
        self._next_attempt[seed] = attempt + 1
        self._taken.add(persistent_id)
        return persistent_id


@dataclass(frozen=True)
class ItunesExporter:
    locations: FileUriMapping
    output_file: Path
    # Optional worker-side mount; used only for file_missing warnings, never for Locations.
    check_base_path: Path | None = None

    def write(self, playlists: Sequence[Playlist]) -> SyncResult:
        ids = _IdPool()
        collection = collect_tracks(playlists, self.check_base_path)
        tracks = [
            ItunesTrack(
                track_id=entry.track_id,
                persistent_id=ids.allocate(_seed("track", entry.identity)),
                name=entry.track.title,
                artist=entry.track.artist,
                location=self.locations.to_uri(entry.path),
                album=entry.track.album,
                duration_ms=(
                    None
                    if entry.track.duration_seconds is None
                    else entry.track.duration_seconds * 1000
                ),
            )
            for entry in collection.tracks
        ]

        entries = _arrange(playlists, collection, ids)
        document = build_document(
            tracks,
            entries,
            self.locations.music_folder(),
            datetime.now(UTC),
            ids.allocate(_seed("library", LIBRARY_PERSISTENT_SEED)),
        )
        write_atomic(self.output_file, render_document(document))

        counts = {
            "playlists_written": len(playlists),
            "tracks_exported": len(tracks),
            "tracks_skipped": collection.skipped,
            "warnings_emitted": len(collection.warnings),
        }
        return SyncResult(counts=counts, warnings=tuple(collection.warnings))


def _arrange(
    playlists: Sequence[Playlist],
    collection: Collection,
    ids: _IdPool,
) -> list[ItunesPlaylistEntry]:
    entries: list[ItunesPlaylistEntry] = [
        # Master "Library" playlist first, mirroring real iTunes exports:
        # every track in the document, own Persistent ID, Master/All Items set.
        ItunesPlaylistEntry(
            playlist_id=0,
            persistent_id=ids.allocate(_seed("library", MASTER_PLAYLIST_SEED)),
            name="Library",
            items=tuple(sorted(collection.ids.values())),
            master=True,
        )
    ]
    folder_ids: dict[tuple[str, ...], str] = {}

    def add_folders(folder_path: tuple[str, ...]) -> str | None:
        if not folder_path:
            return None
        parent = add_folders(folder_path[:-1])
        known = folder_ids.get(folder_path)
        if known is not None:
            return known
        persistent_id = ids.allocate(_seed("folder", *folder_path))
        folder_ids[folder_path] = persistent_id
        entries.append(
            ItunesPlaylistEntry(
                playlist_id=0,
                persistent_id=persistent_id,
                name=folder_path[-1],
                parent_persistent_id=parent,
                folder=True,
            )
        )
        return persistent_id

    for playlist in playlists:
        parent = add_folders(playlist.folder_path)
        entries.append(
            ItunesPlaylistEntry(
                playlist_id=0,
                persistent_id=ids.allocate(_seed("playlist", *playlist.folder_path, playlist.name)),
                name=playlist.name,
                items=collection.playlist_ids(playlist),
                parent_persistent_id=parent,
            )
        )

    return [replace(entry, playlist_id=index) for index, entry in enumerate(entries, start=1)]
