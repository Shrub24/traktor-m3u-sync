"""Tests for the NML import and M3U export legs (collection.nml -> store -> .m3u8)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from traktor_nml_utils import TraktorCollection
from traktor_nml_utils.models.collection import Entrytype, Locationtype
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.config import (
    AppConfig,
    ConfigError,
    M3uConfig,
    NmlConfig,
    StoreConfig,
    apply_export_overrides,
    apply_import_overrides,
    load_config,
)
from traktor_m3u_sync.formats.m3u.writer import M3uTrack, playlist_file_path, write_m3u8
from traktor_m3u_sync.formats.nml.reader import load_collection, read_playlists
from traktor_m3u_sync.paths.m3u import M3uPathMapping
from traktor_m3u_sync.paths.traktor import PathTranslationError, TraktorPathMapping
from traktor_m3u_sync.services import run_export, run_import
from traktor_m3u_sync.store import PlaylistStore, StoreError, StoreNotPopulatedError

RUNNER = CliRunner()


# ── config ──────────────────────────────────────────────────────────────


def test_load_config_and_apply_export_overrides(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    config = load_config(config_path)
    overridden = apply_export_overrides(
        config,
        format="m3u",
        store_path=tmp_path / "override.db",
        output_dir=tmp_path / "override-out",
    )

    assert config.nml.library_root == PureWindowsPath("C:/Music")
    assert config.m3u.library_root == PurePosixPath("../music")
    assert overridden.store.path == tmp_path / "override.db"
    assert overridden.m3u.output_dir == tmp_path / "override-out"


def test_apply_export_overrides_raises_without_output_dir(tmp_path: Path) -> None:
    config = _app_config(tmp_path, output_dir=None)

    with pytest.raises(ConfigError, match="output_dir is required"):
        apply_export_overrides(config, format="m3u")


# ── NML reader ──────────────────────────────────────────────────────────


def test_read_playlists_skips_smartlists(tmp_path: Path) -> None:
    collection = load_collection(_write_collection_fixture(tmp_path))
    mapping = TraktorPathMapping(_nml_root())

    extracted = read_playlists(collection.nml, mapping)

    assert len(extracted.playlists) == 1
    assert extracted.playlists[0].folder_path == ("House",)
    assert extracted.playlists[0].name == "My:Playlist"
    assert len(extracted.playlists[0].tracks) == 1
    assert extracted.warnings[0].code == "smartlist_skipped"
    assert extracted.warnings[0].playlist == "House/Auto List"


# ── traktor path mapping ────────────────────────────────────────────────


def test_entry_path_prefers_primarykey_and_round_trips_library_space(tmp_path: Path) -> None:
    collection = load_collection(_write_collection_fixture(tmp_path))
    mapping = TraktorPathMapping(_nml_root())
    entry = _first_playlist_entry(collection)

    raw_path = mapping.entry_path(entry)

    assert raw_path == "C:/Music/House/track-one.mp3"
    assert mapping.to_rel_path(raw_path) == "House/track-one.mp3"
    assert mapping.to_full_path("House/track-one.mp3") == "C:/Music/House/track-one.mp3"


def test_entry_path_falls_back_to_location() -> None:
    entry = Entrytype(
        title="Track Two",
        artist="Artist Two",
        location=Locationtype(volume="C:", dir=":/Music/:House/", file="track-two.mp3"),
    )
    mapping = TraktorPathMapping(_nml_root())

    raw_path = mapping.entry_path(entry)

    assert raw_path == "C:/Music/House/track-two.mp3"
    assert mapping.to_rel_path(raw_path) == "House/track-two.mp3"


def test_entry_path_raises_when_neither_primarykey_nor_location() -> None:
    entry = Entrytype(title="Track", artist="Artist")
    mapping = TraktorPathMapping(_nml_root())

    with pytest.raises(PathTranslationError, match="missing both"):
        mapping.entry_path(entry)


def test_to_rel_path_raises_on_path_outside_root() -> None:
    mapping = TraktorPathMapping(_nml_root())

    with pytest.raises(PathTranslationError, match="outside configured"):
        mapping.to_rel_path("D:/Other/track.mp3")


def test_m3u_to_full_path_renders_relative_and_absolute_roots() -> None:
    assert (
        M3uPathMapping(PurePosixPath("/absolute/music")).to_full_path("House/track-one.mp3")
        == "/absolute/music/House/track-one.mp3"
    )
    assert (
        M3uPathMapping(PurePosixPath("../music")).to_full_path("House/track-one.mp3")
        == "../music/House/track-one.mp3"
    )


# ── two-command flow ────────────────────────────────────────────────────


def test_import_then_export_writes_hierarchy_sanitizes_names_and_warns(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _write_collection_fixture(tmp_path))

    imported = RUNNER.invoke(app, ["import", "--format", "nml", "--config", str(config_path)])
    exported = RUNNER.invoke(
        app, ["export", "--format", "m3u", "--config", str(config_path)], catch_exceptions=False
    )

    assert imported.exit_code == 0
    assert 'WARNING code=smartlist_skipped playlist="House/Auto List"' in imported.stderr
    assert exported.exit_code == 0
    exported_playlist = tmp_path / "out" / "House" / "My_Playlist.m3u8"
    assert exported_playlist.exists()
    assert exported_playlist.read_text(encoding="utf-8") == "\n".join(
        [
            "#EXTM3U",
            "#EXTINF:123,Artist One - Track One",
            "../music/House/track-one.mp3",
            "",
        ]
    )
    assert "SUMMARY playlists_written=1 tracks_exported=1 warnings_emitted=0" in exported.stdout


def test_service_level_two_command_flow(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, _write_collection_fixture(tmp_path)))

    imported = run_import(config, "nml")
    exported = run_export(config, "m3u")

    assert imported.counts == {
        "playlists_imported": 1,
        "tracks_stored": 1,
        "tracks_skipped": 0,
        "warnings_emitted": 1,
    }
    assert exported.counts["playlists_written"] == 1
    assert exported.counts["tracks_exported"] == 1
    assert imported.warnings[0].code == "smartlist_skipped"
    assert exported.warnings == ()


def test_export_cli_emits_structured_summary(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _write_collection_fixture(tmp_path))

    RUNNER.invoke(app, ["import", "--format", "nml", "--config", str(config_path)])
    result = RUNNER.invoke(app, ["export", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY playlists_written=1 tracks_exported=1 warnings_emitted=0" in result.stdout


def test_export_cli_fails_fast_on_empty_store(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = RUNNER.invoke(app, ["export", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=export_failed" in result.stderr
    assert "run import first" in result.stderr


def test_export_fails_fast_before_touching_output_dir(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    with pytest.raises(StoreNotPopulatedError, match="run import first"):
        run_export(config, "m3u")

    assert list((tmp_path / "out").iterdir()) == []


def test_unknown_export_format_is_rejected(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    with pytest.raises(ValueError, match="Unsupported format 'flac' for export"):
        run_export(config, "flac")


def test_unknown_import_format_is_rejected(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    with pytest.raises(ValueError, match="Unsupported format 'flac' for import"):
        run_import(config, "flac")


# ── config error tests ──────────────────────────────────────────────────


def test_load_config_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="Config file not found"):
        load_config(tmp_path / "nonexistent.toml")


def test_load_config_rejects_empty_library_root(tmp_path: Path) -> None:
    config_path = tmp_path / "bad.toml"
    config_path.write_text(
        '[store]\npath = "/tmp/s.db"\n[nml]\n[m3u]\nlibrary_root = ""\n',
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="must be a non-empty string"):
        load_config(config_path)


def test_m3u_import_requires_library_root(tmp_path: Path) -> None:
    config = _app_config(tmp_path)
    config = replace(config, m3u=replace(config.m3u, library_root=None))

    with pytest.raises(ConfigError, match="library_root is required for M3U import"):
        apply_import_overrides(config, format="m3u")


def test_nml_export_requires_library_root(tmp_path: Path) -> None:
    config = _app_config(tmp_path)
    config = replace(config, nml=replace(config.nml, library_root=None))

    with pytest.raises(ConfigError, match="library_root is required for NML export"):
        apply_export_overrides(config, format="nml")


def test_import_cli_fails_when_library_root_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[nml]\ncollection_path = "{tmp_path / "collection.nml"}"\n\n'
        f'[m3u]\nimport_dir = "{tmp_path / "in"}"\n',
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr
    assert "library_root is required for M3U import" in result.stderr


def test_load_config_allows_omitting_unselected_format_tables(tmp_path: Path) -> None:
    config_path = tmp_path / "sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[m3u]\nlibrary_root = "{tmp_path / "music"}"\nimport_dir = "{tmp_path / "in"}"\n\n'
        "[itunes]\n"
        'location_base = "file://localhost/M:/Music"\n'
        f'output_file = "{tmp_path / "Library.xml"}"\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.nml == NmlConfig()
    assert apply_import_overrides(config, format="m3u").m3u.import_dir == tmp_path / "in"
    overridden = apply_export_overrides(config, format="itunes")
    assert overridden.itunes.location_base == "file://localhost/M:/Music"

    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[nml]\nlibrary_root = "C:/Music"\ncollection_path = "{tmp_path / "c.nml"}"\n',
        encoding="utf-8",
    )

    assert load_config(config_path).m3u == M3uConfig()


def test_nml_selection_without_nml_table_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[m3u]\nlibrary_root = "{tmp_path / "music"}"\n',
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["export", "--format", "nml", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr
    assert "collection_path is required for NML export" in result.stderr

    config = load_config(config_path)
    config = replace(config, nml=NmlConfig(collection_path=tmp_path / "c.nml"))
    with pytest.raises(ConfigError, match="library_root is required for NML export"):
        apply_export_overrides(config, format="nml")


# ── m3u writer edge cases ───────────────────────────────────────────────


def test_write_m3u8_with_missing_duration(tmp_path: Path) -> None:
    output = tmp_path / "test.m3u8"
    tracks = [
        M3uTrack(path="../music/track.mp3", title="Track", artist="Artist", duration_seconds=None)
    ]

    write_m3u8(output, tracks)

    assert "#EXTINF:-1,Artist - Track" in output.read_text(encoding="utf-8")


def test_playlist_file_path_omits_root_and_sanitizes(tmp_path: Path) -> None:
    result = playlist_file_path(tmp_path, ("House", "Deep?One"), "Mix:Two")

    assert result == tmp_path / "House" / "Deep_One" / "Mix_Two.m3u8"


# ── CLI error handling ──────────────────────────────────────────────────


def test_export_cli_exits_nonzero_on_missing_config(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app, ["export", "--format", "m3u", "--config", str(tmp_path / "nonexistent.toml")]
    )

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


def test_import_cli_exits_nonzero_on_unreadable_collection(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)
    config_path.write_text(
        _config_text(tmp_path).replace(str(tmp_path / "collection.nml"), str(tmp_path / "no.nml")),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "nml", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=import_failed" in result.stderr


# ── multi-playlist and sanitization ──────────────────────────────────────


def test_two_command_flow_writes_multiple_playlists_in_nested_folders(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_multi_playlist_fixture(tmp_path))

    run_import(load_config(config_path), "nml")
    result = run_export(load_config(config_path), "m3u")

    assert result.counts["playlists_written"] == 2
    assert result.counts["tracks_exported"] == 2
    assert (tmp_path / "out" / "House" / "Deep.m3u8").exists()
    assert (tmp_path / "out" / "Techno" / "Rave.m3u8").exists()


def test_two_command_flow_sanitizes_folder_names(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_bad_folder_fixture(tmp_path))

    run_import(load_config(config_path), "nml")
    result = run_export(load_config(config_path), "m3u")

    assert result.counts["playlists_written"] == 1
    assert (tmp_path / "out" / "Bad_Folder" / "Mix.m3u8").exists()


def test_two_command_flow_handles_empty_playlist(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_empty_playlist_fixture(tmp_path))

    run_import(load_config(config_path), "nml")
    result = run_export(load_config(config_path), "m3u")

    assert result.counts["playlists_written"] == 1
    assert result.counts["tracks_exported"] == 0
    assert (tmp_path / "out" / "Empty.m3u8").read_text(encoding="utf-8").strip() == "#EXTM3U"


def test_two_command_flow_warns_on_path_outside_root_and_continues(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_outside_root_fixture(tmp_path))

    imported = run_import(load_config(config_path), "nml")
    result = run_export(load_config(config_path), "m3u")

    path_warnings = [w for w in imported.warnings if w.code == "path_translation_failed"]
    assert len(path_warnings) == 1
    assert result.counts["playlists_written"] == 1
    assert result.counts["tracks_exported"] == 1


def test_two_command_flow_skips_unresolved_tracks_on_export(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_outside_root_fixture(tmp_path))

    run_import(load_config(config_path), "nml")
    result = run_export(load_config(config_path), "m3u")

    unresolved = [w for w in result.warnings if w.code == "track_unresolved"]
    assert len(unresolved) == 1
    assert unresolved[0].playlist == "Mixed"


def test_wholesale_rebuild_replaces_previous_store_content(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, collection=_write_multi_playlist_fixture(tmp_path))
    config = load_config(config_path)

    run_import(config, "nml")
    run_import(config, "nml")

    with PlaylistStore(config.store.path) as store:
        playlists = store.load_playlists()

    assert len(playlists) == 2


# ── atomic publication ───────────────────────────────────────────────────


def test_m3u_export_replaces_existing_target_without_temp_leftovers(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, _write_collection_fixture(tmp_path)))
    run_import(config, "nml")
    target = tmp_path / "out" / "House" / "My_Playlist.m3u8"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stale\n", encoding="utf-8")

    run_export(config, "m3u")

    assert target.read_text(encoding="utf-8").startswith("#EXTM3U")
    assert [p.name for p in target.parent.iterdir()] == ["My_Playlist.m3u8"]


def test_m3u_write_failure_leaves_existing_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = load_config(_write_config(tmp_path, _write_collection_fixture(tmp_path)))
    run_import(config, "nml")
    target = tmp_path / "out" / "House" / "My_Playlist.m3u8"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("stale\n", encoding="utf-8")

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr("os.replace", failing_replace)

    with pytest.raises(OSError, match="no space"):
        run_export(config, "m3u")

    assert target.read_text(encoding="utf-8") == "stale\n"
    assert [p.name for p in target.parent.iterdir()] == ["My_Playlist.m3u8"]


# ── export dry run ───────────────────────────────────────────────────────


def test_m3u_dry_run_matches_real_export_without_writing_target(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, _write_collection_fixture(tmp_path)))
    run_import(config, "nml")

    dry = run_export(config, "m3u", dry_run=True)

    assert list((tmp_path / "out").iterdir()) == []

    real = run_export(config, "m3u")
    assert dry.counts == real.counts
    assert dry.warnings == real.warnings


def test_export_cli_dry_run_preserves_summary_store_and_target(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _write_collection_fixture(tmp_path))
    RUNNER.invoke(app, ["import", "--format", "nml", "--config", str(config_path)])
    store_bytes = (tmp_path / "store.db").read_bytes()

    dry = RUNNER.invoke(
        app, ["export", "--format", "m3u", "--dry-run", "--config", str(config_path)]
    )

    assert dry.exit_code == 0
    assert (tmp_path / "store.db").read_bytes() == store_bytes
    assert list((tmp_path / "out").iterdir()) == []

    real = RUNNER.invoke(app, ["export", "--format", "m3u", "--config", str(config_path)])
    assert dry.stdout == real.stdout
    assert (tmp_path / "out" / "House" / "My_Playlist.m3u8").exists()


def test_export_dry_run_absent_store_creates_nothing(tmp_path: Path) -> None:
    config = AppConfig(
        store=StoreConfig(path=tmp_path / "nested" / "store.db"),
        nml=NmlConfig(
            library_root=PureWindowsPath("C:/Music"), collection_path=tmp_path / "collection.nml"
        ),
        m3u=M3uConfig(
            library_root=PurePosixPath("../music"),
            output_dir=tmp_path / "out",
            import_dir=tmp_path / "in",
        ),
    )

    with pytest.raises(StoreError, match="not found for read-only access"):
        run_export(config, "m3u", dry_run=True)

    assert not (tmp_path / "nested").exists()
    assert not (tmp_path / "out").exists()


def test_export_dry_run_does_not_initialize_existing_empty_store(tmp_path: Path) -> None:
    config = _app_config(tmp_path, output_dir=tmp_path / "out")
    config.store.path.touch()

    with pytest.raises(StoreError, match="not an initialized store"):
        run_export(config, "m3u", dry_run=True)

    assert config.store.path.stat().st_size == 0


def test_export_cli_dry_run_absent_store_fails_without_creating_it(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    result = RUNNER.invoke(
        app, ["export", "--format", "m3u", "--dry-run", "--config", str(config_path)]
    )

    assert result.exit_code == 1
    assert "ERROR code=export_failed" in result.stderr
    assert not (tmp_path / "store.db").exists()


# ── warning-sensitive exit status ────────────────────────────────────────


def test_import_cli_fail_on_warning_exits_2_after_warnings(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _write_collection_fixture(tmp_path))

    result = RUNNER.invoke(
        app, ["import", "--format", "nml", "--config", str(config_path), "--fail-on-warning"]
    )

    assert result.exit_code == 2
    assert 'WARNING code=smartlist_skipped playlist="House/Auto List"' in result.stderr
    assert "SUMMARY" in result.stdout


def test_export_cli_fail_on_warning_status_2_strict_and_0_by_default(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, _write_outside_root_fixture(tmp_path))
    RUNNER.invoke(app, ["import", "--format", "nml", "--config", str(config_path)])

    strict = RUNNER.invoke(
        app, ["export", "--format", "m3u", "--config", str(config_path), "--fail-on-warning"]
    )
    default = RUNNER.invoke(app, ["export", "--format", "m3u", "--config", str(config_path)])

    assert strict.exit_code == 2
    assert "WARNING code=track_unresolved" in strict.stderr
    assert "SUMMARY" in strict.stdout
    assert default.exit_code == 0


def test_cli_real_failure_stays_exit_1_even_with_fail_on_warning(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app,
        [
            "export",
            "--format",
            "m3u",
            "--config",
            str(tmp_path / "nonexistent.toml"),
            "--fail-on-warning",
        ],
    )

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


# ── helpers ─────────────────────────────────────────────────────────────


def _nml_root() -> PureWindowsPath:
    return PureWindowsPath("C:/Music")


def _app_config(tmp_path: Path, *, output_dir: Path | None = None) -> AppConfig:
    return AppConfig(
        store=StoreConfig(path=tmp_path / "store.db"),
        nml=NmlConfig(library_root=_nml_root(), collection_path=tmp_path / "collection.nml"),
        m3u=M3uConfig(
            library_root=PurePosixPath("../music"),
            output_dir=output_dir,
            import_dir=tmp_path / "in",
        ),
    )


def _config_text(tmp_path: Path, collection: Path | None = None) -> str:
    return (
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[nml]\nlibrary_root = "C:/Music"\n'
        f'collection_path = "{collection or tmp_path / "collection.nml"}"\n\n'
        f'[m3u]\nlibrary_root = "../music"\n'
        f'output_dir = "{tmp_path / "out"}"\nimport_dir = "{tmp_path / "in"}"\n'
    )


def _write_config(tmp_path: Path, collection: Path | None = None) -> Path:
    _make_dirs(tmp_path)
    path = tmp_path / "traktor-m3u-sync.toml"
    path.write_text(_config_text(tmp_path, collection), encoding="utf-8")
    return path


def _make_dirs(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "in").mkdir(exist_ok=True)


def _first_playlist_entry(collection: TraktorCollection) -> Entrytype:
    playlists = collection.nml.playlists
    assert playlists is not None and playlists.node is not None
    assert playlists.node.subnodes is not None
    house = playlists.node.subnodes.node[0]
    assert house.subnodes is not None
    playlist = house.subnodes.node[0]
    assert playlist.playlist is not None
    return playlist.playlist.entry[0]


def _write_collection_fixture(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="1">
    <ENTRY TITLE="Track One" ARTIST="Artist One">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/" FILE="track-one.mp3"></LOCATION>
      <INFO PLAYTIME="123000"></INFO>
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
                  <INFO PLAYTIME="123000"></INFO>
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
      <INFO PLAYTIME="100000"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-a.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Track B" ARTIST="Artist B">
      <LOCATION VOLUME="C:" DIR=":/Music/:Techno/" FILE="track-b.mp3"></LOCATION>
      <INFO PLAYTIME="200000"></INFO>
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
      <INFO PLAYTIME="100000"></INFO>
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
      <INFO PLAYTIME="100000"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/good.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Bad Track" ARTIST="Artist">
      <LOCATION VOLUME="D:" DIR=":/Other/:Dir/" FILE="bad.mp3"></LOCATION>
      <INFO PLAYTIME="200000"></INFO>
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
