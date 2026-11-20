"""Engine performance codec, model mapping, snapshot capture and snapshot JSON."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import zlib
from dataclasses import replace
from pathlib import Path
from uuid import UUID

import pytest

from traktor_m3u_sync.formats.engine.performance import (
    EnginePerformanceError,
    capture,
    decode_beat_data,
    decode_loops,
    decode_quick_cues,
    encode_beat_data,
    encode_loops,
    encode_quick_cues,
    engine_key,
)
from traktor_m3u_sync.formats.engine.writer import EngineWriteError
from traktor_m3u_sync.model.performance import (
    Color,
    Cue,
    Key,
    Loop,
    SnapshotError,
    dumps,
    loads,
)

# Blobs written by Engine DJ 4 (home-forge media library).
REAL_BEAT_DATA = bytes.fromhex(
    "0000008a789c7378dad1c000048e991b6626006946060860924adcb93b6aed87037ffe43c0332688c4"
    "7793590f4436653a3e82f2d100b9fa1818008abf297e"
)
REAL_QUICK_CUES = bytes.fromhex(
    "00000081789c636000030e86fd1f181080761c871531c1aeca0d1f181daebe6002090000228212f0"
)
_EMPTY_LOOP = "00" + "000000000000f0bf" * 2 + "0000" + "00000000"
REAL_LOOPS = bytes.fromhex("0800000000000000" + _EMPTY_LOOP * 8)

LIBRARY = UUID("8ae3af13-4aae-44e6-91c2-8abc483ba2c9")
RATE = 44100.0


def test_real_engine_blobs_decode_and_reencode_byte_for_byte() -> None:
    beat = decode_beat_data(REAL_BEAT_DATA)
    assert beat.sample_rate == RATE and beat.grid_set
    assert [(m.beat, m.beats_to_next) for m in beat.adjusted_grid] == [(-4, 742), (738, 0)]
    assert beat.default_grid == beat.adjusted_grid
    assert beat.extra == bytes(9)
    cues = decode_quick_cues(REAL_QUICK_CUES)
    assert len(cues.cues) == 8 and all(cue.sample == -1 for cue in cues.cues)
    assert cues.main_cue_adjusted and cues.adjusted_main_cue != cues.default_main_cue
    loops = decode_loops(REAL_LOOPS)
    assert len(loops.loops) == 8 and not any(loop.start_set for loop in loops.loops)

    assert encode_beat_data(beat) == REAL_BEAT_DATA
    assert encode_quick_cues(cues) == REAL_QUICK_CUES
    assert encode_loops(loops) == REAL_LOOPS


@pytest.mark.parametrize(
    ("value", "key"),
    [
        (0, Key(0, False)),  # C
        (1, Key(9, True)),  # Am
        (9, Key(1, True)),  # D♭m
        (19, Key(0, True)),  # Cm
        (22, Key(5, False)),  # F
        (23, Key(2, True)),  # Dm
    ],
)
def test_engine_key_follows_libdjinterop_order(value: int, key: Key) -> None:
    assert engine_key(value) == key


def _quick_cues(*cues: tuple[str, float, tuple[int, int, int, int]], main: float) -> bytes:
    """Engine keeps the analysed main cue as the default; only the adjusted one is in use."""
    body = struct.pack(">q", len(cues))
    for label, sample, argb in cues:
        body += bytes([len(label)]) + label.encode() + struct.pack(">d4B", sample, *argb)
    body += struct.pack(">dBd", main, 1, main + RATE)
    return struct.pack(">I", len(body)) + zlib.compress(body)


def _loops(*loops: tuple[str, float, float, bool, bool]) -> bytes:
    body = struct.pack("<q", len(loops))
    for label, start, end, start_set, end_set in loops:
        body += bytes([len(label)]) + label.encode()
        body += struct.pack("<dd2B4B", start, end, start_set, end_set, 255, 1, 2, 3)
    return body


_HOT_CUES = _quick_cues(
    ("", -1.0, (0, 0, 0, 0)),
    ("Drop", 2 * RATE, (255, 200, 30, 10)),
    main=RATE / 2,
)
_SAVED_LOOPS = _loops(
    ("Intro", RATE, 2 * RATE, True, True),
    ("", 3 * RATE, -1.0, True, False),
)


def _edited_beat_data() -> bytes:
    """The real grid with the default (analysed) grid moved, as after a manual grid edit."""
    beat = decode_beat_data(REAL_BEAT_DATA)
    moved = tuple(replace(marker, sample=marker.sample + RATE) for marker in beat.default_grid)
    return encode_beat_data(replace(beat, default_grid=moved))


def _engine_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE Information (uuid TEXT, schemaVersionMajor INTEGER,
                schemaVersionMinor INTEGER, schemaVersionPatch INTEGER);
            CREATE TABLE Track (id INTEGER PRIMARY KEY, path TEXT, key INTEGER,
                originDatabaseUuid TEXT, originTrackId INTEGER);
            CREATE TABLE PerformanceData (trackId INTEGER PRIMARY KEY, beatData BLOB,
                quickCues BLOB, loops BLOB);
            """
        )
        connection.execute("INSERT INTO Information VALUES (?, 3, 0, 2)", (str(LIBRARY),))
        connection.execute(
            "INSERT INTO Track VALUES (5, '../library/a.mp3', 1, ?, 5),"
            " (6, '../library/b.mp3', NULL, ?, 6)",
            (str(LIBRARY), str(LIBRARY)),
        )
        connection.execute(
            "INSERT INTO PerformanceData VALUES (5, ?, ?, ?), (6, NULL, NULL, NULL)",
            (_edited_beat_data(), _HOT_CUES, _SAVED_LOOPS),
        )


