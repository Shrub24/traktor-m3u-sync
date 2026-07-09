from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath

from .config import LibraryConfig
from .playlist_tree import PlaylistTrackSource


class PathTranslationError(ValueError):
    """Raised when a Traktor path cannot be translated into an M3U path."""


class ReversePathTranslationError(ValueError):
    """Raised when an M3U path cannot be reverse-translated into Traktor space."""


def translate_track_path(track: PlaylistTrackSource, library: LibraryConfig) -> str:
    source_path = _select_source_path(track)

    try:
        relative_path = source_path.relative_to(library.traktor_root)
    except ValueError as exc:
        raise PathTranslationError(
            f"Track path '{source_path}' is outside configured "
            f"Traktor root '{library.traktor_root}'"
        ) from exc

    translated_path = library.m3u_root.joinpath(*relative_path.parts)
    return translated_path.as_posix()


def reverse_translate_track_path(m3u_path: str, library: LibraryConfig) -> PureWindowsPath:
    """Reverse-translate an M3U path back into Traktor library space.

    The returned path is suitable for normalizing into a collection entry
    lookup key via ``normalize_for_collection_lookup``.
    """
    posix_path = PurePosixPath(m3u_path)

    relative = _strip_m3u_root_prefix(posix_path, library.m3u_root)

    traktor_path = library.traktor_root.joinpath(*relative.parts)
    return PureWindowsPath(traktor_path)


def normalize_for_collection_lookup(path: PureWindowsPath) -> str:
    """Normalize a Windows path into a Traktor-compatible lookup key.

    Produces a forward-slash form matching the canonical ``PRIMARYKEY`` format:
    ``C:/Music/House/track.mp3``.
    """
    parts = list(path.parts)
    if parts:
        parts[0] = parts[0].rstrip("\\")
    normalized = "/".join(parts)
    return normalized


def _strip_m3u_root_prefix(posix_path: PurePosixPath, m3u_root: PurePosixPath) -> PurePosixPath:
    """Strip the m3u_root prefix from a posix path to get the relative portion."""
    m3u_parts = m3u_root.parts
    path_parts = posix_path.parts

    if not m3u_parts:
        return posix_path

    # For relative roots (e.g. "../music"), resolve the prefix
    if m3u_root.is_absolute():
        if not posix_path.is_absolute():
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' is relative but m3u_root '{m3u_root}' is absolute"
            )
        if len(path_parts) < len(m3u_parts):
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' is shorter than configured m3u_root '{m3u_root}'"
            )
        if path_parts[: len(m3u_parts)] != m3u_parts:
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' does not start with configured m3u_root '{m3u_root}'"
            )
        return PurePosixPath(*path_parts[len(m3u_parts) :])

    # Relative root: resolve by collapsing shared prefix after normalisation
    resolved_root = _resolve_relative_posix(m3u_root)
    resolved_path = _resolve_relative_posix(posix_path)

    root_parts = resolved_root.parts
    rp_parts = resolved_path.parts

    if len(rp_parts) < len(root_parts):
        raise ReversePathTranslationError(
            f"M3U path '{posix_path}' is shorter than resolved m3u_root '{m3u_root}'"
        )
    if rp_parts[: len(root_parts)] != root_parts:
        raise ReversePathTranslationError(
            f"M3U path '{posix_path}' does not fall beneath resolved m3u_root '{m3u_root}'"
        )
    return PurePosixPath(*rp_parts[len(root_parts) :])


def _resolve_relative_posix(path: PurePosixPath) -> PurePosixPath:
    """Collapse leading '..' segments by removing them and one preceding segment."""
    parts = list(path.parts)
    resolved: list[str] = []
    for part in parts:
        if part == ".." and resolved:
            resolved.pop()
        elif part != ".":
            resolved.append(part)
    return PurePosixPath(*resolved) if resolved else PurePosixPath("")


def _select_source_path(track: PlaylistTrackSource) -> PureWindowsPath:
    if track.primarykey_path:
        return _normalize_primarykey_path(track.primarykey_path)

    if track.location_volume and track.location_dir and track.location_file:
        return _reconstruct_location_path(
            volume=track.location_volume,
            directory=track.location_dir,
            file_name=track.location_file,
        )

    raise PathTranslationError("Track is missing both PRIMARYKEY and LOCATION path data")


def _normalize_primarykey_path(value: str) -> PureWindowsPath:
    return PureWindowsPath(value.replace("/", "\\"))


def _reconstruct_location_path(*, volume: str, directory: str, file_name: str) -> PureWindowsPath:
    normalized_directory = directory.replace("/:", "/")
    if normalized_directory.startswith(":/"):
        normalized_directory = normalized_directory[2:]

    parts = [part for part in normalized_directory.split("/") if part]
    return PureWindowsPath(f"{volume}\\").joinpath(*parts, file_name)
