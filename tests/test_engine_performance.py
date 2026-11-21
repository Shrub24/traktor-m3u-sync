"""Engine performance codec, model mapping, snapshot capture and snapshot JSON."""

from __future__ import annotations

import hashlib
import sqlite3
import struct
import zlib
from dataclasses import replace
from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET

import pytest
from engine_blobs import REAL_BEAT_DATA, REAL_LOOPS, REAL_QUICK_CUES
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
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
    PlaylistNode,
    Snapshot,
    SnapshotError,
    TrackInfo,
    TrackRef,
    dumps,
    loads,
    select,
)

LIBRARY = UUID("8ae3af13-4aae-44e6-91c2-8abc483ba2c9")
OTHER = UUID("11111111-2222-3333-4444-555555555555")
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
                originDatabaseUuid TEXT, originTrackId INTEGER, title TEXT, artist TEXT,
                album TEXT, genre TEXT, label TEXT, comment TEXT, year INTEGER,
                length INTEGER, bitrate INTEGER, fileBytes INTEGER, albumArtId INTEGER);
            CREATE TABLE AlbumArt (id INTEGER PRIMARY KEY, hash BLOB);
            CREATE TABLE PerformanceData (trackId INTEGER PRIMARY KEY, beatData BLOB,
                quickCues BLOB, loops BLOB);
            CREATE TABLE Playlist (id INTEGER PRIMARY KEY, title TEXT, parentListId INTEGER,
                nextListId INTEGER);
            CREATE TABLE PlaylistEntity (id INTEGER PRIMARY KEY, listId INTEGER,
                trackId INTEGER, databaseUuid TEXT, nextEntityId INTEGER);
            """
        )
        connection.execute("INSERT INTO Information VALUES (?, 3, 0, 2)", (str(LIBRARY),))
        connection.execute("INSERT INTO AlbumArt VALUES (3, ?)", (bytes(range(20)),))
        connection.execute(
            "INSERT INTO Track VALUES"
            " (5, '../library/a.mp3', 1, ?, 5, 'A', 'Artist', '', NULL, '', '', 2024,"
            " 300, 320, 1234, 3),"
            " (6, '../library/b.mp3', NULL, ?, 6, 'B', '', '', '', '', '', NULL,"
            " NULL, NULL, NULL, NULL)",
            (str(LIBRARY), str(LIBRARY)),
        )
        # Ids deliberately disagree with Engine's linked order.
        connection.execute(
            "INSERT INTO Playlist VALUES (10, 'Sync', 0, 0), (11, 'Other', 0, 10),"
            " (12, 'Second', 10, 0), (13, 'First', 10, 12)"
        )
        connection.execute(
            "INSERT INTO PlaylistEntity VALUES (20, 13, 5, ?, 0), (21, 13, 6, ?, 20),"
            " (22, 12, 7, ?, 0)",
            (str(LIBRARY), str(LIBRARY), str(OTHER)),
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
    assert analyzed.info == TrackInfo(
        "A",
        "Artist",
        year=2024,
        duration=300,
        bitrate=320,
        sample_rate=44100,
        file_size=1234,
        artwork="Artwork/AAECAwQFBgcICQoLDA0ODxAREhM.jpg",
    )
    assert unanalyzed.info == TrackInfo("B")


def test_capture_keeps_engine_playlist_order_and_selects_a_subtree(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    snapshot = capture(database)
    a, b = (TrackRef(LIBRARY, 5), TrackRef(LIBRARY, 6))
    assert snapshot.playlists == (
        PlaylistNode("Other"),
        PlaylistNode(
            "Sync",
            children=(
                PlaylistNode("First", (b, a)),
                PlaylistNode("Second", (TrackRef(OTHER, 7),)),
            ),
        ),
    )
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM PlaylistEntity WHERE id = 22")
    chosen = select(capture(database), "Sync")
    assert [node.name for node in chosen.playlists] == ["Sync"]
    assert {track.ref for track in chosen.tracks} == {a, b}
    with pytest.raises(SnapshotError, match="missing from the snapshot"):
        select(snapshot, "Sync")


def test_capture_rejects_a_broken_playlist_chain(tmp_path: Path) -> None:
    database = tmp_path / "m.db"
    _engine_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE PlaylistEntity SET nextEntityId = 21 WHERE id = 20")
    with pytest.raises(EnginePerformanceError, match="playlist order"):
        capture(database)


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
        '{"version": 1, "library": "x", "sha256": "", "tracks": []}',
        '{"version": 2, "library": "8ae3af13-4aae-44e6-91c2-8abc483ba2c9", "sha256": "",'
        ' "playlists": [], "tracks": [{"database": "8ae3af13-4aae-44e6-91c2-8abc483ba2c9",'
        ' "track_id": 1, "path": "a", "key": null, "grid": [], "main_cue": null,'
        ' "hot_cues": {"0": {"position": 1.0, "label": "", "color": [0, 0, 0]}}, "loops": {},'
        ' "info": {"title": "", "artist": "", "album": "", "genre": "", "label": "",'
        ' "comment": "", "year": null, "duration": null, "bitrate": null,'
        ' "sample_rate": null, "file_size": null, "artwork": null}}]}',
    ],
    ids=["unknown version", "slot zero"],
)
def test_snapshot_json_rejects_unknown_or_malformed_content(text: str) -> None:
    with pytest.raises(SnapshotError):
        loads(text)


def test_rekordbox_xml_exports_selected_engine_grid_cues_and_playlist(tmp_path: Path) -> None:
    library = tmp_path / "Engine Library"
    database = library / "Database2/m.db"
    database.parent.mkdir(parents=True)
    _engine_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM PlaylistEntity WHERE id = 22")
    with sqlite3.connect(database) as connection:
        (blob,) = connection.execute(
            "SELECT quickCues FROM PerformanceData WHERE trackId = 5"
        ).fetchone()
        cues = decode_quick_cues(blob)
        seeded = replace(cues, cues=(replace(cues.cues[0], sample=RATE), *cues.cues[1:]))
        connection.execute(
            "UPDATE PerformanceData SET quickCues = ? WHERE trackId = 5",
            (encode_quick_cues(seeded),),
        )
    config = tmp_path / "usb.toml"
    config.write_text(
        f'[usb]\nlibrary = "{library}"\noutput_dir = "{tmp_path / "out"}"\nplaylist_root = "Sync"\n'
    )
    output = tmp_path / "reference.xml"
    result = CliRunner().invoke(
        app,
        [
            "usb",
            "rekordbox-xml",
            "--config",
            str(config),
            "--output-file",
            str(output),
            "--location-base",
            "file://localhost/M:/Engine%20Library",
        ],
    )
    assert result.exit_code == 0, result.output
    xml = ET.parse(output)
    by_location = {track.attrib["Location"]: track for track in xml.findall("./COLLECTION/TRACK")}
    a = by_location["file://localhost/M:/library/a.mp3"]
    b = by_location["file://localhost/M:/library/b.mp3"]
    assert a.attrib["Tonality"] == "Am"
    (tempo,) = a.findall("TEMPO")
    assert float(tempo.attrib["Bpm"]) == pytest.approx(145, abs=0.02)
    assert float(tempo.attrib["Inizio"]) == pytest.approx(0.1062, abs=0.0001)
    assert tempo.attrib["Battito"] == "1"
    assert not b.findall("TEMPO") and "Tonality" not in b.attrib
    assert {
        (mark.attrib["Type"], mark.attrib["Num"], float(mark.attrib["Start"]))
        for mark in a.findall("POSITION_MARK")
    } == {("0", "-1", 1.0), ("0", "0", 1.0), ("0", "1", 2.0), ("4", "-1", 1.0)}
    (loop,) = a.findall("POSITION_MARK[@Type='4']")
    assert float(loop.attrib["End"]) == 2.0
    assert [track.attrib["Key"] for track in xml.findall("./PLAYLISTS/NODE/NODE/NODE/TRACK")] == [
        b.attrib["TrackID"],
        a.attrib["TrackID"],
    ]


SHARED_SNAPSHOT = Path(__file__).parent / "fixtures" / "snapshot.json"


def _shared_source(tmp_path: Path) -> Snapshot:
    database = tmp_path / "m.db"
    _engine_db(database)
    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM PlaylistEntity WHERE id = 22")
    return select(capture(database), "Sync")


def test_shared_snapshot_fixture_is_current(tmp_path: Path) -> None:
    """pioneer-usb's tests parse this file, so it must stay what capture produces."""
    shared = loads(SHARED_SNAPSHOT.read_text())
    assert shared == replace(_shared_source(tmp_path), sha256=shared.sha256)
