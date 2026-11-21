"""Render a DJ performance snapshot as rekordbox playlist-sharing XML."""

import math
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from pathlib import Path
from urllib.parse import quote, urljoin

from ...model.performance import GridMarker, Performance, PlaylistNode, Snapshot, TrackRef
from ...paths.uri import FileUriMapping
from .exporter import document, playlist_node, publish_xml

_NOTES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")


def write_snapshot(snapshot: Snapshot, locations: FileUriMapping, output: Path) -> None:
    root, collection = document(len(snapshot.tracks))
    ids: dict[TrackRef, int] = {}
    for track_id, entry in enumerate(snapshot.tracks, 1):
        ids[entry.ref] = track_id
        info = entry.info
        track = ET.SubElement(
            collection,
            "TRACK",
            TrackID=str(track_id),
            Name=info.title,
            Artist=info.artist,
            Album=info.album,
            Genre=info.genre,
            Label=info.label,
            Location=urljoin(locations.music_folder(), quote(entry.path, safe="/")),
        )
        for name, value in (
            ("TotalTime", info.duration),
            ("Year", info.year),
            ("Size", info.file_size),
            ("BitRate", info.bitrate),
            ("SampleRate", info.sample_rate),
        ):
            if value is not None:
                track.set(name, str(value))
        _performance(track, entry.performance)
    tree = ET.Element("NODE", Type="0", Name="ROOT", Count=str(len(snapshot.playlists)))
    tree.extend(_playlist(node, ids) for node in snapshot.playlists)
    publish_xml(root, tree, output)


def _playlist(node: PlaylistNode, ids: Mapping[TrackRef, int]) -> ET.Element:
    if not node.children:
        return playlist_node(node.name, [ids[ref] for ref in node.tracks])
    if node.tracks:
        raise ValueError(f"Playlist {node.name!r} holds both tracks and playlists")
    folder = ET.Element("NODE", Type="0", Name=node.name, Count=str(len(node.children)))
    folder.extend(_playlist(child, ids) for child in node.children)
    return folder


def _tempos(grid: Sequence[GridMarker]) -> list[tuple[float, float, int]]:
    anchors: list[tuple[float, float, int]] = []
    for start, end in zip(grid, grid[1:]):
        if end.position <= start.position or end.beat <= start.beat:
            raise ValueError("Grid markers are out of order")
        interval = (end.position - start.position) / (end.beat - start.beat)
        skip = max(0, math.ceil(-start.position / interval))
        if skip < end.beat - start.beat:
            position = max(0.0, start.position + skip * interval)
            anchors.append((position, 60 / interval, (start.beat + skip) % 4 + 1))
    return anchors


def _performance(track: ET.Element, performance: Performance) -> None:
    if (key := performance.key) is not None:
        track.set("Tonality", _NOTES[key.tonic] + ("m" if key.minor else ""))
    anchors = _tempos(performance.grid)
    if anchors:
        track.set("AverageBpm", f"{anchors[0][1]:.9f}")
    for position, bpm, beat in anchors:
        ET.SubElement(
            track,
            "TEMPO",
            Inizio=f"{position:.9f}",
            Bpm=f"{bpm:.9f}",
            Metro="4/4",
            Battito=str(beat),
        )
    if (start := performance.hot_cues.get(1)) is not None:
        ET.SubElement(
            track, "POSITION_MARK", Name=start.label, Type="0", Start=str(start.position), Num="-1"
        )
    for slot, cue in sorted(performance.hot_cues.items()):
        ET.SubElement(
            track,
            "POSITION_MARK",
            Name=cue.label,
            Type="0",
            Start=str(cue.position),
            Num=str(slot - 1),
        )
    for _, loop in sorted(performance.loops.items()):
        ET.SubElement(
            track,
            "POSITION_MARK",
            Name=loop.label,
            Type="4",
            Start=str(loop.start),
            End=str(loop.end),
            Num="-1",
        )
