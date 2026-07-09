"""Read UTF-8 .m3u8 playlists into import-side data models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImportedTrack:
    """A single track entry parsed from an M3U8 file."""

    path: str
    title: str
    artist: str
    duration_seconds: int | None


@dataclass(frozen=True)
class ImportedPlaylist:
    """A complete M3U8 playlist with its relative directory path."""

    relative_dir: Path
    name: str
    tracks: tuple[ImportedTrack, ...]


class M3uReadError(RuntimeError):
    """Raised when an M3U8 file cannot be read or parsed."""


def read_m3u8(path: Path) -> tuple[ImportedTrack, ...]:
    """Parse a single .m3u8 file into an ordered sequence of tracks."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise M3uReadError(f"Cannot read M3U file: {path}") from exc

    return _parse_m3u8_text(text)


def discover_m3u8_files(import_dir: Path) -> list[Path]:
    """Find all .m3u8 files under import_dir, sorted deterministically."""
    if not import_dir.is_dir():
        raise M3uReadError(f"Import directory does not exist: {import_dir}")
    return sorted(import_dir.rglob("*.m3u8"))


def read_import_tree(import_dir: Path) -> list[ImportedPlaylist]:
    """Discover and parse all .m3u8 files under import_dir."""
    m3u_files = discover_m3u8_files(import_dir)
    playlists: list[ImportedPlaylist] = []

    for m3u_path in m3u_files:
        relative_dir = m3u_path.parent.relative_to(import_dir)
        name = m3u_path.stem
        tracks = read_m3u8(m3u_path)
        playlists.append(
            ImportedPlaylist(
                relative_dir=relative_dir,
                name=name,
                tracks=tracks,
            )
        )

    return playlists


def _parse_m3u8_text(text: str) -> tuple[ImportedTrack, ...]:
    """Parse #EXTM3U-formatted text into tracks."""
    lines = text.splitlines()
    tracks: list[ImportedTrack] = []

    pending_duration: int | None = None
    pending_title: str | None = None
    pending_artist: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped == "#EXTM3U":
            continue

        if stripped.startswith("#EXTINF:"):
            duration, title, artist = _parse_extinf(stripped)
            pending_duration = duration
            pending_title = title
            pending_artist = artist
            continue

        if stripped.startswith("#"):
            continue

        # This is a track path line
        path = stripped
        tracks.append(
            ImportedTrack(
                path=path,
                title=pending_title or "Unknown Title",
                artist=pending_artist or "Unknown Artist",
                duration_seconds=pending_duration,
            )
        )
        pending_duration = None
        pending_title = None
        pending_artist = None

    return tuple(tracks)


def _parse_extinf(line: str) -> tuple[int | None, str, str]:
    """Parse an #EXTINF line into (duration, title, artist)."""
    # Format: #EXTINF:<duration>,<artist> - <title>
    payload = line[len("#EXTINF:") :]
    comma_idx = payload.find(",")
    if comma_idx < 0:
        return None, "Unknown Title", "Unknown Artist"

    duration_part = payload[:comma_idx]
    meta_part = payload[comma_idx + 1 :]

    try:
        duration = int(duration_part)
    except ValueError:
        duration = None

    if duration is not None and duration < 0:
        duration = None

    title, artist = _split_artist_title(meta_part)
    return duration, title, artist


def _split_artist_title(meta: str) -> tuple[str, str]:
    """Split 'Artist - Title' into (title, artist)."""
    separator = " - "
    idx = meta.find(separator)
    if idx >= 0:
        artist = meta[:idx].strip()
        title = meta[idx + len(separator) :].strip()
        if title:
            return title, artist or "Unknown Artist"

    return meta.strip() or "Unknown Title", "Unknown Artist"
