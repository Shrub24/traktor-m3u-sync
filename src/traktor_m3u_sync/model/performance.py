"""Format-neutral DJ performance data and its versioned JSON form.

Times are seconds from the start of the audio. Cue and loop slots are numbered from 1.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

SNAPSHOT_VERSION = 1


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
class TrackPerformance:
    ref: TrackRef
    path: str
    performance: Performance


@dataclass(frozen=True)
class Snapshot:
    library: UUID
    sha256: str
    tracks: tuple[TrackPerformance, ...]


def dumps(snapshot: Snapshot) -> str:
    return json.dumps(
        {
            "version": SNAPSHOT_VERSION,
            "library": str(snapshot.library),
            "sha256": snapshot.sha256,
            "tracks": [
                _track_json(track) for track in sorted(snapshot.tracks, key=lambda t: t.ref)
            ],
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
        }:
            return Snapshot(_uuid(library), digest, tuple(_track(t) for t in _items(tracks)))
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
            )
        case _:
            raise SnapshotError(f"Malformed track: {data!r}")


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
