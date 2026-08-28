"""Tests for the iTunes XML export leg (store -> iTunes Music Library plist)."""

from __future__ import annotations

import plistlib
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

import pytest
from typer.testing import CliRunner

from traktor_m3u_sync.cli import app
from traktor_m3u_sync.config import (
    AppConfig,
    ConfigError,
    ItunesConfig,
    LibraryConfig,
    M3uConfig,
    NmlConfig,
    StoreConfig,
    apply_export_overrides,
    load_config,
)
from traktor_m3u_sync.formats.itunes import exporter as itunes_exporter
from traktor_m3u_sync.formats.itunes.exporter import ItunesExporter
from traktor_m3u_sync.model import Playlist, Track
from traktor_m3u_sync.model.identity import identify
from traktor_m3u_sync.services import run_export, run_import
from traktor_m3u_sync.store import StoreNotPopulatedError

RUNNER = CliRunner()

PERSISTENT_ID = re.compile(r"^[0-9A-F]{16}$")


# ── document structure ──────────────────────────────────────────────────


def test_export_writes_minimal_plus_plist_document(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (_playlist(base, name="Deep", folder=("House",), rel="House/track.mp3"),)

    document = _export(base, playlists, tmp_path)

    assert document["Major Version"] == 1
    assert document["Minor Version"] == 1
    assert document["Application Version"] == "traktor-m3u-sync"
    assert re.search(r"<date>\d{4}-\d{2}-\d{2}T[\d:]+Z</date>", _xml(tmp_path))
    assert document["Music Folder"] == f"{base.as_uri()}/"
    assert PERSISTENT_ID.match(document["Library Persistent ID"])

    (entry,) = document["Tracks"].values()
    assert entry["Name"] == "Track One"
    assert entry["Artist"] == "Artist One"
    assert entry["Album"] == "Album One"
    assert entry["Total Time"] == 123000
    assert entry["Track Type"] == "File"
    assert entry["Location"] == f"{(base / 'House/track.mp3').as_uri()}"

    folders = [p for p in document["Playlists"] if p.get("Folder")]
    playlist = next(p for p in document["Playlists"] if not p.get("Folder"))
    assert folders[0]["All Items"] is True
    assert playlist["Playlist Items"] == [{"Track ID": entry["Track ID"]}]


def test_omits_unknown_metadata_and_never_emits_smart_fields(tmp_path: Path) -> None:
    base = _library(tmp_path)
    track = _resolved_track("House/bare.mp3", album=None, duration=None)
    playlists = (Playlist(name="Bare", tracks=(track,)),)

    output = tmp_path / "Library.xml"
    ItunesExporter(base, output).write(playlists)
    document = plistlib.load(output.open("rb"))

    entry = next(iter(document["Tracks"].values()))
    assert "Album" not in entry
    assert "Total Time" not in entry
    text = output.read_text(encoding="utf-8")
    assert "Smart" not in text
    assert "Distinguished Kind" not in text
    assert "Master" not in text
    assert "Play Count" not in text


# ── stable identifiers ──────────────────────────────────────────────────


def test_identifiers_stable_across_repeated_exports(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="Deep", rel="House/b-track.mp3"),
        _playlist(base, name="Root", rel="House/a-track.mp3"),
    )
    exporter = ItunesExporter(base, tmp_path / "Library.xml")

    exporter.write(playlists)
    first = plistlib.load((tmp_path / "Library.xml").open("rb"))
    exporter.write(playlists)
    second = plistlib.load((tmp_path / "Library.xml").open("rb"))

    del first["Date"], second["Date"]
    assert first == second


def test_track_ids_assigned_in_sorted_identity_order(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="One", rel="House/zeta.mp3"),
        _playlist(base, name="Two", rel="House/alpha.mp3"),
    )

    document = _export(base, playlists, tmp_path)

    ids = {entry["Location"]: entry["Track ID"] for entry in document["Tracks"].values()}
    alpha = ids[f"{(base / 'House/alpha.mp3').as_uri()}"]
    zeta = ids[f"{(base / 'House/zeta.mp3').as_uri()}"]
    assert alpha < zeta
    assert list(document["Tracks"]) == [str(i) for i in sorted(ids.values())]


