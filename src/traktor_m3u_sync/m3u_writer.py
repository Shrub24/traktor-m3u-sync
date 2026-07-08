from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .playlist_tree import ExportTrack


def write_m3u8(path: Path, tracks: Iterable[ExportTrack]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    lines = ["#EXTM3U"]
    for track in tracks:
        lines.append(_format_extinf(track))
        lines.append(track.path)

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _format_extinf(track: ExportTrack) -> str:
    duration = track.duration_seconds if track.duration_seconds is not None else -1
    return f"#EXTINF:{duration},{track.artist} - {track.title}"
