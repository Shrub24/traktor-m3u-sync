"""Render an iTunes Music Library-compatible XML plist document via plistlib."""

from __future__ import annotations

import plistlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

APPLICATION_NAME: Final[str] = "traktor-m3u-sync"
MAJOR_VERSION: Final[int] = 1
MINOR_VERSION: Final[int] = 1


@dataclass(frozen=True)
class ItunesTrack:
    track_id: int
    persistent_id: str
    name: str
    artist: str
    location: str
    album: str | None = None
    duration_ms: int | None = None


@dataclass(frozen=True)
class ItunesPlaylistEntry:
    playlist_id: int
    persistent_id: str
    name: str
    items: tuple[int, ...] = ()
    parent_persistent_id: str | None = None
    folder: bool = False
    master: bool = False


def build_document(
    tracks: Sequence[ItunesTrack],
    playlists: Sequence[ItunesPlaylistEntry],
    music_folder: str,
    date: datetime,
    library_persistent_id: str,
) -> dict[str, Any]:
    return {
        "Major Version": MAJOR_VERSION,
        "Minor Version": MINOR_VERSION,
        "Application Version": APPLICATION_NAME,
        "Date": date,
        "Music Folder": music_folder,
        "Library Persistent ID": library_persistent_id,
        "Tracks": {str(track.track_id): _track_dict(track) for track in tracks},
        "Playlists": [_playlist_dict(entry) for entry in playlists],
    }


def render_document(document: dict[str, Any]) -> bytes:
    return plistlib.dumps(document, fmt=plistlib.FMT_XML)


def _track_dict(track: ItunesTrack) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "Track ID": track.track_id,
        "Name": track.name,
        "Artist": track.artist,
        "Track Type": "File",
        "Location": track.location,
        "Persistent ID": track.persistent_id,
    }
    if track.album is not None:
        entry["Album"] = track.album
    if track.duration_ms is not None:
        entry["Total Time"] = track.duration_ms
    return entry


def _playlist_dict(entry: ItunesPlaylistEntry) -> dict[str, Any]:
    playlist: dict[str, Any] = {
        "Name": entry.name,
        "Playlist ID": entry.playlist_id,
        "Playlist Persistent ID": entry.persistent_id,
        "All Items": True,
    }
    if entry.master:
        playlist["Master"] = True
        playlist["Visible"] = False
    if entry.parent_persistent_id is not None:
        playlist["Parent Persistent ID"] = entry.parent_persistent_id
    if entry.folder:
        playlist["Folder"] = True
    else:
        playlist["Playlist Items"] = [{"Track ID": track_id} for track_id in entry.items]
    return playlist