def test_persistent_ids_unique_per_identity(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="One", rel="House/one.mp3"),
        _playlist(base, name="Two", rel="House/two.mp3"),
    )

    document = _export(base, playlists, tmp_path)

    persistent = (
        [entry["Persistent ID"] for entry in document["Tracks"].values()]
        + [p["Playlist Persistent ID"] for p in document["Playlists"]]
        + [document["Library Persistent ID"]]
    )
    assert all(PERSISTENT_ID.match(pid) for pid in persistent)
    assert len(set(persistent)) == len(persistent)


def test_delimiter_like_folder_paths_do_not_collide(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="Slash", folder=("A/B",), rel="ab/one.mp3"),
        _playlist(base, name="Nested", folder=("A", "B"), rel="a/b/two.mp3"),
    )

    document = _export(base, playlists, tmp_path)

    by_name = {p["Name"]: p for p in document["Playlists"]}
    flat, outer, inner = by_name["A/B"], by_name["A"], by_name["B"]
    assert flat["Playlist Persistent ID"] != inner["Playlist Persistent ID"]
    assert inner["Parent Persistent ID"] == outer["Playlist Persistent ID"]
    assert by_name["Slash"]["Parent Persistent ID"] == flat["Playlist Persistent ID"]
    assert "Parent Persistent ID" not in outer


def test_duplicate_playlist_names_in_one_folder_get_unique_stable_ids(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="Deep", folder=("House",), rel="House/one.mp3"),
        _playlist(base, name="Deep", folder=("House",), rel="House/two.mp3"),
    )

    first = _export(base, playlists, tmp_path)
    second = _export(base, playlists, tmp_path)

    deeps = [p["Playlist Persistent ID"] for p in first["Playlists"] if p["Name"] == "Deep"]
    assert len(set(deeps)) == 2
    house = next(p for p in first["Playlists"] if p.get("Folder"))["Playlist Persistent ID"]
    deep_entries = [p for p in first["Playlists"] if p["Name"] == "Deep"]
    assert all(p["Parent Persistent ID"] == house for p in deep_entries)
    assert first["Playlists"] == second["Playlists"]


def test_truncated_hash_collisions_resolve_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_persistent_id(seed: str) -> str:
        return f"{int(seed.rsplit('#', 1)[-1]):016X}"

    monkeypatch.setattr(itunes_exporter, "_persistent_id", fake_persistent_id)
    base = _library(tmp_path)
    playlists = tuple(_playlist(base, name=f"P{i}", rel=f"p{i}.mp3") for i in range(3))

    def ids() -> list[str]:
        document = _export(base, playlists, tmp_path)
        return (
            [entry["Persistent ID"] for entry in document["Tracks"].values()]
            + [p["Playlist Persistent ID"] for p in document["Playlists"]]
            + [document["Library Persistent ID"]]
        )

    first = ids()
    assert len(set(first)) == len(first)
    assert ids() == first


# ── locations and durations ─────────────────────────────────────────────


@pytest.mark.parametrize(
    "rel",
    ["House/01 Track.mp3", "House/#9 track.mp3", "House/Ünïcødé ßong.mp3"],
)
def test_location_percent_encodes_special_characters(tmp_path: Path, rel: str) -> None:
    base = _library(tmp_path)
    playlists = (_playlist(base, rel=rel),)

    document = _export(base, playlists, tmp_path)

    location = next(iter(document["Tracks"].values()))["Location"]
    assert location == (base / rel).as_uri()
    assert location.startswith("file://")
    assert all(ord(char) < 128 for char in location)


def test_scenario_location_matches_expected_uri(tmp_path: Path) -> None:
    base = _library(tmp_path)

    document = _export(base, (_playlist(base, rel="House/01 Track.mp3"),), tmp_path)

    entry = next(iter(document["Tracks"].values()))
    assert Path(entry["Location"].removeprefix("file://")).name == "01%20Track.mp3"
    assert entry["Total Time"] == 123 * 1000


