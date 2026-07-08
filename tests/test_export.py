from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.config import ConfigError, LibraryConfig, apply_export_overrides, load_config
from traktor_m3u_sync.export_service import run_export
from traktor_m3u_sync.m3u_writer import write_m3u8
from traktor_m3u_sync.nml_reader import load_collection
from traktor_m3u_sync.pathmap import PathTranslationError, translate_track_path
from traktor_m3u_sync.playlist_tree import (
    ExportTrack,
    PlaylistTrackSource,
    extract_playlist_nodes,
)

RUNNER = CliRunner()


def test_load_config_and_apply_export_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        """
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/tmp/collection.nml"
output_dir = "/tmp/playlists"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    overridden = apply_export_overrides(
        config,
        collection_path=Path("/override/collection.nml"),
        output_dir=Path("/override/playlists"),
    )

    assert config.library.traktor_root == PureWindowsPath("C:/Music")
    assert config.library.m3u_root == PurePosixPath("../music")
    assert overridden.export.collection_path == Path("/override/collection.nml")
    assert overridden.export.output_dir == Path("/override/playlists")


def test_extract_playlist_nodes_skips_smartlists(tmp_path: Path) -> None:
    collection = load_collection(_write_collection_fixture(tmp_path))

    playlists, warnings = extract_playlist_nodes(collection.nml)

    assert len(playlists) == 1
    assert playlists[0].folder_parts == ("House",)
    assert playlists[0].playlist_name == "My:Playlist"
    assert len(playlists[0].tracks) == 1
    assert warnings[0].code == "smartlist_skipped"
    assert warnings[0].playlist == "House/Auto List"


def test_translate_track_path_prefers_primarykey_and_supports_relative_root() -> None:
    track = PlaylistTrackSource(
        primarykey_path="C:/Music/House/track-one.mp3",
        location_dir=":/Wrong/:Folder/",
        location_file="wrong-track.mp3",
        location_volume="D:",
        title="Track One",
        artist="Artist One",
        duration_seconds=123,
    )

    translated = translate_track_path(
        track,
        library=_library_config(),
    )

    assert translated == "../music/House/track-one.mp3"


def test_translate_track_path_falls_back_to_location() -> None:
    track = PlaylistTrackSource(
        primarykey_path=None,
        location_dir=":/Music/:House/",
        location_file="track-two.mp3",
        location_volume="C:",
        title="Track Two",
        artist="Artist Two",
        duration_seconds=234,
    )

    translated = translate_track_path(
        track,
        library=_library_config(),
    )

    assert translated == "../music/House/track-two.mp3"


def test_run_export_writes_hierarchy_sanitizes_names_and_emits_warnings(tmp_path: Path) -> None:
    collection_path = _write_collection_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = run_export(load_config(config_path))

    exported_playlist = output_dir / "House" / "My_Playlist.m3u8"
    assert exported_playlist.exists()
    assert exported_playlist.read_text(encoding="utf-8") == "\n".join(
        [
            "#EXTM3U",
            "#EXTINF:123,Artist One - Track One",
            "../music/House/track-one.mp3",
            "",
        ]
    )
    assert result.summary.playlists_written == 1
    assert result.summary.tracks_exported == 1
    assert result.summary.warnings_emitted == 1
    assert result.warnings[0].code == "smartlist_skipped"


def test_export_cli_emits_structured_summary(tmp_path: Path) -> None:
    collection_path = _write_collection_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["export", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY playlists_written=1 tracks_exported=1 warnings_emitted=1" in result.stdout


# ── config error tests ──────────────────────────────────────────────────


def test_load_config_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "nonexistent.toml")


def test_load_config_raises_on_missing_library_table(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.toml"
    config_path.write_text(
        '[export]\ncollection_path = "/tmp/n"\noutput_dir = "/tmp/o"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Missing required \\[library\\] table"):
        load_config(config_path)


def test_load_config_raises_on_missing_required_field(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.toml"
    config_path.write_text(
        '[library]\nm3u_root = "../music"\n\n'
        '[export]\ncollection_path = "/tmp/n"\noutput_dir = "/tmp/o"\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Missing required string field 'traktor_root'"):
        load_config(config_path)


# ── path translation error tests ────────────────────────────────────────


def test_translate_track_path_raises_on_path_outside_root() -> None:
    track = PlaylistTrackSource(
        primarykey_path="D:/Other/track.mp3",
        location_dir=None,
        location_file=None,
        location_volume=None,
        title="Track",
        artist="Artist",
        duration_seconds=100,
    )

    with pytest.raises(PathTranslationError, match="outside configured"):
        translate_track_path(track, library=_library_config())


def test_translate_track_path_raises_when_neither_primarykey_nor_location() -> None:
    track = PlaylistTrackSource(
        primarykey_path=None,
        location_dir=None,
        location_file=None,
        location_volume=None,
        title="Track",
        artist="Artist",
        duration_seconds=100,
    )

    with pytest.raises(PathTranslationError, match="missing both"):
        translate_track_path(track, library=_library_config())


def test_translate_track_path_with_absolute_m3u_root() -> None:
    track = PlaylistTrackSource(
        primarykey_path="C:/Music/House/track-one.mp3",
        location_dir=None,
        location_file=None,
        location_volume=None,
        title="Track",
        artist="Artist",
        duration_seconds=100,
    )
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("/absolute/music"),
    )

    result = translate_track_path(track, library=library)

    assert result == "/absolute/music/House/track-one.mp3"


# ── m3u writer edge cases ───────────────────────────────────────────────


def test_write_m3u8_with_missing_duration(tmp_path: Path) -> None:
    output = tmp_path / "test.m3u8"
    tracks = [
        ExportTrack(
            path="../music/track.mp3",
            title="Track",
            artist="Artist",
            duration_seconds=None,
        )
    ]

    write_m3u8(output, tracks)

    assert "#EXTINF:-1,Artist - Track" in output.read_text(encoding="utf-8")


# ── CLI error handling ──────────────────────────────────────────────────


def test_export_cli_exits_nonzero_on_missing_config(tmp_path: Path) -> None:
    result = RUNNER.invoke(app, ["export", "--config", str(tmp_path / "nonexistent.toml")])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


# ── multi-playlist and sanitization ──────────────────────────────────────


def test_run_export_writes_multiple_playlists_in_nested_folders(tmp_path: Path) -> None:
    collection_path = _write_multi_playlist_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = run_export(load_config(config_path))

    assert result.summary.playlists_written == 2
    assert result.summary.tracks_exported == 2
    assert (output_dir / "House" / "Deep.m3u8").exists()
    assert (output_dir / "Techno" / "Rave.m3u8").exists()


def test_run_export_sanitizes_folder_names(tmp_path: Path) -> None:
    collection_path = _write_bad_folder_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = run_export(load_config(config_path))

    assert result.summary.playlists_written == 1
    assert (output_dir / "Bad_Folder" / "Mix.m3u8").exists()


def test_run_export_handles_empty_playlist(tmp_path: Path) -> None:
    collection_path = _write_empty_playlist_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = run_export(load_config(config_path))

    assert result.summary.playlists_written == 1
    assert result.summary.tracks_exported == 0
    assert (output_dir / "Empty.m3u8").read_text(encoding="utf-8").strip() == "#EXTM3U"


def test_run_export_warns_on_path_outside_root_and_continues(tmp_path: Path) -> None:
    collection_path = _write_outside_root_fixture(tmp_path)
    output_dir = tmp_path / "playlists"
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{output_dir}"
""".strip(),
        encoding="utf-8",
    )

    result = run_export(load_config(config_path))

    assert result.summary.playlists_written == 1
    assert result.summary.tracks_exported == 1
    path_warnings = [w for w in result.warnings if w.code == "path_translation_failed"]
    assert len(path_warnings) == 1


