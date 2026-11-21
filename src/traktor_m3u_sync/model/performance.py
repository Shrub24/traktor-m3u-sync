"""Format-neutral DJ library snapshot: performance data, track metadata and playlists.

Times are seconds from the start of the audio. Cue and loop slots are numbered from 1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from typing import Any, Literal, cast
from uuid import UUID

SNAPSHOT_VERSION = 2


class SnapshotError(ValueError):
    """Raised when snapshot JSON is malformed or has an unknown version."""


@dataclass(frozen=True)
class Color:
    red: int
    green: int
    blue: int


@dataclass(frozen=True)
class Cue:
    position: float
    label: str
    color: Color


@dataclass(frozen=True)
class Loop:
    start: float
    end: float
    label: str
    color: Color


@dataclass(frozen=True)
class GridMarker:
    """A beat at ``position``; tempo is constant between consecutive markers."""

    position: float
    beat: int


@dataclass(frozen=True)
class Key:
    tonic: int  # pitch class, 0 = C
    minor: bool


@dataclass(frozen=True)
class Performance:
    key: Key | None = None
    grid: tuple[GridMarker, ...] = ()
    main_cue: float | None = None
    hot_cues: Mapping[int, Cue] = field(default_factory=dict[int, Cue])
    loops: Mapping[int, Loop] = field(default_factory=dict[int, Loop])


@dataclass(frozen=True, order=True)
class TrackRef:
    """Engine origin identity, preserved when Engine copies a track to another library."""

    database: UUID
    track_id: int


@dataclass(frozen=True)
class TrackInfo:
    title: str = ""
    artist: str = ""
    album: str = ""
    genre: str = ""
    label: str = ""
    comment: str = ""
    year: int | None = None
    duration: int | None = None  # whole seconds
    bitrate: int | None = None
    sample_rate: int | None = None
    file_size: int | None = None
    artwork: str | None = None  # relative to the library directory


@dataclass(frozen=True)
class TrackPerformance:
    ref: TrackRef
    path: str  # relative to the library directory
    performance: Performance
    info: TrackInfo = TrackInfo()


@dataclass(frozen=True)
class PlaylistNode:
    name: str
    tracks: tuple[TrackRef, ...] = ()
    children: tuple[PlaylistNode, ...] = ()


@dataclass(frozen=True)
class Snapshot:
    library: UUID
    sha256: str
    tracks: tuple[TrackPerformance, ...]
    playlists: tuple[PlaylistNode, ...] = ()


def select(snapshot: Snapshot, root: str | None) -> Snapshot:
    """Select one top-level playlist or all playlists, and only the tracks they hold."""
    nodes = [node for node in snapshot.playlists if root is None or node.name == root]
    if root is not None and len(nodes) != 1:
        raise SnapshotError(f"Expected one top-level playlist named {root!r}")
    refs: set[TrackRef] = set()
    pending = list(nodes)
    while pending:
        node = pending.pop()
        refs.update(node.tracks)
        pending += node.children
    tracks = tuple(track for track in snapshot.tracks if track.ref in refs)
    if len(tracks) != len(refs):
        raise SnapshotError(f"Playlist {root!r} holds tracks missing from the snapshot")
    return Snapshot(snapshot.library, snapshot.sha256, tracks, tuple(nodes))


type Field = Literal["key", "grid", "main_cue", "hot_cues", "loops"]


@dataclass(frozen=True)
class Change:
    ref: TrackRef
    path: str
    field: Field
    slot: int | None
    current: object
    device: object
    title: str
    artist: str


def diff(current: Snapshot, device: Snapshot) -> tuple[Change, ...]:
    """Where a device's tracks differ from the current library; unknown tracks are skipped."""
    library = {track.ref: track for track in current.tracks}
    changes: list[Change] = []
    for track in sorted(device.tracks, key=lambda t: t.ref):
        known = library.get(track.ref)
        if known is None:
            continue
        ours, theirs, path = known.performance, track.performance, known.path
        title, artist = known.info.title, known.info.artist

        def compare(field: Field, slot: int | None, a: object, b: object) -> None:
            if a != b:
                changes.append(Change(track.ref, path, field, slot, a, b, title, artist))

        compare("key", None, ours.key, theirs.key)
        compare("grid", None, ours.grid, theirs.grid)
        compare("main_cue", None, ours.main_cue, theirs.main_cue)
        for slot in sorted(ours.hot_cues.keys() | theirs.hot_cues.keys()):
            compare("hot_cues", slot, ours.hot_cues.get(slot), theirs.hot_cues.get(slot))
        for slot in sorted(ours.loops.keys() | theirs.loops.keys()):
            compare("loops", slot, ours.loops.get(slot), theirs.loops.get(slot))
    return tuple(changes)


def dumps(snapshot: Snapshot) -> str:
    return json.dumps(
        {
            "version": SNAPSHOT_VERSION,
            "library": str(snapshot.library),
            "sha256": snapshot.sha256,
            "tracks": [
                _track_json(track) for track in sorted(snapshot.tracks, key=lambda t: t.ref)
            ],
            "playlists": [_playlist_json(node) for node in snapshot.playlists],
        },
        ensure_ascii=False,
    )


def loads(text: str) -> Snapshot:
    match json.loads(text):
        case {"version": int(version)} if version != SNAPSHOT_VERSION:
            raise SnapshotError(f"Unsupported snapshot version {version}")
        case {
            "version": int(),
            "library": str(library),
            "sha256": str(digest),
            "tracks": tracks,
            "playlists": playlists,
        }:
            return Snapshot(
                _uuid(library),
                digest,
                tuple(_track(t) for t in _items(tracks)),
                tuple(_playlist(p) for p in _items(playlists)),
            )
        case _:
            raise SnapshotError("Malformed snapshot")


