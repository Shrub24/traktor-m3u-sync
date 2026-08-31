"""Tests for the M3U import and NML export legs (.m3u8 -> store -> collection.nml)."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from traktor_nml_utils import TraktorCollection
from traktor_nml_utils.models.collection import Nml, Nodetype
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
from traktor_m3u_sync.formats.m3u.parser import M3uReadError, read_import_tree, read_m3u8
from traktor_m3u_sync.formats.nml.exporter import SandboxWriteError
from traktor_m3u_sync.formats.nml.nodes import count_playlists, find_sandbox
from traktor_m3u_sync.formats.nml.reader import load_collection
from traktor_m3u_sync.model import Track
from traktor_m3u_sync.model.identity import identify
from traktor_m3u_sync.paths.m3u import M3uPathMapping, ReversePathTranslationError
from traktor_m3u_sync.paths.traktor import CollectionIndex, TraktorPathMapping
from traktor_m3u_sync.services import run_export, run_import
from traktor_m3u_sync.store import PlaylistStore

RUNNER = CliRunner()

SANDBOX = "Imported Playlists"


# ── M3U parser tests ────────────────────────────────────────────────────


def test_read_m3u8_parses_tracks_with_extinf(tmp_path: Path) -> None:
    m3u = tmp_path / "test.m3u8"
    m3u.write_text(
        "#EXTM3U\n"
        "#EXTINF:123,Artist One - Track One\n"
        "../music/House/track-one.mp3\n"
        "#EXTINF:-1,Unknown - Track Two\n"
        "../music/Techno/track-two.mp3\n",
        encoding="utf-8",
    )

    tracks = read_m3u8(m3u)

    assert len(tracks) == 2
    assert tracks[0].path == "../music/House/track-one.mp3"
    assert tracks[0].title == "Track One"
    assert tracks[0].artist == "Artist One"
    assert tracks[0].duration_seconds == 123
    assert tracks[1].path == "../music/Techno/track-two.mp3"
    assert tracks[1].title == "Track Two"
    assert tracks[1].artist == "Unknown"
    assert tracks[1].duration_seconds is None


def test_read_m3u8_handles_missing_extinf(tmp_path: Path) -> None:
    m3u = tmp_path / "bare.m3u8"
    m3u.write_text("#EXTM3U\n../music/track.mp3\n", encoding="utf-8")

    tracks = read_m3u8(m3u)

    assert len(tracks) == 1
    assert tracks[0].title == "Unknown Title"
    assert tracks[0].artist == "Unknown Artist"
    assert tracks[0].duration_seconds is None


def test_read_m3u8_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(M3uReadError, match="Cannot read"):
        read_m3u8(tmp_path / "nonexistent.m3u8")


def test_read_import_tree_discovers_nested_m3u8_files(tmp_path: Path) -> None:
    (tmp_path / "House").mkdir()
    (tmp_path / "House" / "Deep.m3u8").write_text(
        "#EXTM3U\n../music/track-a.mp3\n", encoding="utf-8"
    )
    (tmp_path / "Techno").mkdir()
    (tmp_path / "Techno" / "Rave.m3u8").write_text(
        "#EXTM3U\n../music/track-b.mp3\n", encoding="utf-8"
    )

    playlists = read_import_tree(tmp_path)

    assert len(playlists) == 2
    assert playlists[0].relative_dir == Path("House")
    assert playlists[0].name == "Deep"
    assert playlists[1].relative_dir == Path("Techno")
    assert playlists[1].name == "Rave"


def test_read_import_tree_handles_flat_directory(tmp_path: Path) -> None:
    (tmp_path / "MixA.m3u8").write_text("#EXTM3U\n../music/track.mp3\n", encoding="utf-8")
    (tmp_path / "MixB.m3u8").write_text("#EXTM3U\n../music/track2.mp3\n", encoding="utf-8")

    playlists = read_import_tree(tmp_path)

    assert len(playlists) == 2
    assert all(p.relative_dir == Path(".") for p in playlists)


def test_read_import_tree_discovers_plain_m3u_files(tmp_path: Path) -> None:
    (tmp_path / "Mix.m3u").write_text("#EXTM3U\n../music/track.mp3\n", encoding="utf-8")

    playlists = read_import_tree(tmp_path)

    assert len(playlists) == 1
    assert playlists[0].name == "Mix"


# ── M3U path mapping tests ──────────────────────────────────────────────


def test_to_rel_path_strips_relative_m3u_root() -> None:
    mapping = M3uPathMapping(_m3u_root())

    assert mapping.to_rel_path("../music/House/track.mp3") == "House/track.mp3"


def test_to_rel_path_strips_absolute_m3u_root() -> None:
    mapping = M3uPathMapping(PurePosixPath("/absolute/music"))

    assert mapping.to_rel_path("/absolute/music/House/track.mp3") == "House/track.mp3"


def test_to_rel_path_raises_on_path_outside_root() -> None:
    mapping = M3uPathMapping(_m3u_root())

    with pytest.raises(ReversePathTranslationError, match="does not fall beneath"):
        mapping.to_rel_path("../other/track.mp3")


def test_to_rel_path_raises_on_absolute_root_with_relative_path() -> None:
    with pytest.raises(ReversePathTranslationError, match="is relative"):
        M3uPathMapping(PurePosixPath("/absolute/music")).to_rel_path("music/track.mp3")


def test_to_full_path_renders_primarykey_format() -> None:
    result = TraktorPathMapping(_nml_root()).to_full_path("House/track.mp3")

    assert result == "C:/Music/House/track.mp3"


# ── collection index tests ──────────────────────────────────────────────


def test_collection_index_lookup_resolves_by_primarykey(tmp_path: Path) -> None:
    index = _collection_index(tmp_path)

    reference = index.lookup(identify(_track("House/track-a.mp3", "Track A", "Artist A")))

    assert reference is not None
    assert reference.entry.title == "Track A"
    assert reference.primarykey == "C:/Music/House/track-a.mp3"


def test_collection_index_falls_back_to_artist_title(tmp_path: Path) -> None:
    index = _collection_index(tmp_path)
    track = Track(title="Track A", artist="Artist   A", raw_path="unmapped", resolved=False)

    reference = index.lookup(identify(track))

    assert reference is not None
    assert reference.primarykey == "C:/Music/House/track-a.mp3"


def test_collection_index_returns_none_for_unmatched(tmp_path: Path) -> None:
    index = _collection_index(tmp_path)

    assert index.lookup(identify(_track("Nowhere/ghost.mp3", "Ghost", "Nobody"))) is None


# ── store-mediated two-command flow ─────────────────────────────────────


def test_import_flat_playlists_into_sandbox(tmp_path: Path) -> None:
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)

    imported = run_import(config, "m3u")
    result = run_export(config, "nml")

    assert imported.counts["playlists_imported"] == 2
    assert result.counts["playlists_written"] == 2
    assert result.counts["tracks_matched"] == 2
    assert result.counts["tracks_skipped"] == 0

    sandbox = _sandbox_node(_collection_path(config))
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert len(sandbox.subnodes.node) == 2
    assert {n.name for n in sandbox.subnodes.node} == {"MixOne", "MixTwo"}


def test_import_nested_playlists_preserves_hierarchy(tmp_path: Path) -> None:
    config = _write_and_load(tmp_path, _write_nested_m3u_fixture)

    run_import(config, "m3u")
    result = run_export(config, "nml")

    assert result.counts["playlists_written"] == 2
    assert result.counts["tracks_matched"] == 2

    sandbox = _sandbox_node(_collection_path(config))
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert [n.name for n in sandbox.subnodes.node] == ["House", "Techno"]

    house_folder = next(n for n in sandbox.subnodes.node if n.name == "House")
    assert house_folder.subnodes is not None
    assert len(house_folder.subnodes.node) == 1
    assert house_folder.subnodes.node[0].name == "Deep"
    assert house_folder.subnodes.node[0].playlist is not None
    assert len(house_folder.subnodes.node[0].playlist.entry) == 1


def test_export_skips_unmatched_tracks_with_warnings(tmp_path: Path) -> None:
    def write_m3u(import_dir: Path) -> None:
        (import_dir / "Mixed.m3u8").write_text(
            "#EXTM3U\n"
            "#EXTINF:100,Artist A - Track A\n"
            "../music/House/track-a.mp3\n"
            "#EXTINF:99,Ghost - Phantom\n"
            "../music/Nowhere/phantom.mp3\n",
            encoding="utf-8",
        )

    config = _write_and_load(tmp_path, write_m3u)

    run_import(config, "m3u")
    result = run_export(config, "nml")

    assert result.counts["playlists_written"] == 1
    assert result.counts["tracks_matched"] == 1
    assert result.counts["tracks_skipped"] == 1
    assert any(w.code == "track_unmatched" for w in result.warnings)


def test_export_creates_backup_before_write(tmp_path: Path) -> None:
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)

    run_import(config, "m3u")
    run_export(config, "nml")

    collection_path = _collection_path(config)
    assert len(list(collection_path.parent.glob("collection.backup.*.nml"))) == 1


def test_export_rebuild_sandbox_is_idempotent(tmp_path: Path) -> None:
    """Running the export leg twice should produce the same result."""
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)

    run_import(config, "m3u")
    first = run_export(config, "nml")
    second = run_export(config, "nml")

    assert first.counts == second.counts

    sandbox = _sandbox_node(_collection_path(config))
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert len(sandbox.subnodes.node) == 2


def test_export_preserves_existing_non_sandbox_playlists(tmp_path: Path) -> None:
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)

    run_import(config, "m3u")
    run_export(config, "nml")

    collection = load_collection(_collection_path(config))
    assert collection.nml.playlists is not None
    root = collection.nml.playlists.node
    assert root is not None and root.subnodes is not None

    non_sandbox = [n for n in root.subnodes.node if n.name != SANDBOX]
    assert len(non_sandbox) == 1
    assert non_sandbox[0].name == "Existing"


def test_round_trip_nml_to_m3u_to_nml(tmp_path: Path) -> None:
    """Import NML, export M3U, re-import the M3U, export into a second sandbox."""
    collection_path = _write_round_trip_collection(tmp_path)
    export_dir = tmp_path / "exported"
    export_dir.mkdir()
    config = _app_config(tmp_path, collection_path, output_dir=export_dir, import_dir=export_dir)

    run_import(config, "nml")
    run_export(config, "m3u")

    imported_back = run_import(config, "m3u")
    assert imported_back.counts["tracks_stored"] == 3
    assert imported_back.counts["tracks_skipped"] == 0

    result = run_export(config, "nml")
    assert result.counts["tracks_skipped"] == 0

    sandbox = _sandbox_node(collection_path)
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert [n.name for n in sandbox.subnodes.node] == ["Favs", "Techno Bangers"]

    favs_folder = next(n for n in sandbox.subnodes.node if n.name == "Favs")
    assert favs_folder.subnodes is not None
    assert len(favs_folder.subnodes.node) == 1
    assert favs_folder.subnodes.node[0].name == "Deep Cuts"

    deep_cuts = favs_folder.subnodes.node[0]
    assert deep_cuts.playlist is not None
    assert len(deep_cuts.playlist.entry) == 2

    keys = [str(entry.primarykey.key) for entry in deep_cuts.playlist.entry if entry.primarykey]
    assert keys == ["C:/Music/House/Deep/alpha.mp3", "C:/Music/House/Deep/beta.mp3"]


def test_sandbox_playlist_count_is_recursive(tmp_path: Path) -> None:
    config = _write_and_load(tmp_path, _write_nested_m3u_fixture)

    run_import(config, "m3u")
    result = run_export(config, "nml")

    sandbox = _sandbox_node(_collection_path(config))
    assert sandbox is not None and sandbox.subnodes is not None
    assert count_playlists(list(sandbox.subnodes.node)) == result.counts["playlists_written"] == 2


def test_export_nml_dry_run_exercises_sandbox_without_touching_collection(
    tmp_path: Path,
) -> None:
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)
    run_import(config, "m3u")
    collection_path = _collection_path(config)
    original = collection_path.read_bytes()

    dry = run_export(config, "nml", dry_run=True)

    assert dry.counts["playlists_written"] == 2
    assert dry.counts["tracks_matched"] == 2
    assert collection_path.read_bytes() == original
    assert list(collection_path.parent.glob("collection.backup.*.nml")) == []

    real = run_export(config, "nml")
    assert real.counts == dry.counts
    assert _sandbox_node(collection_path) is not None


# ── CLI tests ───────────────────────────────────────────────────────────


def test_import_cli_emits_structured_summary(tmp_path: Path) -> None:
    config_path = _write_config_file(tmp_path, _write_flat_m3u_fixture)

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY" in result.stdout
    assert "playlists_imported=2" in result.stdout
    assert "tracks_stored=2" in result.stdout
    assert "tracks_skipped=0" in result.stdout
    assert "warnings_emitted=0" in result.stdout


def test_import_cli_summary_reports_warning_count(tmp_path: Path) -> None:
    _write_flat_m3u_fixture(tmp_path)
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        "[nml]\n\n"
        f'[m3u]\nlibrary_root = "D:/elsewhere"\nimport_dir = "{tmp_path}"\n',
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 0
    match = re.search(r"warnings_emitted=(\d+)", result.stdout)
    assert match is not None
    emitted = int(match.group(1))
    assert emitted > 0
    assert emitted == result.stderr.count("WARNING code=path_translation_failed")


def test_export_cli_emits_sandbox_summary(tmp_path: Path) -> None:
    config_path = _write_config_file(tmp_path, _write_flat_m3u_fixture)

    RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])
    result = RUNNER.invoke(app, ["export", "--format", "nml", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY playlists_written=2 tracks_matched=2 tracks_skipped=0 warnings_emitted=0" in (
        result.stdout
    )


def test_export_cli_honours_sandbox_name_override(tmp_path: Path) -> None:
    config_path = _write_config_file(tmp_path, _write_flat_m3u_fixture)
    RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    result = RUNNER.invoke(
        app,
        [
            "export",
            "--format",
            "nml",
            "--config",
            str(config_path),
            "--sandbox-name",
            "Custom Box",
        ],
    )

    collection_path = tmp_path / "collection.nml"
    assert result.exit_code == 0
    assert _find_sandbox_node(load_collection(collection_path).nml, "Custom Box") is not None
    assert _find_sandbox_node(load_collection(collection_path).nml, SANDBOX) is None


def test_import_cli_exits_nonzero_on_missing_config(tmp_path: Path) -> None:
    result = RUNNER.invoke(
        app, ["import", "--format", "m3u", "--config", str(tmp_path / "nonexistent.toml")]
    )

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


def test_import_cli_exits_nonzero_on_missing_import_dir(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        (
            f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
            f'[nml]\nlibrary_root = "C:/Music"\n'
            f'collection_path = "{tmp_path / "collection.nml"}"\n\n'
            f'[m3u]\nlibrary_root = "../music"\noutput_dir = "{tmp_path / "out"}"\n'
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr
    assert "import_dir is required" in result.stderr


def test_import_cli_exits_nonzero_on_missing_import_directory(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        (
            f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
            f'[nml]\nlibrary_root = "C:/Music"\n'
            f'collection_path = "{tmp_path / "collection.nml"}"\n\n'
            f'[m3u]\nlibrary_root = "../music"\nimport_dir = "{tmp_path / "nowhere"}"\n'
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "ERROR code=import_failed" in result.stderr


# ── config tests ────────────────────────────────────────────────────────


def test_load_config_with_m3u_and_nml_sections(tmp_path: Path) -> None:
    config_path = _write_config_file(tmp_path, _write_flat_m3u_fixture)

    config = load_config(config_path)

    assert config.m3u.import_dir == tmp_path / "m3u"
    assert config.nml.sandbox_name == SANDBOX
    assert config.nml.collection_path == tmp_path / "collection.nml"
    assert config.store.path == tmp_path / "store.db"


def test_load_config_defaults_store_path(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        '[store]\n\n[nml]\ncollection_path = "/tmp/collection.nml"\n\n[m3u]\n',
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.store.path == Path("~/.local/state/traktor-m3u-sync/store.db").expanduser()


def test_load_config_defaults_sandbox_name(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        '[nml]\ncollection_path = "/tmp/collection.nml"\n\n'
        "[m3u]\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.nml.sandbox_name == SANDBOX
    assert config.m3u.import_dir is None


def test_load_config_allows_missing_nml_collection_path(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        "[store]\n\n[nml]\n\n[m3u]\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.nml.collection_path is None


def test_nml_commands_require_collection_path(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        "[store]\n\n[nml]\n\n[m3u]\n",
        encoding="utf-8",
    )

    config = load_config(config_path)

    with pytest.raises(ConfigError, match=r"collection_path is required for NML import"):
        apply_import_overrides(config, format="nml")
    with pytest.raises(ConfigError, match=r"collection_path is required for NML export"):
        apply_export_overrides(config, format="nml")


def test_m3u_import_works_without_nml_collection_path(tmp_path: Path) -> None:
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        "[nml]\n\n"
        f'[m3u]\nlibrary_root = "../music"\nimport_dir = "{import_dir}"\n',
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--format", "m3u", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY playlists_imported=2" in result.stdout


def test_apply_import_overrides(tmp_path: Path) -> None:
    config_path = _write_config_file(tmp_path, _write_flat_m3u_fixture)
    config = load_config(config_path)

    overridden = apply_import_overrides(
        config,
        format="m3u",
        store_path=tmp_path / "override.db",
        collection_path=tmp_path / "override.nml",
        import_dir=tmp_path / "override-m3u",
    )

    assert overridden.store.path == tmp_path / "override.db"
    assert overridden.nml.collection_path == tmp_path / "override.nml"
    assert overridden.m3u.import_dir == tmp_path / "override-m3u"


def test_apply_import_overrides_raises_without_import_dir(tmp_path: Path) -> None:
    config = AppConfig(
        store=StoreConfig(path=tmp_path / "store.db"),
        nml=NmlConfig(collection_path=tmp_path / "collection.nml"),
        m3u=M3uConfig(),
    )

    with pytest.raises(ConfigError, match="import_dir is required"):
        apply_import_overrides(config, format="m3u")


def test_apply_import_overrides_allows_nml_without_import_dir(tmp_path: Path) -> None:
    config = AppConfig(
        store=StoreConfig(path=tmp_path / "store.db"),
        nml=NmlConfig(
            library_root=PureWindowsPath("C:/Music"), collection_path=tmp_path / "collection.nml"
        ),
        m3u=M3uConfig(),
    )

    overridden = apply_import_overrides(config, format="nml")

    assert overridden.m3u.import_dir is None


# ── helpers ─────────────────────────────────────────────────────────────


# ── fix-pass regression tests ───────────────────────────────────────────


def test_to_rel_path_rejects_traversal_under_absolute_root() -> None:
    mapping = M3uPathMapping(PurePosixPath("/absolute/music"))

    with pytest.raises(ReversePathTranslationError, match="does not start with"):
        mapping.to_rel_path("/absolute/music/../outside/file.mp3")

    assert mapping.to_rel_path("/absolute/music/../music/House/track.mp3") == "House/track.mp3"


def test_import_keeps_pathless_unresolvable_entries_separate(tmp_path: Path) -> None:
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
        <NODE TYPE="PLAYLIST" NAME="Ghostly">
          <PLAYLIST ENTRIES="2" TYPE="LIST">
            <ENTRY TITLE="One"></ENTRY>
            <ENTRY TITLE="Two"></ENTRY>
          </PLAYLIST>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    config = _app_config(tmp_path, collection_path, import_dir=collection_path.parent)

    result = run_import(config, "nml")

    assert result.counts["tracks_stored"] == 2
    assert result.counts["tracks_skipped"] == 2
    with PlaylistStore(config.store.path) as store:
        tracks = store.load_playlists()[0].tracks
    assert [t.title for t in tracks] == ["One", "Two"]
    assert all(not t.resolved and t.identity is None for t in tracks)


def test_export_skips_ambiguous_fallback_matches(tmp_path: Path) -> None:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="2">
    <ENTRY TITLE="Dup" ARTIST="Same">
      <LOCATION VOLUME="C:" DIR=":/Music/:A/" FILE="dup.mp3"></LOCATION>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/A/dup.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Dup" ARTIST="Same">
      <LOCATION VOLUME="C:" DIR=":/Music/:B/" FILE="twin.mp3"></LOCATION>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="PLAYLIST" NAME="Mix">
          <PLAYLIST ENTRIES="1" TYPE="LIST">
            <ENTRY TITLE="Dup" ARTIST="Same"></ENTRY>
          </PLAYLIST>
        </NODE>
      </SUBNODES>
    </NODE>
  </PLAYLISTS>
</NML>
""",
        encoding="utf-8",
    )
    config = _app_config(tmp_path, collection_path, import_dir=collection_path.parent)

    run_import(config, "nml")
    result = run_export(config, "nml")

    assert result.counts["tracks_skipped"] == 1
    assert [w.code for w in result.warnings] == ["ambiguous_fallback_identity"]
    sandbox = _sandbox_node(collection_path)
    assert sandbox is not None and sandbox.subnodes is not None
    playlist = sandbox.subnodes.node[0]
    assert playlist.playlist is not None
    assert playlist.playlist.entry == []


