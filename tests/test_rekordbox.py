"""Tests for the rekordbox XML export leg (store -> rekordbox playlists-sharing XML)."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from traktor_m3u_sync.config import ConfigError, apply_export_overrides, load_config
from traktor_m3u_sync.formats.rekordbox import RekordboxExporter
from traktor_m3u_sync.model import Playlist, Track
from traktor_m3u_sync.paths.uri import FileUriMapping
from traktor_m3u_sync.services import run_export
from traktor_m3u_sync.store import PlaylistStore

BASE = "file://localhost/M:/Music"


def _track(path: str, *, album: str | None = None, duration: int | None = None) -> Track:
    return Track(
        title=Path(path).stem,
        artist="Artist",
        path=path,
        identity=path.casefold(),
        album=album,
        duration_seconds=duration,
    )


def _export(tmp_path: Path, playlists: tuple[Playlist, ...], check: Path | None = None):
    output = tmp_path / "rekordbox.xml"
    result = RekordboxExporter(FileUriMapping(BASE), output, check).write(playlists)
    return result, ET.parse(output).getroot()


def _tree(node: ET.Element) -> list[object]:
    """Playlist nodes as (name, type, count-or-keys, children) for structural comparison."""
    shape: list[object] = []
    for child in node.findall("NODE"):
        if child.get("Type") == "0":
            shape.append((child.get("Name"), child.get("Count"), _tree(child)))
        else:
            keys = [t.get("Key") for t in child.findall("TRACK")]
            assert child.get("KeyType") == "0"
            assert child.get("Entries") == str(len(keys))
            shape.append((child.get("Name"), keys))
    return shape


def test_export_writes_collection_and_playlist_tree(tmp_path: Path) -> None:
    deep = _track("House/01 Deep Track.mp3", album="Album", duration=321)
    rave = _track("Techno/Ravé #1.flac")
    unresolved = Track(
        title="Lost", artist="Nobody", raw_path="C:/elsewhere/lost.mp3", resolved=False
    )
    playlists = (
        Playlist("Deep", ("House", "Late"), (deep, rave, deep)),
        Playlist("Rave", (), (rave, unresolved)),
        Playlist("Warmup", ("House",), (deep,)),
    )

    result, root = _export(tmp_path, playlists)

    assert root.tag == "DJ_PLAYLISTS" and root.get("Version") == "1.0.0"
    assert root.find("PRODUCT") is not None
    collection = root.find("COLLECTION")
    assert collection is not None
    tracks = collection.findall("TRACK")
    assert collection.get("Entries") == str(len(tracks)) == "2"
    assert [t.attrib for t in tracks] == [
        {
            "TrackID": "1",
            "Name": "01 Deep Track",
            "Artist": "Artist",
            "Location": f"{BASE}/House/01%20Deep%20Track.mp3",
            "Album": "Album",
            "TotalTime": "321",
        },
        {
            "TrackID": "2",
            "Name": "Ravé #1",
            "Artist": "Artist",
            "Location": f"{BASE}/Techno/Rav%C3%A9%20%231.flac",
        },
    ]
    playlist_root = root.find("PLAYLISTS/NODE")
    assert playlist_root is not None
    assert (playlist_root.get("Type"), playlist_root.get("Name")) == ("0", "ROOT")
    assert playlist_root.get("Count") == "2"
    assert _tree(playlist_root) == [
        ("House", "2", [("Late", "1", [("Deep", ["1", "2", "1"])]), ("Warmup", ["1"])]),
        ("Rave", ["2"]),
    ]
    assert result.counts == {
        "playlists_written": 3,
        "tracks_exported": 2,
        "tracks_skipped": 1,
        "warnings_emitted": 1,
    }
    assert [(w.code, w.playlist) for w in result.warnings] == [("track_unresolved", "Rave")]


def test_missing_local_file_warns_and_still_exports(tmp_path: Path) -> None:
    music = tmp_path / "music"
    (music / "House").mkdir(parents=True)
    (music / "House/present.mp3").write_bytes(b"audio")
    playlists = (Playlist("P", (), (_track("House/present.mp3"), _track("House/absent.mp3"))),)

    result, root = _export(tmp_path, playlists, check=music)

    assert len(root.findall("COLLECTION/TRACK")) == 2
    assert [(w.code, w.detail) for w in result.warnings] == [
        ("file_missing", (music / "House/absent.mp3").as_posix())
    ]


def test_repeated_export_of_unchanged_store_is_byte_identical(tmp_path: Path) -> None:
    playlists = (Playlist("P", ("F",), (_track("b.mp3"), _track("a.mp3"))),)
    output = tmp_path / "rekordbox.xml"
    exporter = RekordboxExporter(FileUriMapping(BASE), output)

    exporter.write(playlists)
    first = output.read_bytes()
    exporter.write(playlists)

    assert output.read_bytes() == first


def _write_toml(tmp_path: Path, rekordbox: str) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f'[store]\npath = "{tmp_path / "store.db"}"\n\n'
        f'[itunes]\noutput_file = "{tmp_path / "itunes.xml"}"\nlocation_base = "file:///itunes"\n\n'
        f"[rekordbox]\n{rekordbox}",
        encoding="utf-8",
    )
    return path


def test_rekordbox_requires_its_own_section(tmp_path: Path) -> None:
    config = load_config(_write_toml(tmp_path, f'output_file = "{tmp_path / "rb.xml"}"\n'))

    with pytest.raises(ConfigError, match=r"\[rekordbox\]\.location_base"):
        apply_export_overrides(config, format="rekordbox")


def test_cli_overrides_apply_only_to_the_selected_format(tmp_path: Path) -> None:
    config = load_config(
        _write_toml(tmp_path, f'output_file = "{tmp_path / "rb.xml"}"\nlocation_base = "{BASE}"\n')
    )

    applied = apply_export_overrides(config, format="rekordbox", location_base="file:///override")

    assert applied.rekordbox.location_base == "file:///override"
    assert applied.rekordbox.output_file == tmp_path / "rb.xml"
    assert applied.itunes == config.itunes


def test_dry_run_leaves_configured_output_untouched(tmp_path: Path) -> None:
    output = tmp_path / "rb.xml"
    config = load_config(
        _write_toml(tmp_path, f'output_file = "{output}"\nlocation_base = "{BASE}"\n')
    )
    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild((Playlist("P", (), (_track("a.mp3"),)),), source_format="m3u")

    dry = run_export(apply_export_overrides(config, format="rekordbox"), "rekordbox", dry_run=True)

    assert dry.counts["tracks_exported"] == 1
    assert not output.exists()
    real = run_export(apply_export_overrides(config, format="rekordbox"), "rekordbox")
    assert real.counts == dry.counts
    assert output.is_file()