def test_unresolved_track_skipped_with_warning(tmp_path: Path) -> None:
    base = _library(tmp_path)
    unresolved = Track(title="Bad", artist="Artist", raw_path="D:/other/bad.mp3")
    playlists = (Playlist(name="Mixed", tracks=(_resolved_track("House/good.mp3"), unresolved)),)
    output = tmp_path / "Library.xml"

    result = ItunesExporter(base, output).write(playlists)
    document = plistlib.load(output.open("rb"))

    skip = [w for w in result.warnings if w.code == "track_unresolved"]
    assert len(skip) == 1 and skip[0].playlist == "Mixed"
    assert len(document["Tracks"]) == 1
    assert result.counts["tracks_skipped"] == 1
    items = next(p for p in document["Playlists"] if not p.get("Folder"))["Playlist Items"]
    assert [ref["Track ID"] for ref in items] == [
        entry["Track ID"] for entry in document["Tracks"].values()
    ]


# ── folder mirroring ────────────────────────────────────────────────────


def test_folder_hierarchy_links_children_to_parent_persistent_ids(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="Sub", folder=("House", "Deep"), rel="House/Deep/s.mp3"),
        _playlist(base, name="Top", folder=("Techno",), rel="Techno/t.mp3"),
        _playlist(base, name="Rooty", rel="root.mp3"),
    )

    document = _export(base, playlists, tmp_path)

    by_name = {p["Name"]: p for p in document["Playlists"]}
    house = by_name["House"]
    deep = by_name["Deep"]
    assert house["Folder"] is True and "Parent Persistent ID" not in house
    assert deep["Folder"] is True
    assert deep["Parent Persistent ID"] == house["Playlist Persistent ID"]
    assert by_name["Sub"]["Parent Persistent ID"] == deep["Playlist Persistent ID"]
    assert "Parent Persistent ID" not in by_name["Techno"]
    assert "Parent Persistent ID" not in by_name["Rooty"]


def test_sibling_folder_keeps_distinct_parent(tmp_path: Path) -> None:
    base = _library(tmp_path)
    playlists = (
        _playlist(base, name="Sub", folder=("House", "Deep"), rel="House/Deep/s.mp3"),
        _playlist(base, name="Top", folder=("Techno",), rel="Techno/t.mp3"),
    )

    document = _export(base, playlists, tmp_path)

    by_name = {p["Name"]: p for p in document["Playlists"]}
    techno = by_name["Techno"]
    assert techno["Folder"] is True and "Parent Persistent ID" not in techno
    assert by_name["Top"]["Parent Persistent ID"] == techno["Playlist Persistent ID"]


# ── existence check ─────────────────────────────────────────────────────


def test_missing_files_warn_without_blocking_export(tmp_path: Path) -> None:
    base = tmp_path / "unmounted"
    playlists = (Playlist(name="Detached", tracks=(_resolved_track("House/ghost.mp3"),)),)
    output = tmp_path / "Library.xml"

    result = ItunesExporter(base, output).write(playlists)
    document = plistlib.load(output.open("rb"))

    missing = [w for w in result.warnings if w.code == "file_missing"]
    assert len(missing) == 1
    assert "House/ghost.mp3" in (missing[0].detail or "")
    assert len(document["Tracks"]) == 1
    assert result.counts["warnings_emitted"] == 1


# ── end-to-end: m3u import -> store -> itunes export ────────────────────


def test_m3u_import_then_itunes_export_keeps_referential_integrity(
    tmp_path: Path,
) -> None:
    config_path = _write_config(tmp_path)
    store = config_path.parent / "store.db"

    imported = RUNNER.invoke(
        app, ["import", "--format", "m3u", "--config", str(config_path)], catch_exceptions=False
    )
    exported = RUNNER.invoke(
        app,
        [
            "export",
            "--format",
            "itunes",
            "--config",
            str(config_path),
            "--store",
            str(store),
        ],
        catch_exceptions=False,
    )

    assert imported.exit_code == 0
    assert exported.exit_code == 0
    assert "SUMMARY playlists_written=2 tracks_exported=2" in exported.stdout
    document = plistlib.load((tmp_path / "out" / "iTunes Music Library.xml").open("rb"))
    track_ids = {entry["Track ID"] for entry in document["Tracks"].values()}
    names = {p["Name"] for p in document["Playlists"] if not p.get("Folder")}
    assert names == {"Deep", "Rave"}
    for playlist in document["Playlists"]:
        for ref in playlist.get("Playlist Items", []):
            assert ref["Track ID"] in track_ids