def test_export_validation_failure_restores_backup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _write_and_load(tmp_path, _write_flat_m3u_fixture)
    run_import(config, "m3u")
    collection_path = _collection_path(config)
    original = collection_path.read_bytes()

    real_save = TraktorCollection.save

    def dropping_save(self: TraktorCollection) -> None:
        playlists = self.nml.playlists
        assert playlists is not None and playlists.node is not None
        sandbox = find_sandbox(playlists.node, SANDBOX)
        assert sandbox is not None and sandbox.subnodes is not None
        first = sandbox.subnodes.node[0].playlist
        assert first is not None
        first.entry.pop()
        real_save(self)

    monkeypatch.setattr(TraktorCollection, "save", dropping_save)

    with pytest.raises(SandboxWriteError, match="Post-save validation failed"):
        run_export(config, "nml")

    assert collection_path.read_bytes() == original


def _nml_root() -> PureWindowsPath:
    return PureWindowsPath("C:/Music")


def _m3u_root() -> PurePosixPath:
    return PurePosixPath("../music")


def _app_config(
    tmp_path: Path,
    collection_path: Path,
    *,
    output_dir: Path | None = None,
    import_dir: Path | None = None,
) -> AppConfig:
    return AppConfig(
        store=StoreConfig(path=tmp_path / "store.db"),
        nml=NmlConfig(library_root=_nml_root(), collection_path=collection_path),
        m3u=M3uConfig(
            library_root=_m3u_root(),
            output_dir=output_dir or tmp_path / "out",
            import_dir=import_dir or tmp_path / "m3u",
        ),
    )


