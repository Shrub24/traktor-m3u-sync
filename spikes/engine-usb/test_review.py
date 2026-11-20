"""Exercise Engine edit review using disposable SQLite libraries."""

import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from export import copy_assets
from review import apply, checksum, plan

SOURCE = "11111111-1111-4111-8111-111111111111"
DEVICE = "22222222-2222-4222-8222-222222222222"


def fixture(path, uuid, track_id):
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE Information(uuid, schemaVersionMajor,
                schemaVersionMinor, schemaVersionPatch);
            CREATE TABLE Track(id INTEGER PRIMARY KEY, originDatabaseUuid,
                originTrackId, title, bpmAnalyzed);
            CREATE TABLE PerformanceData(trackId INTEGER PRIMARY KEY REFERENCES Track, quickCues,
                loops, activeOnLoadLoops, beatData, overviewWaveFormData);
        """)
        db.execute("INSERT INTO Information VALUES (?, 3, 0, 2)", (uuid,))
        db.execute("INSERT INTO Track VALUES (?, ?, 1, ?, 120)", (track_id, SOURCE, "Song"))
        db.execute(
            "INSERT INTO PerformanceData VALUES (?, ?, ?, 0, ?, ?)",
            (track_id, b"cue", b"loop", b"grid", b"wave"),
        )


def execute(path, query):
    with sqlite3.connect(path) as db:
        return db.execute(query).fetchall()


def exercise(tmp):
    source, baseline, usb = (tmp / f"{name}.db" for name in ("source", "base", "usb"))
    fixture(source, SOURCE, 1)
    fixture(baseline, DEVICE, 21)
    fixture(usb, DEVICE, 31)
    execute(
        usb, "UPDATE PerformanceData SET quickCues = NULL, loops = x'99', activeOnLoadLoops = 1"
    )
    execute(usb, "UPDATE PerformanceData SET beatData = x'bb'")
    execute(usb, "UPDATE Track SET bpmAnalyzed = 125")
    execute(source, "UPDATE PerformanceData SET beatData = x'aa'")
    script = Path(__file__).with_name("review.py")
    command = [sys.executable, script, source, baseline, usb]
    review = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    token = review.split("approval token: ")[1].splitlines()[0]
    edits = plan(source, baseline, usb)
    assert [(row[0], row[2], row[3]) for row in edits] == [
        (1, "cues", "apply"),
        (1, "loops", "apply"),
        (1, "grid", "conflict"),
    ]
    execute(source, "UPDATE Track SET title = 'New title'")
    stale = subprocess.run([*command, "--approve", token], capture_output=True, text=True)
    assert stale.returncode != 0 and "Review changed" in stale.stderr
    old = source.read_bytes()
    backup = source.with_name(f"{source.name}.before-usb-{checksum(source)}.bak")
    fresh = subprocess.check_output(command, text=True)
    token = fresh.split("approval token: ")[1].splitlines()[0]
    subprocess.run([*command, "--approve", token], check=True, capture_output=True)
    assert backup.read_bytes() == old
    assert execute(source, "SELECT * FROM PerformanceData") == [
        (1, None, b"\x99", 1, b"\xaa", b"wave")
    ]
    assert execute(source, "SELECT title, bpmAnalyzed FROM Track") == [("New title", 120)]
    assert [row[3] for row in plan(source, baseline, usb)] == ["conflict"]
    apply(source, checksum(source), plan(source, baseline, usb, conflicts="usb"))
    assert execute(
        source, "SELECT beatData, bpmAnalyzed FROM PerformanceData JOIN Track ON id = trackId"
    ) == [(b"\xbb", 125)]
    assert not plan(source, baseline, usb)


def asset_paths(tmp):
    source = tmp / "Engine Library"
    overview = source / "Database2/OverviewData" / SOURCE
    overview.mkdir(parents=True)
    (overview / "1.rgb").write_bytes(b"overview")
    audio = tmp / "song.mp3"
    paths = []
    for index, payload in enumerate((b"old", b"old", b"new")):
        audio.write_bytes(payload)
        target = tmp / f"stage-{index}"
        with sqlite3.connect(":memory:") as db:
            db.executescript("""
                CREATE TABLE Track(id, path, filename, isAnalyzed, albumArtId);
                CREATE TABLE PerformanceData(trackId, beatData);
                CREATE TABLE AlbumArt(hash);
                INSERT INTO Track VALUES (1, '../song.mp3', 'song.mp3', 1, NULL);
                INSERT INTO PerformanceData VALUES (1, x'AB');
            """)
            copy_assets(db, source, target, SOURCE, DEVICE)
            (path,) = db.execute("SELECT path FROM Track").fetchone()
            assert (target / path).read_bytes() == payload
            paths.append(path)
    assert paths[0] == paths[1] != paths[2]


if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as directory:
        exercise(Path(directory))
        asset_paths(Path(directory))
    print("Engine USB edit review checks passed")
