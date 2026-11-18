"""Engine analysis check: which managed tracks have saved analysis."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.formats.engine.analysis import managed_analysis_saved
from traktor_m3u_sync.formats.engine.writer import EngineWriteError

RUNNER = CliRunner()

_SCHEMA = """
CREATE TABLE Information (uuid TEXT, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch);
CREATE TABLE Track (id INTEGER PRIMARY KEY, isAnalyzed BOOLEAN);
CREATE TABLE PerformanceData (trackId INTEGER PRIMARY KEY, beatData BLOB);
CREATE TABLE Playlist (id INTEGER PRIMARY KEY, title TEXT, parentListId INTEGER);
CREATE TABLE PlaylistEntity (listId INTEGER, trackId INTEGER, databaseUuid TEXT);
INSERT INTO Information VALUES ('local', 3, 0, 2);
INSERT INTO Playlist VALUES (1, 'Playlist Sync', 0), (2, 'Nested', 1), (3, 'Unmanaged', 0);
INSERT INTO Track VALUES (10, 0), (11, 1), (12, 1), (13, 0), (99, 0);
INSERT INTO PerformanceData VALUES (11, x'AB'), (12, NULL);
INSERT INTO PlaylistEntity VALUES
  (1, 10, 'local'), (2, 11, 'local'), (2, 12, 'local'), (2, 13, 'foreign'),
  (2, 14, 'local'), (3, 99, 'local');
"""


@pytest.fixture
def engine(tmp_path: Path) -> Path:
    path = tmp_path / "m.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_SCHEMA)
    return path


def test_reports_only_local_managed_tracks_and_requires_a_saved_grid(engine: Path) -> None:
    assert managed_analysis_saved(engine, "Playlist Sync") == {
        10: False,  # not analyzed
        11: True,
        12: False,  # flagged analyzed but no beat grid persisted
        14: False,  # entity whose Track row is missing
    }


def test_track_becomes_saved_when_analysis_and_grid_land(engine: Path) -> None:
    with sqlite3.connect(engine) as connection:
        connection.execute("UPDATE Track SET isAnalyzed = 1 WHERE id = 10")
        assert managed_analysis_saved(engine, "Playlist Sync")[10] is False
        connection.execute("INSERT INTO PerformanceData VALUES (10, x'CD')")
    assert managed_analysis_saved(engine, "Playlist Sync")[10] is True


@pytest.mark.parametrize("root", ["Missing", "Nested"])
def test_requires_exactly_one_top_level_managed_root(engine: Path, root: str) -> None:
    with pytest.raises(EngineWriteError, match="exactly one top-level playlist"):
        managed_analysis_saved(engine, root)


def test_rejects_unsupported_schema(engine: Path) -> None:
    with sqlite3.connect(engine) as connection:
        connection.execute("UPDATE Information SET schemaVersionMinor = 1")
    with pytest.raises(EngineWriteError, match="unsupported"):
        managed_analysis_saved(engine, "Playlist Sync")


def test_locked_database_raises_busy(engine: Path) -> None:
    writer = sqlite3.connect(engine, isolation_level=None)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        with pytest.raises(sqlite3.OperationalError) as caught:
            managed_analysis_saved(engine, "Playlist Sync", busy_timeout=0.01)
    finally:
        writer.close()
    assert caught.value.sqlite_errorcode == sqlite3.SQLITE_BUSY


def test_cli_prints_json_from_flags_without_engine_section(engine: Path, tmp_path: Path) -> None:
    config = tmp_path / "store-only.toml"
    config.write_text(f'[store]\npath = "{tmp_path / "store.db"}"\n')
    result = RUNNER.invoke(
        app,
        [
            "engine-analysis",
            "--config",
            str(config),
            "--engine-database",
            str(engine),
            "--engine-managed-root",
            "Playlist Sync",
        ],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"10": False, "11": True, "12": False, "14": False}


def test_cli_exits_75_when_database_is_locked(engine: Path, tmp_path: Path) -> None:
    config = tmp_path / "engine.toml"
    config.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n'
        f'[engine]\ndatabase_path = "{engine}"\nmanaged_root = "Playlist Sync"\n'
    )
    writer = sqlite3.connect(engine, isolation_level=None)
    try:
        writer.execute("BEGIN EXCLUSIVE")
        result = RUNNER.invoke(app, ["engine-analysis", "--config", str(config)])
    finally:
        writer.close()
    assert result.exit_code == 75
    assert "code=engine_busy" in result.stderr


def test_cli_reports_other_failures_as_errors(engine: Path, tmp_path: Path) -> None:
    config = tmp_path / "store-only.toml"
    config.write_text(f'[store]\npath = "{tmp_path / "store.db"}"\n')
    result = RUNNER.invoke(
        app,
        [
            "engine-analysis",
            "--config",
            str(config),
            "--engine-database",
            str(engine),
            "--engine-managed-root",
            "Missing",
        ],
    )
    assert result.exit_code == 1
    assert "code=engine_analysis_failed" in result.stderr
