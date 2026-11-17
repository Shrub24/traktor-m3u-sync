"""Track collection shared by the library-file exporters (iTunes, rekordbox)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..contracts import AdapterWarning, playlist_label
from ..model import Playlist, Track


@dataclass(frozen=True)
class CollectedTrack:
    track_id: int
    identity: str
    track: Track
    path: str


@dataclass(frozen=True)
class Collection:
    """Distinct resolvable store tracks with integer IDs assigned in sorted identity order."""

    tracks: tuple[CollectedTrack, ...]
    ids: dict[str, int]
    skipped: int
    warnings: list[AdapterWarning] = field(default_factory=list[AdapterWarning])

    def playlist_ids(self, playlist: Playlist) -> tuple[int, ...]:
        """The playlist's memberships as track IDs, in stored order."""
        return tuple(
            self.ids[track.identity]
            for track in playlist.tracks
            if track.identity is not None and track.identity in self.ids
        )


def collect_tracks(playlists: Sequence[Playlist], check_base_path: Path | None) -> Collection:
    warnings: list[AdapterWarning] = []
    skipped = 0
    candidates: dict[str, tuple[Track, str]] = {}
    for playlist in playlists:
        for track in playlist.tracks:
            if track.identity is None or track.path is None:
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
            candidates.setdefault(track.identity, (track, track.path))

    tracks: list[CollectedTrack] = []
    ids: dict[str, int] = {}
    for track_id, identity in enumerate(sorted(candidates), start=1):
        track, path = candidates[identity]
        if check_base_path is not None and not (check_base_path / path).exists():
            warnings.append(
                AdapterWarning(
                    code="file_missing",
                    message="Track file not found on the local filesystem",
                    detail=(check_base_path / path).as_posix(),
                )
            )
        ids[identity] = track_id
        tracks.append(CollectedTrack(track_id, identity, track, path))
    return Collection(tuple(tracks), ids, skipped, warnings)
