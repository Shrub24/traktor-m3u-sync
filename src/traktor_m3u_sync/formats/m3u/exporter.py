"""M3U exporter: store playlists to .m3u8 files."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...contracts import AdapterWarning, SyncResult, playlist_label
from ...model import Playlist, Track
from ...paths.m3u import M3uPathMapping
from .writer import M3uTrack, playlist_file_path, write_m3u8

FORMAT: Final[str] = "m3u"


@dataclass(frozen=True)
class M3uExporter:
    mapping: M3uPathMapping
    output_dir: Path

    def write(self, playlists: Sequence[Playlist]) -> SyncResult:
        root = self.output_dir
        warnings: list[AdapterWarning] = []
        tracks_exported = 0

        for playlist in playlists:
            label = playlist_label(playlist.folder_path, playlist.name)
            tracks = tuple(
                _render(track, self.mapping)
                for track in playlist.tracks
                if _keep(track, label, warnings)
            )
            write_m3u8(playlist_file_path(root, playlist.folder_path, playlist.name), tracks)
            tracks_exported += len(tracks)

        counts = {
            "playlists_written": len(playlists),
            "tracks_exported": tracks_exported,
            "warnings_emitted": len(warnings),
        }
        return SyncResult(counts=counts, warnings=tuple(warnings))


def _keep(track: Track, label: str, warnings: list[AdapterWarning]) -> bool:
    if track.path is not None:
        return True
    warnings.append(
        AdapterWarning(
            code="track_unresolved",
            message="Skipping track without a library-relative path",
            playlist=label,
            detail=track.raw_path or f"{track.artist} - {track.title}",
        )
    )
    return False


def _render(track: Track, mapping: M3uPathMapping) -> M3uTrack:
    return M3uTrack(
        path=mapping.to_full_path(track.path or ""),
        title=track.title,
        artist=track.artist,
        duration_seconds=track.duration_seconds,
    )