# ── helpers ─────────────────────────────────────────────────────────────


def _library_config() -> LibraryConfig:
    return LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )


def _write_collection_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="1">
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track-one.mp3"></LOCATION>
      <INFO PLAYTIME="123"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-one.mp3"></PRIMARYKEY>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="FOLDER" NAME="House">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="My:Playlist">
              <PLAYLIST ENTRIES="1" TYPE="LIST">
                <ENTRY TITLE="Track One" ARTIST="Artist One">
                  <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track-one.mp3"></LOCATION>
                  <INFO PLAYTIME="123"></INFO>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-one.mp3"></PRIMARYKEY>
                </ENTRY>
              </PLAYLIST>
            </NODE>
            <NODE TYPE="SMARTLIST" NAME="Auto List">
              <SMARTLIST UUID="smart-1"></SMARTLIST>
            </NODE>
          </SUBNODES>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    return collection_path


def _write_multi_playlist_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="2">
    <ENTRY TITLE="Track A" ARTIST="Artist A">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track-a.mp3"></LOCATION>
      <INFO PLAYTIME="100"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-a.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Track B" ARTIST="Artist B">
      <LOCATION VOLUME="C:" DIR=":/Music/:Techno/" FILE="track-b.mp3"></LOCATION>
      <INFO PLAYTIME="200"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/Techno/track-b.mp3"></PRIMARYKEY>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="FOLDER" NAME="House">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="Deep">
              <PLAYLIST ENTRIES="1" TYPE="LIST">
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-a.mp3"></PRIMARYKEY>
                </ENTRY>
              </PLAYLIST>
            </NODE>
          </SUBNODES>
        </NODE>
        <NODE TYPE="FOLDER" NAME="Techno">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="Rave">
              <PLAYLIST ENTRIES="1" TYPE="LIST">
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/Techno/track-b.mp3"></PRIMARYKEY>
                </ENTRY>
              </PLAYLIST>
            </NODE>
          </SUBNODES>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    return collection_path


def _write_bad_folder_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="1">
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track.mp3"></LOCATION>
      <INFO PLAYTIME="100"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track.mp3"></PRIMARYKEY>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="FOLDER" NAME="Bad?Folder">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="Mix">
              <PLAYLIST ENTRIES="1" TYPE="LIST">
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track.mp3"></PRIMARYKEY>
                </ENTRY>
              </PLAYLIST>
            </NODE>
          </SUBNODES>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    return collection_path


def _write_empty_playlist_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="0">
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="PLAYLIST" NAME="Empty">
          <PLAYLIST ENTRIES="0" TYPE="LIST">
          </PLAYLIST>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    return collection_path


def _write_outside_root_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="2">
    <ENTRY TITLE="Good Track" ARTIST="Artist">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="good.mp3"></LOCATION>
      <INFO PLAYTIME="100"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/good.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Bad Track" ARTIST="Artist">
      <LOCATION VOLUME="D:" DIR=":/Other/:Dir/" FILE="bad.mp3"></LOCATION>
      <INFO PLAYTIME="200"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="D:/Other/Dir/bad.mp3"></PRIMARYKEY>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="PLAYLIST" NAME="Mixed">
          <PLAYLIST ENTRIES="2" TYPE="LIST">
            <ENTRY>
              <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/good.mp3"></PRIMARYKEY>
            </ENTRY>
            <ENTRY>
              <PRIMARYKEY TYPE="TRACK" KEY="D:/Other/Dir/bad.mp3"></PRIMARYKEY>
            </ENTRY>
          </PLAYLIST>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    return collection_path
