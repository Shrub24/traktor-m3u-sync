"""Write .m3u8 files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

from ...fs import write_atomic

INVALID_NAME_CHARACTERS: Final[set[str]] = set('<>:"/\\|?*')


@dataclass(frozen=True)
class M3uTrack:
    path: str
    title: str
    artist: str
    duration_seconds: int | None


def sanitize_component(name: str) -> str:
    sanitized = "".join(
        "_" if character in INVALID_NAME_CHARACTERS else character for character in name
    )
    collapsed = sanitized.strip().strip(".")
    return collapsed or "unnamed"


def playlist_file_path(output_dir: Path, folder_path: tuple[str, ...], name: str) -> Path:
    folder = output_dir.joinpath(*(sanitize_component(part) for part in folder_path))
    return folder / f"{sanitize_component(name)}.m3u8"


def write_m3u8(path: Path, tracks: Iterable[M3uTrack]) -> None:
    lines = ["#EXTM3U"]
    for track in tracks:
        duration = track.duration_seconds if track.duration_seconds is not None else -1
        lines.append(f"#EXTINF:{duration},{track.artist} - {track.title}")
        lines.append(track.path)
    write_atomic(path, ("\n".join(lines) + "\n").encode("utf-8"))
