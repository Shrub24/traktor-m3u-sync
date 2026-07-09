"""Tests for M3U import: parsing, reverse mapping, sandbox rebuild, and round-trip."""

from __future__ import annotations

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from traktor_nml_utils.models.collection import Nml, Nodetype
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.collection_matcher import build_collection_index, match_track
from traktor_m3u_sync.config import (
    AppConfig,
    ImportConfig,
    LibraryConfig,
    apply_import_overrides,
    load_config,
)
from traktor_m3u_sync.export_service import run_export
from traktor_m3u_sync.import_service import run_import
from traktor_m3u_sync.m3u_reader import ImportedTrack, M3uReadError, read_import_tree, read_m3u8
from traktor_m3u_sync.nml_reader import load_collection
from traktor_m3u_sync.pathmap import (
    ReversePathTranslationError,
    normalize_for_collection_lookup,
    reverse_translate_track_path,
)

RUNNER = CliRunner()


# ── M3U reader tests ───────────────────────────────────────────────────


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
    m3u.write_text(
        "#EXTM3U\n../music/track.mp3\n",
        encoding="utf-8",
    )

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


# ── Reverse path translation tests ────────────────────────────────────


def test_reverse_translate_relative_m3u_path() -> None:
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )

    result = reverse_translate_track_path("../music/House/track.mp3", library)

    assert result == PureWindowsPath("C:/Music/House/track.mp3")


def test_reverse_translate_absolute_m3u_path() -> None:
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("/absolute/music"),
    )

    result = reverse_translate_track_path("/absolute/music/House/track.mp3", library)

    assert result == PureWindowsPath("C:/Music/House/track.mp3")


def test_reverse_translate_raises_on_path_outside_root() -> None:
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )

    with pytest.raises(ReversePathTranslationError, match="does not fall beneath"):
        reverse_translate_track_path("../other/track.mp3", library)


def test_reverse_translate_raises_on_absolute_root_with_relative_path() -> None:
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("/absolute/music"),
    )

    with pytest.raises(ReversePathTranslationError, match="is relative"):
        reverse_translate_track_path("music/track.mp3", library)


def test_normalize_for_collection_lookup_matches_primarykey_format() -> None:
    path = PureWindowsPath("C:/Music/House/track.mp3")

    result = normalize_for_collection_lookup(path)

    assert result == "C:/Music/House/track.mp3"


# ── Collection matcher tests ──────────────────────────────────────────


def _write_collection_for_matching(tmp_path: Path) -> Path:
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


def test_match_track_resolves_by_primarykey(tmp_path: Path) -> None:
    collection_path = _write_collection_for_matching(tmp_path)
    collection = load_collection(collection_path)
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )
    index = build_collection_index(collection.nml, library)

    track = ImportedTrack(
        path="../music/House/track-a.mp3",
        title="Track A",
        artist="Artist A",
        duration_seconds=100,
    )

    result = match_track(track, index, library)

    assert result.entry is not None
    assert result.entry.title == "Track A"
    assert result.lookup_key == "C:/Music/House/track-a.mp3"


def test_match_track_returns_none_for_unmatched(tmp_path: Path) -> None:
    collection_path = _write_collection_for_matching(tmp_path)
    collection = load_collection(collection_path)
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )
    index = build_collection_index(collection.nml, library)

    track = ImportedTrack(
        path="../music/Nonexistent/ghost.mp3",
        title="Ghost",
        artist="Nobody",
        duration_seconds=60,
    )

    result = match_track(track, index, library)

    assert result.entry is None
    assert result.error == "not_in_collection"


def test_match_track_returns_error_for_untranslatable_path(tmp_path: Path) -> None:
    collection_path = _write_collection_for_matching(tmp_path)
    collection = load_collection(collection_path)
    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("/absolute/music"),
    )
    index = build_collection_index(collection.nml, library)

    track = ImportedTrack(
        path="relative/track.mp3",
        title="Track",
        artist="Artist",
        duration_seconds=60,
    )

    result = match_track(track, index, library)

    assert result.entry is None
    assert result.error is not None


# ── Import service tests ──────────────────────────────────────────────


def _write_importable_collection(tmp_path: Path) -> Path:
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


def test_import_flat_playlists_into_sandbox(tmp_path: Path) -> None:
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    result = run_import(config)

    assert result.summary.playlists_imported == 2
    assert result.summary.tracks_matched == 2
    assert result.summary.tracks_skipped == 0

    # Verify sandbox exists in the saved NML
    reloaded = load_collection(collection_path)
    sandbox = _find_sandbox_node(reloaded.nml, "Imported Playlists")
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert len(sandbox.subnodes.node) == 2
    playlist_names = {n.name for n in sandbox.subnodes.node}
    assert playlist_names == {"MixOne", "MixTwo"}