def test_itunes_import_is_unsupported(tmp_path: Path) -> None:
    config = _app_config(tmp_path)

    with pytest.raises(ValueError, match="Unsupported format 'itunes' for import"):
        run_import(config, "itunes")


def test_itunes_export_requires_configured_fields(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path, with_itunes=False)

    result = RUNNER.invoke(app, ["export", "--format", "itunes", "--config", str(config_path)])

    assert result.exit_code == 1
    assert "output_file is required for iTunes export" in result.stderr


def test_itunes_export_fails_fast_on_empty_store(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    with pytest.raises(StoreNotPopulatedError, match="run import first"):
        run_export(config, "itunes")


# ── config ──────────────────────────────────────────────────────────────


def test_load_config_without_itunes_section(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, with_itunes=False))

    assert config.itunes == ItunesConfig()


def test_itunes_export_overrides_validate_and_win(tmp_path: Path) -> None:
    bare = load_config(_write_config(tmp_path, with_itunes=False))

    with pytest.raises(ConfigError, match="base_path is required for iTunes export"):
        apply_export_overrides(bare, format="itunes", output_file=tmp_path / "x.xml")

    config = load_config(_write_config(tmp_path))
    overridden = apply_export_overrides(
        config,
        format="itunes",
        output_file=tmp_path / "other.xml",
        base_path=tmp_path / "other-music",
    )
    assert overridden.itunes.output_file == tmp_path / "other.xml"
    assert overridden.itunes.base_path == tmp_path / "other-music"
    assert overridden.m3u.output_dir == tmp_path / "out"


def test_m3u_and_nml_commands_ignore_missing_itunes(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path, with_itunes=False))

    assert apply_export_overrides(config, format="m3u").itunes == ItunesConfig()
    assert apply_export_overrides(config, format="nml").itunes == ItunesConfig()


def test_itunes_export_rejects_relative_base_path(tmp_path: Path) -> None:
    config_path = tmp_path / "traktor-m3u-sync.toml"
    config_path.write_text(_config_text(tmp_path, base_path="music"), encoding="utf-8")
    config = load_config(config_path)

    assert config.itunes.base_path == Path("music")
    with pytest.raises(ConfigError, match="base_path must be an absolute path"):
        apply_export_overrides(config, format="itunes")
    assert apply_export_overrides(config, format="m3u").itunes.base_path == Path("music")


def test_itunes_export_rejects_relative_base_path_override(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    with pytest.raises(ConfigError, match="base_path must be an absolute path"):
        apply_export_overrides(config, format="itunes", base_path=Path("other-music"))


def test_itunes_export_accepts_absolute_base_path(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))

    resolved = apply_export_overrides(config, format="itunes")

    assert resolved.itunes.base_path == tmp_path / "music"
    assert resolved.itunes.output_file == tmp_path / "out" / "iTunes Music Library.xml"


# ── atomic publication and dry run ───────────────────────────────────────


def test_itunes_export_replaces_existing_target_without_temp_leftovers(tmp_path: Path) -> None:
    base = _library(tmp_path)
    target_dir = tmp_path / "lib"
    target_dir.mkdir()
    output = target_dir / "Library.xml"
    output.write_bytes(b"stale")

    ItunesExporter(base, output).write((_playlist(base, rel="House/track.mp3"),))

    assert plistlib.load(output.open("rb"))["Major Version"] == 1
    assert [p.name for p in target_dir.iterdir()] == ["Library.xml"]


def test_itunes_write_failure_leaves_existing_target_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = _library(tmp_path)
    target_dir = tmp_path / "lib"
    target_dir.mkdir()
    output = target_dir / "Library.xml"
    output.write_bytes(b"stale")

    def failing_replace(src: object, dst: object) -> None:
        raise OSError("no space left on device")

    monkeypatch.setattr("os.replace", failing_replace)

    with pytest.raises(OSError, match="no space"):
        ItunesExporter(base, output).write((_playlist(base, rel="House/track.mp3"),))

    assert output.read_bytes() == b"stale"
    assert [p.name for p in target_dir.iterdir()] == ["Library.xml"]