def _track_json(track: TrackPerformance) -> dict[str, Any]:
    performance = track.performance
    key = performance.key
    return {
        "database": str(track.ref.database),
        "track_id": track.ref.track_id,
        "path": track.path,
        "key": None if key is None else {"tonic": key.tonic, "minor": key.minor},
        "grid": [[marker.position, marker.beat] for marker in performance.grid],
        "main_cue": performance.main_cue,
        "hot_cues": {
            str(slot): {"position": cue.position, "label": cue.label, "color": _color(cue.color)}
            for slot, cue in sorted(performance.hot_cues.items())
        },
        "loops": {
            str(slot): {
                "start": loop.start,
                "end": loop.end,
                "label": loop.label,
                "color": _color(loop.color),
            }
            for slot, loop in sorted(performance.loops.items())
        },
        "info": {f.name: getattr(track.info, f.name) for f in fields(TrackInfo)},
    }


def _playlist_json(node: PlaylistNode) -> dict[str, Any]:
    return {
        "name": node.name,
        "tracks": [[str(ref.database), ref.track_id] for ref in node.tracks],
        "children": [_playlist_json(child) for child in node.children],
    }


def _color(color: Color) -> list[int]:
    return [color.red, color.green, color.blue]


def _track(data: Any) -> TrackPerformance:
    match data:
        case {
            "database": str(database),
            "track_id": int(track_id),
            "path": str(path),
            "key": key,
            "grid": grid,
            "main_cue": main_cue,
            "hot_cues": hot_cues,
            "loops": loops,
            "info": info,
        }:
            return TrackPerformance(
                TrackRef(_uuid(database), track_id),
                path,
                Performance(
                    key=_key(key),
                    grid=tuple(_marker(m) for m in _items(grid)),
                    main_cue=None if main_cue is None else _seconds(main_cue),
                    hot_cues={_slot(s): _cue(c) for s, c in _slots(hot_cues)},
                    loops={_slot(s): _loop(lp) for s, lp in _slots(loops)},
                ),
                _info(info),
            )
        case _:
            raise SnapshotError(f"Malformed track: {data!r}")


_INFO_TEXT = frozenset(f.name for f in fields(TrackInfo) if f.type == "str")


def _info(data: Any) -> TrackInfo:
    values = cast(dict[str, Any], data) if isinstance(data, dict) else {}
    if set(values) != {f.name for f in fields(TrackInfo)}:
        raise SnapshotError(f"Malformed track info: {data!r}")
    for name, value in values.items():
        if name in _INFO_TEXT:
            valid = isinstance(value, str)
        elif name == "artwork":
            valid = value is None or isinstance(value, str)
        else:
            valid = value is None or (isinstance(value, int) and not isinstance(value, bool))
        if not valid:
            raise SnapshotError(f"Malformed track info field {name}: {value!r}")
    return TrackInfo(**values)


def _playlist(data: Any) -> PlaylistNode:
    match data:
        case {"name": str(name), "tracks": tracks, "children": children}:
            return PlaylistNode(
                name,
                tuple(_ref(ref) for ref in _items(tracks)),
                tuple(_playlist(child) for child in _items(children)),
            )
        case _:
            raise SnapshotError(f"Malformed playlist: {data!r}")


def _ref(data: Any) -> TrackRef:
    match data:
        case [str(database), int(track_id)] if not isinstance(track_id, bool):
            return TrackRef(_uuid(database), track_id)
        case _:
            raise SnapshotError(f"Malformed track reference: {data!r}")


def _key(data: Any) -> Key | None:
    match data:
        case None:
            return None
        case {"tonic": int(tonic), "minor": bool(minor)} if 0 <= tonic < 12:
            return Key(tonic, minor)
        case _:
            raise SnapshotError(f"Malformed key: {data!r}")


def _marker(data: Any) -> GridMarker:
    match data:
        case [position, int(beat)] if not isinstance(beat, bool):
            return GridMarker(_seconds(position), beat)
        case _:
            raise SnapshotError(f"Malformed grid marker: {data!r}")


def _cue(data: Any) -> Cue:
    match data:
        case {"position": position, "label": str(label), "color": color}:
            return Cue(_seconds(position), label, _parse_color(color))
        case _:
            raise SnapshotError(f"Malformed cue: {data!r}")


def _loop(data: Any) -> Loop:
    match data:
        case {"start": start, "end": end, "label": str(label), "color": color}:
            return Loop(_seconds(start), _seconds(end), label, _parse_color(color))
        case _:
            raise SnapshotError(f"Malformed loop: {data!r}")


def _parse_color(data: Any) -> Color:
    match data:
        case [int(red), int(green), int(blue)] if all(0 <= c <= 255 for c in (red, green, blue)):
            return Color(red, green, blue)
        case _:
            raise SnapshotError(f"Malformed color: {data!r}")


def _seconds(data: Any) -> float:
    if isinstance(data, bool) or not isinstance(data, int | float):
        raise SnapshotError(f"Malformed time: {data!r}")
    return float(data)


def _items(data: Any) -> list[Any]:
    if not isinstance(data, list):
        raise SnapshotError(f"Expected a list: {data!r}")
    return cast(list[Any], data)


def _slots(data: Any) -> list[tuple[str, Any]]:
    if not isinstance(data, dict):
        raise SnapshotError(f"Expected an object: {data!r}")
    return list(cast(dict[str, Any], data).items())


def _slot(text: str) -> int:
    if not text.isdecimal() or int(text) < 1:
        raise SnapshotError(f"Malformed slot: {text!r}")
    return int(text)


def _uuid(text: str) -> UUID:
    try:
        return UUID(text)
    except ValueError as exc:
        raise SnapshotError(f"Malformed UUID: {text!r}") from exc
