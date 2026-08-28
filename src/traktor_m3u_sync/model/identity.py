"""Track identity normalization: path-derived primary, artist+title fallback."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import replace

from ..contracts import AdapterWarning
from . import Playlist, Track

FALLBACK_IDENTITY: str = "artist+title:"

_WHITESPACE = re.compile(r"\s+")


def to_posix(path_text: str) -> str:
    return path_text.replace("\\", "/")


def normalize_identity(rel_path: str) -> str:
    return to_posix(rel_path).casefold()


def fallback_identity(title: str, artist: str) -> str:
    collapsed = _WHITESPACE.sub(" ", f"{artist} - {title}").strip()
    return f"{FALLBACK_IDENTITY}{collapsed.casefold()}"


def identify(track: Track) -> Track:
    """Attach the normalized identity to a track, deriving it from path or metadata."""
    return track if track.identity is not None else _derive(track)


def _derive(track: Track) -> Track:
    if track.path is not None:
        return _with(track, identity=normalize_identity(track.path), resolved=True)
    if track.title and track.artist:
        return _with(track, identity=fallback_identity(track.title, track.artist), resolved=True)
    return _with(track, identity=None, resolved=False)


def identify_playlists(
    playlists: Sequence[Playlist],
) -> tuple[tuple[Playlist, ...], tuple[AdapterWarning, ...]]:
    """Identify every track; flag fallback collisions rather than merging them."""
    identified = _apply(playlists, identify)
    collisions = _fallback_collisions(identified)
    if not collisions:
        return identified, ()

    warnings = tuple(
        AdapterWarning(
            code="ambiguous_identity",
            message="Tracks collide on the artist+title identity; kept apart as unresolved",
            playlist=playlist.name,
            detail=", ".join(
                track.raw_path or f"{track.artist} - {track.title}"
                for track in playlist.tracks
                if _is_fallback(track) and track.identity in collisions
            ),
        )
        for playlist in identified
        if any(_is_fallback(t) and t.identity in collisions for t in playlist.tracks)
    )
    flagged = _apply(
        identified,
        lambda track: (
            _with(track, identity=None, resolved=False)
            if _is_fallback(track) and track.identity in collisions
            else track
        ),
    )
    return flagged, warnings


def dedup_key(track: Track) -> str | None:
    """Dedup discriminator, or None when the track has no identity and no raw path."""
    if track.identity is not None:
        return track.identity
    if track.raw_path is not None:
        return f"raw:{track.raw_path}"
    return None


def unique_identities(tracks: Iterable[Track]) -> tuple[Track, ...]:
    """Distinct tracks by identity; unresolved tracks stay separate."""
    seen: dict[str, Track] = {}
    unkeyed: list[Track] = []
    for track in tracks:
        key = dedup_key(track)
        if key is None:
            unkeyed.append(track)
        else:
            seen.setdefault(key, track)
    return tuple(seen.values()) + tuple(unkeyed)


def _is_fallback(track: Track) -> bool:
    return track.identity is not None and track.path is None


def _fallback_collisions(playlists: Sequence[Playlist]) -> set[str]:
    owners: dict[str, str] = {}
    collisions: set[str] = set()
    for playlist in playlists:
        for track in playlist.tracks:
            if track.identity is None or track.path is not None:
                continue
            raw = track.raw_path or f"{track.artist} - {track.title}"
            if owners.setdefault(track.identity, raw) != raw:
                collisions.add(track.identity)
    return collisions


def _apply(
    playlists: Sequence[Playlist],
    transform: Callable[[Track], Track],
) -> tuple[Playlist, ...]:
    return tuple(
        Playlist(
            name=playlist.name,
            folder_path=playlist.folder_path,
            tracks=tuple(transform(track) for track in playlist.tracks),
        )
        for playlist in playlists
    )


def _with(track: Track, *, identity: str | None, resolved: bool) -> Track:
    return replace(track, identity=identity, resolved=resolved)
