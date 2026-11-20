"""Engine DJ performance data: lossless ``PerformanceData`` blob codec and model mapping.

Layouts follow libdjinterop's Engine v2/v3 blobs. ``beatData`` and ``quickCues`` are a
big-endian uncompressed length followed by zlib data; ``loops`` is uncompressed. Engine
compresses at zlib's default level, which Python's zlib reproduces byte for byte.
"""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import zlib
from collections.abc import Sequence
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import UUID

from ...model.performance import (
    Change,
    Color,
    Cue,
    GridMarker,
    Key,
    Loop,
    Performance,
    Snapshot,
    TrackPerformance,
    TrackRef,
)
from .writer import SCHEMA_VERSION, EngineWriteError, preflight_target

type Argb = tuple[int, int, int, int]


class EnginePerformanceError(ValueError):
    """Raised when an Engine performance blob does not match the known layout."""


@dataclass(frozen=True)
class BeatMarker:
    sample: float
    beat: int
    beats_to_next: int
    unknown: int


@dataclass(frozen=True)
class BeatData:
    sample_rate: float
    samples: float
    grid_set: bool
    default_grid: tuple[BeatMarker, ...]
    adjusted_grid: tuple[BeatMarker, ...]
    extra: bytes


@dataclass(frozen=True)
class QuickCue:
    label: str
    sample: float
    argb: Argb


@dataclass(frozen=True)
class QuickCues:
    cues: tuple[QuickCue, ...]
    adjusted_main_cue: float
    main_cue_adjusted: bool
    default_main_cue: float
    extra: bytes


@dataclass(frozen=True)
class EngineLoop:
    label: str
    start: float
    end: float
    start_set: bool
    end_set: bool
    argb: Argb


@dataclass(frozen=True)
class Loops:
    loops: tuple[EngineLoop, ...]
    extra: bytes


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def take(self, layout: str) -> tuple[int | float, ...]:
        try:
            values = struct.unpack_from(layout, self._data, self._offset)
        except struct.error as exc:
            raise EnginePerformanceError("Truncated Engine performance blob") from exc
        self._offset += struct.calcsize(layout)
        return values

    def flag(self) -> bool:
        (value,) = self.take("B")
        if value not in (0, 1):
            raise EnginePerformanceError(f"Unexpected Engine flag byte {value}")
        return value == 1

    def label(self) -> str:
        (length,) = self.take("B")
        end = self._offset + int(length)
        if end > len(self._data):
            raise EnginePerformanceError("Truncated Engine label")
        text = self._data[self._offset : end].decode()
        self._offset = end
        return text

    def argb(self) -> Argb:
        alpha, red, green, blue = (int(v) for v in self.take("4B"))
        return alpha, red, green, blue

    def rest(self) -> bytes:
        extra = self._data[self._offset :]
        self._offset = len(self._data)
        return extra


def _inflate(blob: bytes) -> bytes:
    (length,) = struct.unpack_from(">I", blob)
    data = zlib.decompress(blob[4:])
    if len(data) != length:
        raise EnginePerformanceError("Engine blob length prefix does not match its content")
    return data


