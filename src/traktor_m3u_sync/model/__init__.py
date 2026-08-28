"""Format-neutral internal playlist model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Track:
    """A track in library-relative space.

    ``path`` is the library-relative POSIX text with original casing and ``identity``
    its normalized dedup key (see ``model.identity``). Tracks with no usable identity
    carry ``resolved=False`` and keep the source spelling in ``raw_path``.
    """

    title: str
    artist: str
    path: str | None = None
    identity: str | None = None
    raw_path: str | None = None
    album: str | None = None
    duration_seconds: int | None = None
    resolved: bool = True


@dataclass(frozen=True)
class Playlist:
    name: str
    folder_path: tuple[str, ...] = ()
    tracks: tuple[Track, ...] = ()