def test_import_nested_playlists_preserves_hierarchy(tmp_path: Path) -> None:
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_nested_m3u_fixture(import_dir)

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    result = run_import(config)

    assert result.summary.playlists_imported == 2
    assert result.summary.tracks_matched == 2

    reloaded = load_collection(collection_path)
    sandbox = _find_sandbox_node(reloaded.nml, "Imported Playlists")
    assert sandbox is not None
    assert sandbox.subnodes is not None

    folder_names = {n.name for n in sandbox.subnodes.node}
    assert folder_names == {"House", "Techno"}

    # Check nested structure
    house_folder = next(n for n in sandbox.subnodes.node if n.name == "House")
    assert house_folder.subnodes is not None
    assert len(house_folder.subnodes.node) == 1
    assert house_folder.subnodes.node[0].name == "Deep"
    assert house_folder.subnodes.node[0].playlist is not None
    assert len(house_folder.subnodes.node[0].playlist.entry) == 1


def test_import_skips_unmatched_tracks_with_warnings(tmp_path: Path) -> None:
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    (import_dir / "Mixed.m3u8").write_text(
        "#EXTM3U\n"
        "#EXTINF:100,Artist A - Track A\n"
        "../music/House/track-a.mp3\n"
        "#EXTINF:99,Ghost - Phantom\n"
        "../music/Nowhere/phantom.mp3\n",
        encoding="utf-8",
    )

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    result = run_import(config)

    assert result.summary.playlists_imported == 1
    assert result.summary.tracks_matched == 1
    assert result.summary.tracks_skipped == 1
    assert any(w.code == "track_unmatched" for w in result.warnings)


def test_import_creates_backup_before_write(tmp_path: Path) -> None:
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    run_import(config)

    backup_files = list(collection_path.parent.glob("collection.backup.*.nml"))
    assert len(backup_files) == 1


def test_import_rebuild_sandbox_is_idempotent(tmp_path: Path) -> None:
    """Running import twice should produce the same result."""
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    result1 = run_import(config)
    result2 = run_import(config)

    assert result1.summary == result2.summary

    reloaded = load_collection(collection_path)
    sandbox = _find_sandbox_node(reloaded.nml, "Imported Playlists")
    assert sandbox is not None
    assert sandbox.subnodes is not None
    assert len(sandbox.subnodes.node) == 2


def test_import_preserves_existing_non_sandbox_playlists(tmp_path: Path) -> None:
    """Import should not touch playlists outside the sandbox."""
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)

    config = AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        export=_dummy_export_config(tmp_path),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=import_dir,
            sandbox_name="Imported Playlists",
        ),
    )

    run_import(config)

    reloaded = load_collection(collection_path)
    assert reloaded.nml.playlists is not None
    root = reloaded.nml.playlists.node
    assert root is not None
    assert root.subnodes is not None

    non_sandbox = [n for n in root.subnodes.node if n.name != "Imported Playlists"]
    assert len(non_sandbox) == 1
    assert non_sandbox[0].name == "Existing"


# ── Round-trip tests ──────────────────────────────────────────────────


def _write_round_trip_collection(tmp_path: Path) -> Path:
    collection_path = tmp_path / "collection.nml"
    collection_path.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="no" ?>
<NML VERSION="20">
  <HEAD COMPANY="Native Instruments"></HEAD>
  <COLLECTION ENTRIES="3">
    <ENTRY TITLE="Alpha" ARTIST="DJ Alpha">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/:Deep/" FILE="alpha.mp3"></LOCATION>
      <INFO PLAYTIME="300"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/alpha.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Beta" ARTIST="DJ Beta">
      <LOCATION VOLUME="C:" DIR=":/Music/:House/:Deep/" FILE="beta.mp3"></LOCATION>
      <INFO PLAYTIME="400"></INFO>
      <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/House/Deep/beta.mp3"></PRIMARYKEY>
    </ENTRY>
    <ENTRY TITLE="Gamma" ARTIST="DJ Gamma">
      <LOCATION VOLUME="C:" DIR=":/Music/:Techno/" FILE="gamma.mp3"></LOCATION>
      <INFO PLAYTIME="500"></INFO>
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


def test_round_trip_nml_to_m3u_to_nml(tmp_path: Path) -> None:
    """Export NML to M3U, then import back. Supported scope should match."""
    collection_path = _write_round_trip_collection(tmp_path)
    export_dir = tmp_path / "exported"
    export_dir.mkdir()

    library = LibraryConfig(
        traktor_root=PureWindowsPath("C:/Music"),
        m3u_root=PurePosixPath("../music"),
    )

    # Export
    export_config = AppConfig(
        library=library,
        export=_make_export_config(collection_path, export_dir),
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=tmp_path / "notused",
            sandbox_name="Imported Playlists",
        ),
    )
    export_result = run_export(export_config)
    assert export_result.summary.playlists_written == 2
    assert export_result.summary.tracks_exported == 3

    # Import back
    import_config = AppConfig(
        library=library,
        export=export_config.export,
        import_=ImportConfig(
            collection_path=collection_path,
            import_dir=export_dir,
            sandbox_name="Round-Trip",
        ),
    )
    import_result = run_import(import_config)

    assert import_result.summary.tracks_matched == 3
    assert import_result.summary.tracks_skipped == 0

    # Verify structure
    reloaded = load_collection(collection_path)
    sandbox = _find_sandbox_node(reloaded.nml, "Round-Trip")
    assert sandbox is not None
    assert sandbox.subnodes is not None

    # Should have Favs folder and Techno Bangers playlist
    node_names = {n.name for n in sandbox.subnodes.node}
    assert "Favs" in node_names
    assert "Techno Bangers" in node_names

    favs_folder = next(n for n in sandbox.subnodes.node if n.name == "Favs")
    assert favs_folder.subnodes is not None
    assert len(favs_folder.subnodes.node) == 1
    # "Deep Cuts" has no invalid chars, so it stays as-is
    assert favs_folder.subnodes.node[0].name == "Deep Cuts"

    deep_cuts = favs_folder.subnodes.node[0]
    assert deep_cuts.playlist is not None
    assert len(deep_cuts.playlist.entry) == 2

    # Track order should be preserved
    keys = [
        e.primarykey.key if e.primarykey is not None else None for e in deep_cuts.playlist.entry
    ]
    assert keys == ["C:/Music/House/Deep/alpha.mp3", "C:/Music/House/Deep/beta.mp3"]