def test_capture_maps_analyzed_and_unanalyzed_tracks(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    snapshot = capture(database)
    assert snapshot.library == LIBRARY
    assert snapshot.sha256 == hashlib.sha256(database.read_bytes()).hexdigest()
    analyzed, unanalyzed = snapshot.tracks
    assert (analyzed.ref.database, analyzed.ref.track_id) == (LIBRARY, 5)
    performance = analyzed.performance
    assert performance.key == Key(9, True)
    adjusted = decode_beat_data(REAL_BEAT_DATA).adjusted_grid
    assert [(m.position, m.beat) for m in performance.grid] == [
        (m.sample / RATE, m.beat) for m in adjusted
    ]
    assert performance.main_cue == 0.5
    assert performance.hot_cues == {2: Cue(2.0, "Drop", Color(200, 30, 10))}
    assert performance.loops == {1: Loop(1.0, 2.0, "Intro", Color(1, 2, 3))}
    empty = unanalyzed.performance
    assert (empty.key, empty.grid, empty.hot_cues, empty.loops) == (None, (), {}, {})


def test_capture_rejects_partial_performance_data(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE PerformanceData SET loops = NULL WHERE trackId = 5")
    with pytest.raises(EnginePerformanceError, match="partial performance data"):
        capture(database)


def test_capture_rejects_a_database_in_use(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    (tmp_path / "m.db-wal").write_bytes(b"")
    with pytest.raises(EngineWriteError):
        capture(database)


def test_snapshot_json_round_trips(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    snapshot = capture(database)
    assert loads(dumps(snapshot)) == snapshot


@pytest.mark.parametrize(
    "text",
    [
        '{"version": 2, "library": "x", "sha256": "", "tracks": []}',
        '{"version": 1, "library": "8ae3af13-4aae-44e6-91c2-8abc483ba2c9", "sha256": "",'
        ' "tracks": [{"database": "8ae3af13-4aae-44e6-91c2-8abc483ba2c9", "track_id": 1,'
        ' "path": "a", "key": null, "grid": [], "main_cue": null,'
        ' "hot_cues": {"0": {"position": 1.0, "label": "", "color": [0, 0, 0]}}, "loops": {}}]}',
    ],
    ids=["unknown version", "slot zero"],
)
def test_snapshot_json_rejects_unknown_or_malformed_content(text: str) -> None:
    with pytest.raises(SnapshotError):
        loads(text)