def _config_text(tmp_path: Path, collection_path: Path) -> str:
    return (
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[nml]\nlibrary_root = "C:/Music"\ncollection_path = "{collection_path}"\n\n'
        f'[m3u]\nlibrary_root = "../music"\n'
        f'output_dir = "{tmp_path / "out"}"\nimport_dir = "{tmp_path / "m3u"}"\n'
    )


def _write_config_file(tmp_path: Path, write_m3u: Callable[[Path], None]) -> Path:
    collection_path = _write_importable_collection(tmp_path)
    _prepare_dirs(tmp_path)
    write_m3u(tmp_path / "m3u")
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(_config_text(tmp_path, collection_path), encoding="utf-8")
    return config_path


def _write_and_load(tmp_path: Path, write_m3u: Callable[[Path], None]) -> AppConfig:
    _write_config_file(tmp_path, write_m3u)
    return load_config(tmp_path / "traktor-m3u-sync.toml")


def _prepare_dirs(tmp_path: Path) -> None:
    (tmp_path / "out").mkdir(exist_ok=True)
    (tmp_path / "m3u").mkdir(exist_ok=True)


def _track(path: str, title: str, artist: str) -> Track:
    return Track(title=title, artist=artist, path=path, raw_path=path)


def _collection_index(tmp_path: Path) -> CollectionIndex:
    collection = load_collection(_write_importable_collection(tmp_path))
    return TraktorPathMapping(_nml_root()).index_collection(collection.nml)


