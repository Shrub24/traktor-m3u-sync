from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from traktor_nml_utils.models.collection import Nml, Nodetype

INVALID_NAME_CHARACTERS: Final[set[str]] = set('<>:"/\\|?*')


@dataclass(frozen=True)
class ExportWarning:
    code: str
    message: str
    playlist: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class PlaylistTrackSource:
    primarykey_path: str | None
    location_dir: str | None
    location_file: str | None
    location_volume: str | None
    title: str
    artist: str
    duration_seconds: int | None


@dataclass(frozen=True)
class PlaylistNodeExport:
    folder_parts: tuple[str, ...]
    playlist_name: str
    tracks: tuple[PlaylistTrackSource, ...]


@dataclass(frozen=True)
class ExportTrack:
    path: str
    title: str
    artist: str
    duration_seconds: int | None


def extract_playlist_nodes(nml: Nml) -> tuple[list[PlaylistNodeExport], list[ExportWarning]]:
    playlists: list[PlaylistNodeExport] = []
    warnings: list[ExportWarning] = []

    root_node = nml.playlists.node if nml.playlists is not None else None
    if root_node is None:
        return playlists, warnings

    _walk_node(root_node, folder_parts=(), playlists=playlists, warnings=warnings)
    return playlists, warnings


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
    playlists: list[PlaylistNodeExport],
    warnings: list[ExportWarning],
) -> None:
    node_name = node.name or "unnamed"
    node_type = (node.type or "").upper()

    if node_type == "SMARTLIST" or node.smartplaylist is not None:
        warnings.append(
            ExportWarning(
                code="smartlist_skipped",
                message="Skipping unsupported smartlist during export",
                playlist=_join_playlist_name(folder_parts, node_name),
            )
        )
        return

    if node_type == "PLAYLIST" and node.playlist is not None:
        playlists.append(
            PlaylistNodeExport(
                folder_parts=folder_parts,
                playlist_name=node_name,
                tracks=tuple(
                    PlaylistTrackSource(
                        primarykey_path=(
                            entry.primarykey.key if entry.primarykey is not None else None
                        ),
                        location_dir=(entry.location.dir if entry.location is not None else None),
                        location_file=(entry.location.file if entry.location is not None else None),
                        location_volume=(
                            entry.location.volume if entry.location is not None else None
                        ),
                        title=entry.title or "Unknown Title",
                        artist=entry.artist or "Unknown Artist",
                        duration_seconds=entry.info.playtime if entry.info is not None else None,
                    )
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
        _walk_node(child, folder_parts=next_folder_parts, playlists=playlists, warnings=warnings)


def _join_playlist_name(folder_parts: tuple[str, ...], playlist_name: str) -> str:
    if not folder_parts:
        return playlist_name
    return "/".join((*folder_parts, playlist_name))
