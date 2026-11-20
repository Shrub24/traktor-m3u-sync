"""rekordbox exporter: store playlists to rekordbox's "XML file format for playlists sharing"."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...contracts import SyncResult
from ...fs import write_atomic
from ...model import Playlist
from ...paths.uri import FileUriMapping
from ..collection import Collection, collect_tracks

FORMAT: Final[str] = "rekordbox"
PRODUCT_NAME: Final[str] = "traktor-m3u-sync"
FORMAT_VERSION: Final[str] = "1.0.0"
_FOLDER: Final[str] = "0"
_PLAYLIST: Final[str] = "1"
_KEY_BY_TRACK_ID: Final[str] = "0"


@dataclass(frozen=True)
class RekordboxExporter:
    locations: FileUriMapping
    output_file: Path
    # Optional worker-side mount; used only for file_missing warnings, never for Locations.
    check_base_path: Path | None = None

    def write(self, playlists: Sequence[Playlist]) -> SyncResult:
        collection = collect_tracks(playlists, self.check_base_path)
        root, tracks = document(len(collection.tracks))
        for entry in collection.tracks:
            attributes = {
                "TrackID": str(entry.track_id),
                "Name": entry.track.title,
                "Artist": entry.track.artist,
                "Location": self.locations.to_uri(entry.path),
            }
            if entry.track.album is not None:
                attributes["Album"] = entry.track.album
            if entry.track.duration_seconds is not None:
                attributes["TotalTime"] = str(entry.track.duration_seconds)
            ET.SubElement(tracks, "TRACK", attributes)
        publish_xml(root, _playlist_tree(playlists, collection), self.output_file)

        counts = {
            "playlists_written": len(playlists),
            "tracks_exported": len(collection.tracks),
            "tracks_skipped": collection.skipped,
            "warnings_emitted": len(collection.warnings),
        }
        return SyncResult(counts=counts, warnings=tuple(collection.warnings))


def document(entries: int) -> tuple[ET.Element, ET.Element]:
    root = ET.Element("DJ_PLAYLISTS", Version=FORMAT_VERSION)
    ET.SubElement(root, "PRODUCT", Name=PRODUCT_NAME, Version="", Company="")
    return root, ET.SubElement(root, "COLLECTION", Entries=str(entries))


def publish_xml(document: ET.Element, tree: ET.Element, output: Path) -> None:
    ET.SubElement(document, "PLAYLISTS").append(tree)
    ET.indent(document)
    write_atomic(output, ET.tostring(document, encoding="UTF-8", xml_declaration=True))


def playlist_node(name: str, keys: Sequence[int]) -> ET.Element:
    node = ET.Element(
        "NODE", Type=_PLAYLIST, Name=name, KeyType=_KEY_BY_TRACK_ID, Entries=str(len(keys))
    )
    for key in keys:
        ET.SubElement(node, "TRACK", Key=str(key))
    return node


def _playlist_tree(playlists: Sequence[Playlist], collection: Collection) -> ET.Element:
    root = ET.Element("NODE", Type=_FOLDER, Name="ROOT")
    folders: dict[tuple[str, ...], ET.Element] = {(): root}

    def folder(path: tuple[str, ...]) -> ET.Element:
        if path not in folders:
            folders[path] = ET.SubElement(folder(path[:-1]), "NODE", Type=_FOLDER, Name=path[-1])
        return folders[path]

    for playlist in playlists:
        folder(playlist.folder_path).append(
            playlist_node(playlist.name, collection.playlist_ids(playlist))
        )
    for node in folders.values():
        node.set("Count", str(len(node)))
    return root