def _collection_path(config: AppConfig) -> Path:
    path = config.nml.collection_path
    assert path is not None
    return path


def _sandbox_node(collection_path: Path) -> Nodetype | None:
    return _find_sandbox_node(load_collection(collection_path).nml, SANDBOX)


def _find_sandbox_node(nml: Nml, sandbox_name: str) -> Nodetype | None:
    if nml.playlists is None or nml.playlists.node is None:
        return None
    return find_sandbox(nml.playlists.node, sandbox_name)


def _write_flat_m3u_fixture(import_dir: Path) -> None:
    (import_dir / "MixOne.m3u8").write_text(
        "#EXTM3U\n#EXTINF:100,Artist A - Track A\n../music/House/track-a.mp3\n",
        encoding="utf-8",
    )
    (import_dir / "MixTwo.m3u8").write_text(
        "#EXTM3U\n#EXTINF:200,Artist B - Track B\n../music/Techno/track-b.mp3\n",
        encoding="utf-8",
    )


def _write_nested_m3u_fixture(import_dir: Path) -> None:
    (import_dir / "House").mkdir()
    (import_dir / "House" / "Deep.m3u8").write_text(
        "#EXTM3U\n#EXTINF:100,Artist A - Track A\n../music/House/track-a.mp3\n",
        encoding="utf-8",
    )
    (import_dir / "Techno").mkdir()
    (import_dir / "Techno" / "Rave.m3u8").write_text(
        "#EXTM3U\n#EXTINF:200,Artist B - Track B\n../music/Techno/track-b.mp3\n",
        encoding="utf-8",
    )


