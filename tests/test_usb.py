"""Engine USB build and SFTP delivery against the real Engine 3.0.2 schema and OpenSSH."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import uuid
from collections.abc import Iterator
from contextlib import closing, nullcontext
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from engine_blobs import REAL_BEAT_DATA, REAL_LOOPS, REAL_QUICK_CUES
from paramiko import Channel, SFTPClient
from typer.testing import CliRunner, Result

from traktor_m3u_sync import cli
from traktor_m3u_sync.formats.engine import usb
from traktor_m3u_sync.formats.engine.performance import (
    QuickCue,
    decode_beat_data,
    decode_quick_cues,
    encode_beat_data,
    encode_quick_cues,
)
from traktor_m3u_sync.formats.engine.usb import DATABASE, EngineUsbError
from traktor_m3u_sync.usb import generation
from traktor_m3u_sync.usb.generation import Entry, Generation
from traktor_m3u_sync.usb.pioneer import DATABASES
from traktor_m3u_sync.usb.sftp import MARKER, DeliveryError, StickState, enter_stick, pull, push

SCHEMA = (Path(__file__).parent / "fixtures" / "engine_3_0_2_schema.sql").read_text()
SOURCE = uuid.UUID("8ae3af13-4aae-44e6-91c2-8abc483ba2c9")
STICK = uuid.UUID("a895a763-930c-424a-96d7-c82333e69c9c")


class Library:
    """A closed Engine media library with real schema and triggers, and audio beside it."""

    def __init__(self, root: Path) -> None:
        self.path = root / "Engine Library"
        self.music = root / "library"
        self.database = self.path / "Database2" / "m.db"
        self.database.parent.mkdir(parents=True)
        (self.path / "Artwork").mkdir()
        self.music.mkdir()
        with self.connect() as db:
            db.executescript(SCHEMA)
            db.execute(
                "INSERT INTO Information (uuid, schemaVersionMajor, schemaVersionMinor,"
                " schemaVersionPatch) VALUES (?, 3, 0, 2)",
                (str(SOURCE),),
            )

    def connect(self) -> closing[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, isolation_level=None)
        connection.execute("PRAGMA recursive_triggers = ON")
        return closing(connection)

    def track(self, name: str, audio: bytes, *, analyzed: bool = True) -> int:
        (self.music / name).write_bytes(audio)
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO Track (path, filename, isAnalyzed) VALUES (?, ?, ?)",
                (f"../library/{name}", name, int(analyzed)),
            )
            track_id = int(cursor.lastrowid or 0)
            if analyzed:
                db.execute(
                    "UPDATE PerformanceData SET beatData = ?, quickCues = ?, loops = ?"
                    " WHERE trackId = ?",
                    (REAL_BEAT_DATA, REAL_QUICK_CUES, REAL_LOOPS, track_id),
                )
        overview = self.path / "Database2" / "OverviewData" / str(SOURCE) / f"{track_id}.rgb"
        overview.parent.mkdir(parents=True, exist_ok=True)
        overview.write_bytes(b"rgb" + audio)
        return track_id

    def playlist(self, title: str, parent: int = 0) -> int:
        with self.connect() as db:
            cursor = db.execute(
                "INSERT INTO Playlist (title, parentListId, isPersisted, nextListId,"
                " lastEditTime, isExplicitlyExported) VALUES (?, ?, 1, 0, '2026-01-01', 1)",
                (title, parent),
            )
            return int(cursor.lastrowid or 0)

    def add(self, playlist: int, *tracks: int) -> None:
        with self.connect() as db:
            for track in tracks:
                entity = db.execute(
                    "INSERT INTO PlaylistEntity (listId, trackId, databaseUuid, nextEntityId,"
                    " membershipReference) VALUES (?, ?, ?, 0, 0)",
                    (playlist, track, str(SOURCE)),
                ).lastrowid
                db.execute(
                    "UPDATE PlaylistEntity SET nextEntityId = ?"
                    " WHERE listId = ? AND nextEntityId = 0 AND id <> ?",
                    (entity, playlist, entity),
                )


def _rows(database: Path, sql: str) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as db:
        return db.execute(sql).fetchall()


def _build(library: Library, output: Path, root: str | None = "Sync") -> Generation:
    return usb.build(library.path, output, root).generation


def test_build_exports_the_selected_tree_with_stable_device_and_media_paths(
    tmp_path: Path,
) -> None:
    library = Library(tmp_path)
    one = library.track("one.mp3", b"one")
    two = library.track("two.mp3", b"two")
    other = library.track("other.mp3", b"other")
    root = library.playlist("Sync")
    library.add(library.playlist("Set", root), two, one)
    library.add(library.playlist("Elsewhere"), other)
    before = library.database.read_bytes()

    first = _build(library, tmp_path / "out")
    staged = first.tree / DATABASE
    assert [row[0] for row in _rows(staged, "SELECT title FROM Playlist ORDER BY id")] == [
        "Sync",
        "Set",
    ]
    tracks = {int(str(i)): str(path) for i, path in _rows(staged, "SELECT id, path FROM Track")}
    assert set(tracks) == {one, two}
    (device,) = _rows(staged, "SELECT uuid FROM Information")
    assert uuid.UUID(str(device[0])) != SOURCE
    assert _rows(staged, "SELECT DISTINCT originDatabaseUuid FROM Track") == [(str(SOURCE),)]
    for track_id, path in tracks.items():
        entry = first.files[f"Engine Library/{path}"]
        assert entry.source == (library.music / ("one.mp3" if track_id == one else "two.mp3"))
        assert not (first.tree / "Engine Library" / str(path)).exists()
    assert library.database.read_bytes() == before

    second = _build(library, tmp_path / "out")
    assert generation.current(tmp_path / "out").path == second.path
    assert _rows(second.tree / DATABASE, "SELECT uuid FROM Information") == [device]
    assert {k: v.sha256 for k, v in second.files.items() if k != DATABASE} == {
        k: v.sha256 for k, v in first.files.items() if k != DATABASE
    }


def test_failed_build_keeps_the_previous_generation(tmp_path: Path) -> None:
    library = Library(tmp_path)
    root = library.playlist("Sync")
    library.add(root, library.track("one.mp3", b"one"))
    published = _build(library, tmp_path / "out")
    library.add(root, library.track("new.mp3", b"new", analyzed=False))
    with pytest.raises(EngineUsbError, match="no saved beat grid"):
        _build(library, tmp_path / "out")
    assert generation.current(tmp_path / "out").path == published.path
    assert [p.name for p in (tmp_path / "out" / "generations").iterdir()] == [published.path.name]


class _Stick(SFTPClient):
    """OpenSSH sftp-server on a socket pair, recording publications and failing on demand."""

    fail_on: str | None = None
    published: list[str]

    def posix_rename(self, oldpath: str | bytes, newpath: str | bytes) -> None:
        if newpath == self.fail_on:
            raise OSError("connection lost")
        super().posix_rename(oldpath, newpath)
        self.published.append(str(newpath))


class _Socket(socket.socket):
    def get_name(self) -> str:
        return "sftp test"


@pytest.fixture
def stick(tmp_path: Path) -> Iterator[tuple[_Stick, Path]]:
    server_binary = os.environ.get("SFTP_SERVER")
    assert server_binary, "SFTP_SERVER must name OpenSSH's sftp-server (set by the dev shell)"
    root = tmp_path / "stick"
    root.mkdir()
    peer, server = socket.socketpair()
    with (
        _Socket(fileno=peer.detach()) as client,
        server,
        subprocess.Popen(
            [server_binary, "-d", str(root)], stdin=server.fileno(), stdout=server.fileno()
        ) as proc,
    ):
        server.close()
        # paramiko only needs send/recv/close from its transport, which a socket provides.
        with _Stick(cast(Channel, client)) as sftp:
            sftp.published = []
            yield sftp, root
        client.close()
        assert proc.wait(timeout=5) == 0


def _state(sftp: SFTPClient, root: Path, tmp_path: Path) -> StickState:
    root.mkdir(exist_ok=True)
    return StickState(tmp_path / "state", enter_stick(sftp, str(root), mark=True))


def _media(published: list[str]) -> list[str]:
    return [name for name in published if name.startswith("Engine Library/Music/")]


def test_push_is_incremental_resumable_and_database_last(
    tmp_path: Path, stick: tuple[_Stick, Path]
) -> None:
    sftp, root = stick
    library = Library(tmp_path)
    playlist = library.playlist("Sync")
    library.add(playlist, library.track("one.mp3", b"one"))
    state = _state(sftp, root, tmp_path)

    built = _build(library, tmp_path / "out")
    preview = push(sftp, built, state, apply=False)
    assert DATABASE in preview.files and not (root / DATABASE).exists()
    push(sftp, built, state, apply=True)
    installed = (root / DATABASE).read_bytes()
    assert installed == (built.tree / DATABASE).read_bytes()
    sftp.published.clear()
    assert push(sftp, built, state, apply=True).files == ()
    assert sftp.published == []

    library.add(playlist, library.track("new.mp3", b"new"))
    updated = _build(library, tmp_path / "out")
    sftp.fail_on = DATABASE
    with pytest.raises(OSError, match="connection lost"):
        push(sftp, updated, state, apply=True)
    assert (root / DATABASE).read_bytes() == installed
    (media,) = _media(sftp.published)
    assert (root / media).read_bytes() == b"new"

    sftp.fail_on = None
    sftp.published.clear()
    push(sftp, updated, state, apply=True)
    assert _media(sftp.published) == []
    assert sftp.published[-1] == DATABASE
    assert (root / DATABASE).read_bytes() == (updated.tree / DATABASE).read_bytes()


def test_pioneer_refresh_preserves_edits_and_resumes_a_partial_database_switch(
    tmp_path: Path, stick: tuple[_Stick, Path]
) -> None:
    sftp, root = stick
    stick_id = enter_stick(sftp, str(root), mark=True)
    state = StickState(tmp_path / "state", stick_id, "pioneer")
    analysis = "PIONEER/USBANLZ/P001/track/ANLZ0000.DAT"
    audio = "Contents/audio.mp3"

    def build(version: bytes) -> Generation:
        path = generation.start(tmp_path / "pioneer")
        files: dict[str, Entry] = {}
        for name in (audio, analysis, *DATABASES):
            data = b"audio" if name == audio else version + name.encode()
            target = path / generation.TREE / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            files[name] = Entry(hashlib.sha256(data).hexdigest(), len(data))
        return generation.publish(path, files, DATABASES)

    initial = build(b"old")
    push(sftp, initial, state, apply=True)
    assert sftp.published[-3:] == list(DATABASES)
    updated = build(b"new")
    (root / analysis).write_bytes(b"player edit")
    with pytest.raises(DeliveryError, match="Pioneer analysis has changed"):
        push(sftp, updated, state, apply=True)
    assert (root / analysis).read_bytes() == b"player edit"
    (root / analysis).write_bytes(initial.local(analysis).read_bytes())

    sftp.published.clear()
    sftp.fail_on = DATABASES[1]
    with pytest.raises(OSError, match="connection lost"):
        push(sftp, updated, state, apply=True)
    assert sftp.published[-2:] == [analysis, DATABASES[0]]
    assert (root / DATABASES[0]).read_bytes() == updated.local(DATABASES[0]).read_bytes()
    assert (root / DATABASES[1]).read_bytes() == initial.local(DATABASES[1]).read_bytes()

    sftp.fail_on = None
    push(sftp, updated, state, apply=True)
    assert all((root / name).read_bytes() == updated.local(name).read_bytes() for name in DATABASES)
    assert push(sftp, updated, state, apply=True).files == ()


def test_each_stick_gets_its_own_identity_and_delivery(
    tmp_path: Path, stick: tuple[_Stick, Path]
) -> None:
    sftp, root = stick
    library = Library(tmp_path)
    library.add(library.playlist("Sync"), library.track("one.mp3", b"one"))
    built = _build(library, tmp_path / "out")
    first = _state(sftp, root / "a", tmp_path)
    push(sftp, built, first, apply=True)
    (root / "b").mkdir()
    assert enter_stick(sftp, str(root / "b"), mark=False) is None
    assert not (root / "b" / MARKER).exists()

    second = _state(sftp, root / "b", tmp_path)
    assert second.path != first.path
    sftp.published.clear()
    push(sftp, built, second, apply=True)
    assert len(_media(sftp.published)) == 1
    assert enter_stick(sftp, str(root / "a"), mark=False) == uuid.UUID(first.path.name)


def test_edited_stick_database_is_kept_until_reviewed(
    tmp_path: Path, stick: tuple[_Stick, Path]
) -> None:
    sftp, root = stick
    library = Library(tmp_path)
    library.add(library.playlist("Sync"), library.track("one.mp3", b"one"))
    state = _state(sftp, root, tmp_path)
    push(sftp, _build(library, tmp_path / "out"), state, apply=True)
    assert pull(sftp, state, DATABASE).changed is False

    with closing(sqlite3.connect(root / DATABASE)) as db, db:
        db.execute("UPDATE PerformanceData SET quickCues = NULL")
    edited = (root / DATABASE).read_bytes()
    pulled = pull(sftp, state, DATABASE)
    assert pulled.changed and pulled.snapshot.read_bytes() == edited

    rebuilt = _build(library, tmp_path / "out")
    with pytest.raises(DeliveryError, match="not the one last installed"):
        push(sftp, rebuilt, state, apply=True)
    assert (root / DATABASE).read_bytes() == edited

    push(sftp, rebuilt, state, apply=True, reviewed=hashlib.sha256(edited).hexdigest())
    assert (root / DATABASE).read_bytes() == (rebuilt.tree / DATABASE).read_bytes()


@pytest.mark.parametrize(
    ("suffix", "content", "allowed"),
    [
        ("-journal", b"", True),
        ("-journal", b"pending", False),
        ("-wal", b"", False),
        ("-shm", b"", False),
    ],
)
def test_pull_checks_sqlite_sidecars(
    tmp_path: Path, stick: tuple[_Stick, Path], suffix: str, content: bytes, allowed: bool
) -> None:
    sftp, root = stick
    state = _state(sftp, root, tmp_path)
    database = root / DATABASE
    database.parent.mkdir(parents=True)
    database.write_bytes(b"database")
    sidecar = database.with_name(database.name + suffix)
    sidecar.write_bytes(content)

    if allowed:
        assert pull(sftp, state, DATABASE).snapshot.read_bytes() == b"database"
    else:
        with pytest.raises(DeliveryError, match="library was not closed cleanly"):
            pull(sftp, state, DATABASE)
    assert sidecar.read_bytes() == content


def _grids(database: Path) -> dict[int, bytes]:
    rows = _rows(database, "SELECT trackId, beatData FROM PerformanceData")
    return {cast(int, track): cast(bytes, blob) for track, blob in rows}


def _edit_on_player(database: Path, track_id: int) -> None:
    """A hot cue in slot 2 and the grid moved one second. The default main cue also moves, as
    real Engine sticks show, though no reviewed field covers it."""
    with closing(sqlite3.connect(database)) as db, db:
        beat, cues = db.execute(
            "SELECT beatData, quickCues FROM PerformanceData WHERE trackId = ?", (track_id,)
        ).fetchone()
        grid = decode_beat_data(beat)
        moved = tuple(replace(m, sample=m.sample + grid.sample_rate) for m in grid.adjusted_grid)
        hot = decode_quick_cues(cues)
        slots = list(hot.cues)
        slots[1] = QuickCue("Drop", 2 * grid.sample_rate, (255, 200, 30, 10))
        db.execute(
            "UPDATE PerformanceData SET beatData = ?, quickCues = ? WHERE trackId = ?",
            (
                encode_beat_data(replace(grid, adjusted_grid=moved)),
                encode_quick_cues(replace(hot, cues=tuple(slots), default_main_cue=0.0)),
                track_id,
            ),
        )


def test_review_and_approve_an_unmarked_stick(
    tmp_path: Path, stick: tuple[_Stick, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    sftp, root = stick
    library = Library(tmp_path)
    edited = library.track("one.mp3", b"one")
    library.add(library.playlist("Sync"), edited)
    output = tmp_path / "out"
    built = _build(library, output / "engine")
    database = root / DATABASE
    database.parent.mkdir(parents=True)
    database.write_bytes(built.local(DATABASE).read_bytes())
    _edit_on_player(database, edited)
    with closing(sqlite3.connect(database)) as db, db:
        cues = decode_quick_cues(db.execute("SELECT quickCues FROM PerformanceData").fetchone()[0])
        db.execute(
            "UPDATE PerformanceData SET quickCues = ?",
            (encode_quick_cues(replace(cues, adjusted_main_cue=0.0, main_cue_adjusted=True)),),
        )
    original = database.read_bytes()
    before = library.database.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    config = tmp_path / "usb.toml"
    config.write_text(
        f'[usb]\nlibrary = "{library.path}"\noutput_dir = "{output}"\n'
        '[usb.device]\nhost = "unused"\nuser = "unused"\n'
        'key_file = "unused"\nknown_hosts = "unused"\n'
        f'state_dir = "{tmp_path / "state"}"\n'
    )

    def session(_: object) -> nullcontext[_Stick]:
        return nullcontext(sftp)

    monkeypatch.setattr(cli.sftp, "session", session)

    def run(command: str, *args: str) -> Result:
        return CliRunner().invoke(
            cli.app,
            [
                "usb",
                command,
                "--config",
                str(config),
                "--root",
                str(root),
                *args,
            ],
        )

    report = tmp_path / "review.json"
    result = run("review", "--diff", "--report", str(report))
    assert result.exit_code == 0, result.output
    assert "1 main cues ignored" in result.output
    assert "Main cue:" not in result.output
    changes = json.loads(report.read_text())["changes"]
    (main,) = [entry for entry in changes if entry["field"] == "main_cue"]
    assert main["device"] == 0.0 and main["selected"] is False
    assert library.database.read_bytes() == before
    code = usb.review(library.path, database).approval
    assert code in result.output
    result = run("review", "--approve", code)
    assert result.exit_code == 0, result.output
    assert digest in result.output
    after = usb.review(library.path, database)
    assert after.selected == ()
    assert [change.field for change in after.changes] == ["main_cue"]
    assert not (root / MARKER).exists()
    assert database.read_bytes() == original

    rebuilt = _build(library, output / "engine")
    assert run("push", "--format", "engine").exit_code != 0
    result = run("push", "--format", "engine", "--reviewed", digest)
    assert result.exit_code == 0, result.output
    assert not (root / MARKER).exists()
    assert database.read_bytes() == original
    result = run("push", "--format", "engine", "--reviewed", digest, "--apply")
    assert result.exit_code == 0, result.output
    assert (root / MARKER).is_file()
    assert database.read_bytes() == rebuilt.local(DATABASE).read_bytes()


def test_review_writes_player_edits_into_engine_and_releases_the_stick(
    tmp_path: Path, stick: tuple[_Stick, Path]
) -> None:
    sftp, root = stick
    library = Library(tmp_path)
    edited, untouched = library.track("one.mp3", b"one"), library.track("two.mp3", b"two")
    library.add(library.playlist("Sync"), edited, untouched)
    state = _state(sftp, root, tmp_path)
    push(sftp, _build(library, tmp_path / "out"), state, apply=True)
    _edit_on_player(root / DATABASE, edited)
    before = _grids(library.database)

    pulled = pull(sftp, state, DATABASE)
    pending = usb.review(library.path, pulled.snapshot)
    assert [(c.ref.track_id, c.field, c.slot) for c in pending.changes] == [
        (edited, "grid", None),
        (edited, "hot_cues", 2),
    ]
    with pytest.raises(EngineUsbError, match="changed since the review"):
        usb.apply_review(library.path, pulled.snapshot, "0" * 16)

    usb.apply_review(library.path, pulled.snapshot, pending.approval)
    state.accept(pulled.sha256)
    assert usb.review(library.path, pulled.snapshot).changes == ()
    after = _grids(library.database)
    assert after[untouched] == before[untouched]
    (cues,) = _rows(
        library.database, f"SELECT quickCues FROM PerformanceData WHERE trackId = {edited}"
    )
    assert decode_quick_cues(cast(bytes, cues[0])).default_main_cue == (
        decode_quick_cues(REAL_QUICK_CUES).default_main_cue
    )

    rebuilt = _build(library, tmp_path / "out")
    push(sftp, rebuilt, state, apply=True)
    assert (root / DATABASE).read_bytes() == (rebuilt.tree / DATABASE).read_bytes()
