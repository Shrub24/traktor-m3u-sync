from __future__ import annotations

from pathlib import PureWindowsPath

from .config import LibraryConfig
from .playlist_tree import PlaylistTrackSource


class PathTranslationError(ValueError):
    """Raised when a Traktor path cannot be translated into an M3U path."""


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