def _write_importable_collection(tmp_path: Path) -> Path:
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
        <NODE TYPE="PLAYLIST" NAME="Existing">
          <PLAYLIST ENTRIES="1" TYPE="LIST">
            <ENTRY>
              <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/track-a.mp3"></PRIMARYKEY>
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


def _write_round_trip_collection(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="3">
    <ENTRY TITLE="Alpha" ARTIST="DJ Alpha">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/:Deep/" FILE="alpha.mp3"></LOCATION>
      <INFO PLAYTIME="300000"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/alpha.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Beta" ARTIST="DJ Beta">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/:Deep/" FILE="beta.mp3"></LOCATION>
      <INFO PLAYTIME="400000"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/beta.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Gamma" ARTIST="DJ Gamma">
      <LOCATION VOLUME="C:" DIR=":/Music/:Techno/" FILE="gamma.mp3"></LOCATION>
      <INFO PLAYTIME="500000"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/Techno/gamma.mp3"></PRIMARYKEY>
    </ENTRY>
  </COLLECTION>
  <PLAYLISTS>
    <NODE TYPE="FOLDER" NAME="$ROOT">
      <SUBNODES>
        <NODE TYPE="FOLDER" NAME="Favs">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="Deep Cuts">
              <PLAYLIST ENTRIES="2" TYPE="LIST">
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/alpha.mp3"></PRIMARYKEY>
                </ENTRY>
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/beta.mp3"></PRIMARYKEY>
                </ENTRY>
              </PLAYLIST>
            </NODE>
          </SUBNODES>
        </NODE>
        <NODE TYPE="PLAYLIST" NAME="Techno Bangers">
          <PLAYLIST ENTRIES="1" TYPE="LIST">
            <ENTRY>
              <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/Techno/gamma.mp3"></PRIMARYKEY>
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
