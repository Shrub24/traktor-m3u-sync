"""Read a Traktor collection.nml into the internal model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from traktor_nml_utils import TraktorCollection
from traktor_nml_utils.models.collection import Entrytype, Nml, Nodetype

from ...contracts import AdapterWarning
from ...model import Playlist, Track
from ...paths.traktor import PathTranslationError, TraktorPathMapping

INVALID_NAME_CHARACTERS: Final[set[str]] = set('<>:"/\\|?*')


class NmlReadError(RuntimeError):
    """Raised when a collection file cannot be loaded."""


@dataclass(frozen=True)
class NmlPlaylists:
    playlists: tuple[Playlist, ...]
    warnings: tuple[AdapterWarning, ...]


def load_collection(path: Path) -> TraktorCollection:
    expanded_path = path.expanduser()
    try:
        return TraktorCollection(path=expanded_path)
    except Exception as exc:  # pragma: no cover - library error surface
        raise NmlReadError(f"Failed to load Traktor collection: {expanded_path}") from exc


def read_playlists(nml: Nml, mapping: TraktorPathMapping) -> NmlPlaylists:
    """Traverse the playlist tree, translating every entry path into library space."""
    playlists: list[Playlist] = []
    warnings: list[AdapterWarning] = []

    root_node = nml.playlists.node if nml.playlists is not None else None
    if root_node is None:
        return NmlPlaylists(playlists=(), warnings=())

    _walk_node(root_node, folder_parts=(), playlists=playlists, warnings=warnings, mapping=mapping)
    return NmlPlaylists(playlists=tuple(playlists), warnings=tuple(warnings))


def sanitize_component(name: str) -> str:
    sanitized = "".join(
        "_" if character in INVALID_NAME_CHARACTERS else character for character in name
    )
    collapsed = sanitized.strip().strip(".")
    return collapsed or "unnamed"


def _walk_node(
    node: Nodetype,
    *,
    folder_parts: tuple[str, ...],
    playlists: list[Playlist],
    warnings: list[AdapterWarning],
    mapping: TraktorPathMapping,
) -> None:
    node_name = node.name or "unnamed"
    node_type = (node.type or "").upper()

    if node_type == "SMARTLIST" or node.smartplaylist is not None:
        warnings.append(
            AdapterWarning(
                code="smartlist_skipped",
                message="Skipping unsupported smartlist during import",
                playlist=_join_playlist_name(folder_parts, node_name),
            )
        )
        return

    if node_type == "PLAYLIST" and node.playlist is not None:
        label = _join_playlist_name(folder_parts, node_name)
        playlists.append(
            Playlist(
                name=node_name,
                folder_path=folder_parts,
                tracks=tuple(
                    _entry_to_track(entry, playlist=label, warnings=warnings, mapping=mapping)
                    for entry in node.playlist.entry
                ),
            )
        )

    next_folder_parts = folder_parts
    if node_type == "FOLDER" and node_name != "$ROOT":
        next_folder_parts = (*folder_parts, node_name)

    if node.subnodes is None:
        return

    for child in node.subnodes.node:
        _walk_node(
            child,
            folder_parts=next_folder_parts,
            playlists=playlists,
            warnings=warnings,
            mapping=mapping,
        )


def _entry_to_track(
    entry: Entrytype,
    *,
    playlist: str,
    warnings: list[AdapterWarning],
    mapping: TraktorPathMapping,
) -> Track:
    title = entry.title or ""
    artist = entry.artist or ""
    duration_seconds = _playtime_seconds(entry)
    raw_path: str | None = None
    try:
        raw_path = mapping.entry_path(entry)
        return Track(
            title=title,
            artist=artist,
            path=mapping.to_rel_path(raw_path),
            raw_path=raw_path,
            duration_seconds=duration_seconds,
        )
    except PathTranslationError as exc:
        warnings.append(
            AdapterWarning(
                code="path_translation_failed",
                message="Skipping track with unmappable path",
                playlist=playlist,
                detail=str(exc),
            )
        )
        return Track(
            title=title,
            artist=artist,
            raw_path=raw_path,
            duration_seconds=duration_seconds,
        )


def _playtime_seconds(entry: Entrytype) -> int | None:
    if entry.info is None or entry.info.playtime is None:
        return None
    return entry.info.playtime // 1000


def _join_playlist_name(folder_parts: tuple[str, ...], playlist_name: str) -> str:
    if not folder_parts:
        return playlist_name
    return "/".join((*folder_parts, playlist_name))