def test_itunes_dry_run_matches_real_export_without_writing_target(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path))
    run_import(config, "m3u")
    target = tmp_path / "out" / "iTunes Music Library.xml"
    target.write_bytes(b"stale")

    dry = run_export(config, "itunes", dry_run=True)

    assert target.read_bytes() == b"stale"
    real = run_export(config, "itunes")
    assert dry.counts == real.counts
    assert dry.counts["playlists_written"] == 2
    assert target.read_bytes() != b"stale"


# ── helpers ─────────────────────────────────────────────────────────────


def _library(tmp_path: Path) -> Path:
    base = tmp_path / "music"
    base.mkdir(exist_ok=True)
    return base


def _resolved_track(
    rel: str, *, album: str | None = "Album One", duration: int | None = 123
) -> Track:
    return identify(
        Track(
            title="Track One",
            artist="Artist One",
            path=rel,
            raw_path=rel,
            album=album,
            duration_seconds=duration,
        )
    )


def _playlist(
    base: Path,
    *,
    name: str = "Deep",
    folder: tuple[str, ...] = (),
    rel: str = "House/track.mp3",
) -> Playlist:
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    return Playlist(name=name, folder_path=folder, tracks=(_resolved_track(rel),))


def _export(base: Path, playlists: tuple[Playlist, ...], tmp_path: Path) -> dict[str, Any]:
    output = tmp_path / "Library.xml"
    ItunesExporter(base, output).write(playlists)
    return plistlib.load(output.open("rb"))


def _xml(tmp_path: Path) -> str:
    return (tmp_path / "Library.xml").read_text(encoding="utf-8")


def _app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath("C:/Music"),
            m3u_root=PurePosixPath("../music"),
        ),
        store=StoreConfig(path=tmp_path / "store.db"),
        nml=NmlConfig(collection_path=tmp_path / "collection.nml"),
        m3u=M3uConfig(output_dir=tmp_path / "out", import_dir=tmp_path / "in"),
        itunes=ItunesConfig(
            output_file=tmp_path / "out" / "iTunes Music Library.xml",
            base_path=tmp_path / "music",
        ),
    )


def _config_text(tmp_path: Path, *, with_itunes: bool = True, base_path: str | None = None) -> str:
    text = (
        f'[library]\ntraktor_root = "C:/Music"\nm3u_root = "../music"\n\n'
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[nml]\ncollection_path = "{tmp_path / "collection.nml"}"\n\n'
        f'[m3u]\noutput_dir = "{tmp_path / "out"}"\nimport_dir = "{tmp_path / "in"}"\n'
    )
    if with_itunes:
        configured = tmp_path / "music" if base_path is None else base_path
        text += (
            f'\n[itunes]\noutput_file = "{tmp_path / "out" / "iTunes Music Library.xml"}"\n'
            f'base_path = "{configured}"\n'
        )
    return text


def _write_config(tmp_path: Path, *, with_itunes: bool = True) -> Path:
    (tmp_path / "in").mkdir(exist_ok=True)
    (tmp_path / "out").mkdir(exist_ok=True)
    _write_m3u_fixture(tmp_path)
    path = tmp_path / "traktor-m3u-sync.toml"
    path.write_text(_config_text(tmp_path, with_itunes=with_itunes), encoding="utf-8")
    return path


def _write_m3u_fixture(tmp_path: Path) -> None:
    (tmp_path / "in" / "House").mkdir(parents=True, exist_ok=True)
    (tmp_path / "in" / "House" / "Deep.m3u8").write_text(
        "#EXTM3U\n#EXTINF:123,Artist One - Track One\n../music/House/track-one.mp3\n",
        encoding="utf-8",
    )
    (tmp_path / "in" / "Rave.m3u8").write_text(
        "#EXTM3U\n../music/techno/track-two.mp3\n", encoding="utf-8"
    )
    for rel in ("House/track-one.mp3", "techno/track-two.mp3"):
        file = tmp_path / "music" / rel
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"audio")
