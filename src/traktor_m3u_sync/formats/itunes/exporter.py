"""iTunes exporter: store playlists to an iTunes Music Library XML plist."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from ...contracts import AdapterWarning, SyncResult, playlist_label
from ...fs import write_atomic
from ...model import Playlist, Track
from ...paths.uri import FileUriMapping
from .writer import ItunesPlaylistEntry, ItunesTrack, build_document, render_document

FORMAT: Final[str] = "itunes"
LIBRARY_PERSISTENT_SEED: Final[str] = "traktor-m3u-sync:library"


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
        warnings: list[AdapterWarning] = []
        skipped = 0
        ids = _IdPool()

        candidates: dict[str, tuple[Track, str]] = {}
        for playlist in playlists:
            for track in playlist.tracks:
                path = track.path
                if track.identity is None or path is None:
                    skipped += 1
                    warnings.append(
                        AdapterWarning(
                            code="track_unresolved",
                            message="Skipping track without a library-relative path",
                            playlist=playlist_label(playlist.folder_path, playlist.name),
                            detail=track.raw_path or f"{track.artist} - {track.title}",
                        )
                    )
                    continue
                candidates.setdefault(track.identity, (track, path))

        tracks: list[ItunesTrack] = []
        track_ids: dict[str, int] = {}
        for track_id, identity in enumerate(sorted(candidates), start=1):
            source, path = candidates[identity]
            if self.check_base_path is not None:
                checked = self.check_base_path / path
                if not checked.exists():
                    warnings.append(
                        AdapterWarning(
                            code="file_missing",
                            message="Track file not found on the local filesystem",
                            detail=checked.as_posix(),
                        )
                    )
            track_ids[identity] = track_id
            tracks.append(
                ItunesTrack(
                    track_id=track_id,
                    persistent_id=ids.allocate(_seed("track", identity)),
                    name=source.title,
                    artist=source.artist,
                    location=self.locations.to_uri(path),
                    album=source.album,
                    duration_ms=(
                        None if source.duration_seconds is None else source.duration_seconds * 1000
                    ),
                )
            )

        entries = _arrange(playlists, track_ids, ids)
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
            "tracks_skipped": skipped,
            "warnings_emitted": len(warnings),
        }
        return SyncResult(counts=counts, warnings=tuple(warnings))


def _arrange(
    playlists: Sequence[Playlist],
    track_ids: Mapping[str, int],
    ids: _IdPool,
) -> list[ItunesPlaylistEntry]:
    entries: list[ItunesPlaylistEntry] = []
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
        items = tuple(
            track_ids[track.identity]
            for track in playlist.tracks
            if track.identity is not None and track.identity in track_ids
        )
        entries.append(
            ItunesPlaylistEntry(
                playlist_id=0,
                persistent_id=ids.allocate(_seed("playlist", *playlist.folder_path, playlist.name)),
                name=playlist.name,
                items=items,
                parent_persistent_id=parent,
            )
        )

    return [replace(entry, playlist_id=index) for index, entry in enumerate(entries, start=1)]