def _deflate(data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + zlib.compress(data)


def _label(text: str) -> bytes:
    encoded = text.encode()
    return struct.pack("B", len(encoded)) + encoded


def _grid(reader: _Reader) -> tuple[BeatMarker, ...]:
    (count,) = reader.take(">q")
    return tuple(
        BeatMarker(float(sample), int(beat), int(beats), int(unknown))
        for sample, beat, beats, unknown in (reader.take("<dqii") for _ in range(int(count)))
    )


def _pack_grid(grid: tuple[BeatMarker, ...]) -> bytes:
    return struct.pack(">q", len(grid)) + b"".join(
        struct.pack("<dqii", m.sample, m.beat, m.beats_to_next, m.unknown) for m in grid
    )


def decode_beat_data(blob: bytes) -> BeatData:
    reader = _Reader(_inflate(blob))
    sample_rate, samples = reader.take(">dd")
    return BeatData(
        float(sample_rate),
        float(samples),
        reader.flag(),
        _grid(reader),
        _grid(reader),
        reader.rest(),
    )


def encode_beat_data(data: BeatData) -> bytes:
    return _deflate(
        struct.pack(">dd?", data.sample_rate, data.samples, data.grid_set)
        + _pack_grid(data.default_grid)
        + _pack_grid(data.adjusted_grid)
        + data.extra
    )


def decode_quick_cues(blob: bytes) -> QuickCues:
    reader = _Reader(_inflate(blob))
    (count,) = reader.take(">q")
    cues: list[QuickCue] = []
    for _ in range(int(count)):
        label = reader.label()
        (sample,) = reader.take(">d")
        cues.append(QuickCue(label, float(sample), reader.argb()))
    (adjusted,) = reader.take(">d")
    flag = reader.flag()
    (default,) = reader.take(">d")
    return QuickCues(tuple(cues), float(adjusted), flag, float(default), reader.rest())


def encode_quick_cues(data: QuickCues) -> bytes:
    return _deflate(
        struct.pack(">q", len(data.cues))
        + b"".join(
            _label(cue.label) + struct.pack(">d4B", cue.sample, *cue.argb) for cue in data.cues
        )
        + struct.pack(">d?d", data.adjusted_main_cue, data.main_cue_adjusted, data.default_main_cue)
        + data.extra
    )


def decode_loops(blob: bytes) -> Loops:
    reader = _Reader(blob)
    (count,) = reader.take("<q")
    loops: list[EngineLoop] = []
    for _ in range(int(count)):
        label = reader.label()
        start, end = reader.take("<dd")
        loops.append(
            EngineLoop(label, float(start), float(end), reader.flag(), reader.flag(), reader.argb())
        )
    return Loops(tuple(loops), reader.rest())


def encode_loops(data: Loops) -> bytes:
    return (
        struct.pack("<q", len(data.loops))
        + b"".join(
            _label(loop.label)
            + struct.pack("<dd??4B", loop.start, loop.end, loop.start_set, loop.end_set, *loop.argb)
            for loop in data.loops
        )
        + data.extra
    )


def engine_key(value: int) -> Key:
    """Engine's ``Track.key`` alternates major and relative minor around the circle of fifths."""
    if not 0 <= value < 24:
        raise EnginePerformanceError(f"Unknown Engine key {value}")
    step, minor = divmod(value, 2)
    return Key((7 * step + 9 * minor) % 12, minor == 1)


def performance(
    key: int | None, beat_data: BeatData, quick_cues: QuickCues, loops: Loops
) -> Performance:
    rate = beat_data.sample_rate
    if rate <= 0:
        raise EnginePerformanceError(f"Invalid Engine sample rate {rate}")

    def color(argb: Argb) -> Color:
        return Color(*argb[1:])

    return Performance(
        key=None if key is None else engine_key(key),
        grid=tuple(GridMarker(m.sample / rate, m.beat) for m in beat_data.adjusted_grid),
        main_cue=(
            quick_cues.adjusted_main_cue / rate if quick_cues.adjusted_main_cue >= 0 else None
        ),
        hot_cues={
            slot: Cue(cue.sample / rate, cue.label, color(cue.argb))
            for slot, cue in enumerate(quick_cues.cues, start=1)
            if cue.sample >= 0
        },
        loops={
            slot: Loop(loop.start / rate, loop.end / rate, loop.label, color(loop.argb))
            for slot, loop in enumerate(loops.loops, start=1)
            if loop.start_set and loop.end_set
        },
    )


_TRACKS = """
SELECT t.originDatabaseUuid, t.originTrackId, t.path, t.key,
       p.beatData, p.quickCues, p.loops
FROM Track t JOIN PerformanceData p ON p.trackId = t.id
ORDER BY t.id
"""


def capture(database_path: Path) -> Snapshot:
    """Snapshot the performance data of a closed Engine database without modifying it."""
    preflight_target(database_path)
    data = database_path.read_bytes()
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.deserialize(data)
        (row,) = connection.execute(
            "SELECT uuid, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch "
            "FROM Information"
        ).fetchall()
        library, *version = row
        if tuple(version) != SCHEMA_VERSION:
            raise EngineWriteError(f"Engine schema {tuple(version)!r} is unsupported")
        tracks = tuple(_track(*track) for track in connection.execute(_TRACKS))
    if len({track.ref for track in tracks}) != len(tracks):
        raise EnginePerformanceError("Engine database has duplicate track origins")
    return Snapshot(UUID(library), hashlib.sha256(data).hexdigest(), tracks)


def _track(
    database: str | None,
    track_id: int | None,
    path: str,
    key: int | None,
    beat_data: bytes | None,
    quick_cues: bytes | None,
    loops: bytes | None,
) -> TrackPerformance:
    if database is None or track_id is None:
        raise EnginePerformanceError(f"Engine track {path!r} has no origin")
    if beat_data is None and quick_cues is None and loops is None:
        result = Performance(key=None if key is None else engine_key(key))
    elif beat_data is not None and quick_cues is not None and loops is not None:
        result = performance(
            key, decode_beat_data(beat_data), decode_quick_cues(quick_cues), decode_loops(loops)
        )
    else:
        raise EnginePerformanceError(f"Engine track {path!r} has partial performance data")
    return TrackPerformance(TrackRef(UUID(database), track_id), path, result)


_PERFORMANCE = """
SELECT t.id, t.key, p.beatData, p.quickCues, p.loops
FROM Track t JOIN PerformanceData p ON p.trackId = t.id
WHERE t.originDatabaseUuid = ? AND t.originTrackId = ?
"""


def apply_device_edits(
    connection: sqlite3.Connection, device_database: Path, changes: Sequence[Change]
) -> None:
    """Write the device's value of each changed field into the library, natively.

    Only the changed fields are taken from the device; everything else in each blob,
    including fields the model ignores, keeps the library's bytes.
    """
    with closing(sqlite3.connect(device_database.as_uri() + "?mode=ro", uri=True)) as device:
        for ref in dict.fromkeys(change.ref for change in changes):
            fields = {(c.field, c.slot) for c in changes if c.ref == ref}
            origin = (str(ref.database), ref.track_id)
            track_id, key, beat, cues, loops = _native(connection, origin)
            _, device_key, device_beat, device_cues, device_loops = _native(device, origin)
            if ("key", None) in fields:
                key = device_key
            if ("grid", None) in fields:
                beat = replace(
                    beat, grid_set=device_beat.grid_set, adjusted_grid=device_beat.adjusted_grid
                )
            if ("main_cue", None) in fields:
                cues = replace(
                    cues,
                    adjusted_main_cue=device_cues.adjusted_main_cue,
                    main_cue_adjusted=device_cues.main_cue_adjusted,
                )
            hot = list(cues.cues)
            saved = list(loops.loops)
            for field, slot in fields:
                if field == "hot_cues" and slot is not None:
                    hot[slot - 1] = device_cues.cues[slot - 1]
                elif field == "loops" and slot is not None:
                    saved[slot - 1] = device_loops.loops[slot - 1]
            cues = replace(cues, cues=tuple(hot))
            loops = replace(loops, loops=tuple(saved))
            connection.execute("UPDATE Track SET key = ? WHERE id = ?", (key, track_id))
            connection.execute(
                "UPDATE PerformanceData SET beatData = ?, quickCues = ?, loops = ?"
                " WHERE trackId = ?",
                (encode_beat_data(beat), encode_quick_cues(cues), encode_loops(loops), track_id),
            )


def _native(
    connection: sqlite3.Connection, origin: tuple[str, int]
) -> tuple[int, int | None, BeatData, QuickCues, Loops]:
    row = connection.execute(_PERFORMANCE, origin).fetchone()
    if row is None or None in row[2:]:
        raise EnginePerformanceError(f"Track {origin} has no saved performance data")
    track_id, key, beat, cues, loops = row
    return track_id, key, decode_beat_data(beat), decode_quick_cues(cues), decode_loops(loops)