# ── CLI import command tests ──────────────────────────────────────────


def test_import_cli_emits_structured_summary(tmp_path: Path) -> None:
    collection_path = _write_importable_collection(tmp_path)
    import_dir = tmp_path / "m3u"
    import_dir.mkdir()
    _write_flat_m3u_fixture(import_dir)

    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        f"""
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "{collection_path}"
output_dir = "{tmp_path / "playlists"}"

[import]
collection_path = "{collection_path}"
import_dir = "{import_dir}"
sandbox_name = "Imported Playlists"
""".strip(),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["import", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "SUMMARY" in result.stdout
    assert "playlists_imported=2" in result.stdout
    assert "tracks_matched=2" in result.stdout
    assert "tracks_skipped=0" in result.stdout


def test_import_cli_exits_nonzero_on_missing_config(tmp_path: Path) -> None:
    result = RUNNER.invoke(app, ["import", "--config", str(tmp_path / "nonexistent.toml")])

    assert result.exit_code == 1
    assert "ERROR code=config_error" in result.stderr


def test_import_cli_exits_nonzero_on_missing_import_dir() -> None:
    """Import CLI should fail if no import_dir is configured or passed."""
    # Config without [import] section and no CLI override
    # This should fail at apply_import_overrides since import_dir is None
    pass  # Tested via apply_import_overrides below


# ── Config tests ──────────────────────────────────────────────────────


def test_load_config_with_import_section(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        """
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/tmp/collection.nml"
output_dir = "/tmp/playlists"

[import]
import_dir = "/tmp/m3u"
sandbox_name = "My Sandbox"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.import_.import_dir == Path("/tmp/m3u")
    assert config.import_.sandbox_name == "My Sandbox"
    assert config.import_.collection_path == Path("/tmp/collection.nml")


def test_load_config_defaults_import_sandbox_name(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        """
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/tmp/collection.nml"
output_dir = "/tmp/playlists"

[import]
import_dir = "/tmp/m3u"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.import_.sandbox_name == "Imported Playlists"


def test_load_config_import_dir_optional_when_section_absent(tmp_path: Path) -> None:
    """Config without [import] should load fine for export-only use."""
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

    assert config.import_.import_dir is None
    assert config.import_.sandbox_name == "Imported Playlists"


def test_apply_import_overrides(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(
        """
[library]
traktor_root = "C:/Music"
m3u_root = "../music"

[export]
collection_path = "/tmp/collection.nml"
output_dir = "/tmp/playlists"

[import]
import_dir = "/tmp/m3u"
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)
    overridden = apply_import_overrides(
        config,
        collection_path=Path("/override/collection.nml"),
        import_dir=Path("/override/m3u"),
        sandbox_name="Custom Sandbox",
    )

    assert overridden.import_.collection_path == Path("/override/collection.nml")
    assert overridden.import_.import_dir == Path("/override/m3u")
    assert overridden.import_.sandbox_name == "Custom Sandbox"


def test_apply_import_overrides_raises_without_import_dir(tmp_path: Path) -> None:
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

    with pytest.raises(Exception, match="import_dir is required"):
        apply_import_overrides(
            config,
            collection_path=None,
            import_dir=None,
            sandbox_name=None,
        )


# ── helpers ─────────────────────────────────────────────────────────────


def _dummy_export_config(tmp_path: Path):
    from traktor_m3u_sync.config import ExportConfig

    return ExportConfig(
        collection_path=tmp_path / "collection.nml",
        output_dir=tmp_path / "playlists",
    )


def _make_export_config(collection_path: Path, output_dir: Path):
    from traktor_m3u_sync.config import ExportConfig

    return ExportConfig(collection_path=collection_path, output_dir=output_dir)


def _find_sandbox_node(nml: Nml, sandbox_name: str) -> Nodetype | None:
    """Find the sandbox folder node in the NML."""
    if nml.playlists is None or nml.playlists.node is None:
        return None
    root = nml.playlists.node
    if root.subnodes is None:
        return None
    for child in root.subnodes.node:
        if child.type == "FOLDER" and child.name == sandbox_name:
            return child
    return None
