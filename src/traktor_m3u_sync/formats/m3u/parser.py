"""Parse .m3u8 files and directory trees."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

_EXTINF: Final = re.compile(r"^#EXTINF:(-?\d+),(.*)$")
_KNOWN_SUFFIXES: Final[frozenset[str]] = frozenset(
    {".mp3", ".wav", ".aiff", ".aif", ".flac", ".ogg", ".m4a", ".m4b", ".m4r", ".opus", ".wma"}
)


class M3uReadError(RuntimeError):
    """Raised when an .m3u8 file cannot be read."""


@dataclass(frozen=True)
class ParsedTrack:
    path: str
    title: str
    artist: str
    duration_seconds: int | None


@dataclass(frozen=True)
class ParsedPlaylist:
    name: str
    relative_dir: Path
    tracks: tuple[ParsedTrack, ...]


def read_m3u8(path: Path) -> tuple[ParsedTrack, ...]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise M3uReadError(f"Cannot read {path}: {exc.strerror}") from exc
    except UnicodeDecodeError as exc:
        raise M3uReadError(f"Cannot read {path}: not valid UTF-8") from exc

    tracks: list[ParsedTrack] = []
    pending: tuple[str, str, int | None] | None = None

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            pending = _parse_extinf(line)
            continue
        if line.startswith("#"):
            continue
        if _looks_like_track(line):
            title, artist, duration = pending or ("Unknown Title", "Unknown Artist", None)
            tracks.append(
                ParsedTrack(path=line, title=title, artist=artist, duration_seconds=duration)
            )
        pending = None

    return tuple(tracks)


def read_import_tree(root: Path) -> tuple[ParsedPlaylist, ...]:
    if not root.is_dir():
        raise M3uReadError(f"Import directory does not exist: {root}")

    m3u_paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in (".m3u", ".m3u8")
    )
    playlists: list[ParsedPlaylist] = []

    for m3u_path in m3u_paths:
        relative_dir = m3u_path.parent.relative_to(root)
        playlists.append(
            ParsedPlaylist(
                name=m3u_path.stem,
                relative_dir=relative_dir,
                tracks=read_m3u8(m3u_path),
            )
        )

    return tuple(playlists)


def _parse_extinf(line: str) -> tuple[str, str, int | None]:
    match = _EXTINF.match(line)
    if match is None:
        return "Unknown Title", "Unknown Artist", None

    duration_raw, display = match.groups()
    duration = int(duration_raw) if duration_raw != "-1" else None

    if " - " in display:
        artist, _, title = display.partition(" - ")
    else:
        artist, title = "Unknown Artist", display

    return title.strip() or "Unknown Title", artist.strip() or "Unknown Artist", duration


def _looks_like_track(text: str) -> bool:
    if text.startswith("/") or text.startswith("../"):
        return True
    suffix = Path(text).suffix.lower()
    return suffix in _KNOWN_SUFFIXES
