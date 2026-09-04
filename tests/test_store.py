"""Tests for the SQLite store: schema, ordering, identity dedup, and rebuild semantics."""

from __future__ import annotations

import sqlite3
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest
from traktor_nml_utils.models.collection import Nml, Nodetype

from traktor_m3u_sync.formats.nml.exporter import NmlExporter
from traktor_m3u_sync.formats.nml.reader import load_collection
from traktor_m3u_sync.model import Playlist, Track
from traktor_m3u_sync.model.identity import identify, identify_playlists, normalize_identity
from traktor_m3u_sync.paths.traktor import TraktorPathMapping
from traktor_m3u_sync.store import (
    SCHEMA_VERSION,
    PlaylistStore,
    StoreError,
    StoreSchemaError,
)


def _track(path: str, *, title: str = "T", artist: str = "A") -> Track:
    return identify(Track(title=title, artist=artist, path=path, raw_path=path))


def _playlist(name: str, *paths: str, folder: tuple[str, ...] = ()) -> Playlist:
    return Playlist(
        name=name,
        folder_path=folder,
        tracks=tuple(_track(path) for path in paths),
    )


def test_store_round_trips_playlists_in_order(tmp_path: Path) -> None:
    playlists = (
        _playlist("Deep", "House/a.mp3", "House/b.mp3", folder=("Favs",)),
        _playlist("Empty"),
        _playlist("Rave", "Techno/c.mp3"),
    )

    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild(playlists, source_format="m3u")
        assert store.count_playlists() == 3
        loaded = store.load_playlists()

    assert loaded == playlists


def test_store_rebuild_replaces_previous_snapshot(tmp_path: Path) -> None:
    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild((_playlist("Old", "x.mp3"),), source_format="m3u")
        store.rebuild((_playlist("New", "y.mp3"), _playlist("Also", "z.mp3")), source_format="m3u")
        loaded = store.load_playlists()

        assert [playlist.name for playlist in loaded] == ["New", "Also"]
        assert store.count_tracks() == 2


def test_store_deduplicates_tracks_by_identity(tmp_path: Path) -> None:
    shared = _playlist("Shared", "House/a.mp3")

    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild(
            (shared, _playlist("Other", "House/a.mp3", "Techno/b.mp3")), source_format="m3u"
        )

        assert store.count_tracks() == 2
        assert len(_query_track_ids(tmp_path / "store.db")) == 2


def test_store_preserves_duplicate_positions_within_a_playlist(tmp_path: Path) -> None:
    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild((_playlist("Loop", "House/a.mp3", "House/a.mp3"),), source_format="m3u")
        assert store.count_tracks() == 1
        loaded = store.load_playlists()

    assert [track.path for track in loaded[0].tracks] == ["House/a.mp3", "House/a.mp3"]


def test_store_keeps_unresolved_tracks_with_raw_path(tmp_path: Path) -> None:
    unresolved = identify(Track(title="", artist="", raw_path="D:/weird/track.mp3"))
    assert unresolved.resolved is False

    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild((Playlist(name="Mixed", tracks=(unresolved,)),), source_format="m3u")
        assert store.count_tracks() == 1
        loaded = store.load_playlists()

    assert loaded[0].tracks[0].raw_path == "D:/weird/track.mp3"
    assert loaded[0].tracks[0].resolved is False


def test_store_rejects_schema_version_mismatch_in_read_only(tmp_path: Path) -> None:
    path = tmp_path / "store.db"
    with PlaylistStore(path) as store:
        store.rebuild((_playlist("Deep", "a.mp3"),), source_format="m3u")

    with sqlite3.connect(path) as connection:
        connection.execute("UPDATE meta SET schema_version = ?", (SCHEMA_VERSION + 1,))
        connection.commit()

    with pytest.raises(StoreSchemaError, match="re-run import"):
        PlaylistStore(path, read_only=True)
    # Write mode treats the stale store as a disposable cache: it resets in place
    # instead of raising, so the next rebuild can run (M3).
    with PlaylistStore(path) as store:
        assert store.count_tracks() == 0


def test_v1_store_write_mode_resets_and_stamps_provenance(tmp_path: Path) -> None:
    """A pre-provenance v1 store upgrades in place on write, read-only still fails fast."""
    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE meta (schema_version INTEGER NOT NULL);"
            "CREATE TABLE tracks (id INTEGER PRIMARY KEY);"
            "CREATE TABLE playlists (id INTEGER PRIMARY KEY);"
            "CREATE TABLE playlist_tracks ("
            "playlist_id INTEGER NOT NULL, track_id INTEGER NOT NULL"
            ");"
            "INSERT INTO meta (schema_version) VALUES (1);"
        )

    with pytest.raises(StoreSchemaError, match="re-run import"):
        PlaylistStore(path, read_only=True)

    with PlaylistStore(path) as store:
        store.rebuild((_playlist("Deep", "a.mp3"),), source_format="m3u")
        assert store.count_tracks() == 1
        assert store.provenance().source_format == "m3u"

    with PlaylistStore(path, read_only=True) as store:
        assert store.count_tracks() == 1


def test_legacy_store_without_provenance_is_rejected_read_only(tmp_path: Path) -> None:
    """A pre-provenance store (meta without the two columns) fails like a schema mismatch."""
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE meta (schema_version INTEGER NOT NULL)")
        connection.execute("INSERT INTO meta (schema_version) VALUES (1)")

    with pytest.raises(StoreSchemaError, match="re-run import"):
        PlaylistStore(path, read_only=True)
    # Write mode resets the stale legacy store instead of raising (M3).
    with PlaylistStore(path) as store:
        assert store.count_playlists() == 0


def test_rebuild_records_store_provenance(tmp_path: Path) -> None:
    path = tmp_path / "store.db"

    with PlaylistStore(path) as store:
        store.rebuild((_playlist("Deep", "a.mp3"),), source_format="m3u")
        provenance = store.provenance()
        store.rebuild((_playlist("Rave", "b.mp3"),), source_format="nml")
        provenance_after_rebuild = store.provenance()

    assert provenance.source_format == "m3u"
    assert provenance_after_rebuild.source_format == "nml"
    assert provenance_after_rebuild.imported_at >= provenance.imported_at
    # Imported timestamps are UTC ISO-8601 with second precision.
    assert provenance.imported_at.endswith("+00:00")


def test_empty_store_loads_nothing(tmp_path: Path) -> None:
    with PlaylistStore(tmp_path / "store.db") as store:
        assert store.load_playlists() == ()
        assert store.count_playlists() == 0


def test_store_rejects_directory_path(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="not a database file"):
        PlaylistStore(tmp_path)


def test_store_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "deeper" / "store.db"

    with PlaylistStore(path) as store:
        store.rebuild((_playlist("Deep", "a.mp3"),), source_format="m3u")

    assert path.is_file()


# ── identity normalization ──────────────────────────────────────────────


def test_identity_is_casefolded_posix() -> None:
    assert normalize_identity("House//Mixed//A.MP3") == "house//mixed//a.mp3".casefold()
    assert _track("House/A.MP3").identity == "house/a.mp3"


def test_fallback_identity_collapses_whitespace(tmp_path: Path) -> None:
    track = identify(Track(title="  Deep   Cuts ", artist=" DJ  Alpha ", raw_path="unmapped"))

    assert track.identity == "artist+title:dj alpha - deep cuts"
    assert track.resolved is True


def test_ambiguous_fallback_collisions_are_flagged() -> None:
    first = Track(title="Same", artist="Dj", raw_path="unmapped/one.mp3")
    second = Track(title="Same", artist="Dj", raw_path="unmapped/two.mp3")

    playlists, warnings = identify_playlists(
        (Playlist(name="P", tracks=(identify(first), identify(second))),)
    )

    assert [w.code for w in warnings] == ["ambiguous_identity"]
    assert playlists[0].tracks[0].resolved is False
    assert playlists[0].tracks[0].raw_path == "unmapped/one.mp3"


def test_distinct_fallback_identities_are_kept_apart() -> None:
    first = identify(Track(title="Same", artist="Dj", raw_path="unmapped/one.mp3"))
    second = identify(Track(title="Other", artist="Dj", raw_path="unmapped/two.mp3"))

    playlists, warnings = identify_playlists((Playlist(name="P", tracks=(first, second)),))

    assert warnings == ()
    assert [track.identity for track in playlists[0].tracks] == [
        "artist+title:dj - same",
        "artist+title:dj - other",
    ]


# ── NML <-> store invertibility (design D9) ─────────────────────────────


def test_nml_store_nml_is_invertible(tmp_path: Path) -> None:
    """collection.nml -> store -> collection.nml keeps hierarchy, order, and PRIMARYKEYs."""
    collection_path = _write_invertible_collection(tmp_path)
    mapping = TraktorPathMapping(_nml_root())
    read = _playlists_from(collection_path, mapping)

    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild(read, source_format="m3u")
        loaded = store.load_playlists()

    assert loaded == read

    NmlExporter(mapping, collection_path, "Migrated").write(loaded)

    after = load_collection(collection_path).nml
    assert _sandbox_folder_names(after, "Migrated") == ["House", "Techno"]
    assert _sandbox_keys(after, "Migrated") == [
        "C:/Music/House/Deep/alpha.mp3",
        "C:/Music/House/Deep/beta.mp3",
        "C:/Music/Techno/gamma.mp3",
    ]


def test_nml_store_m3u_is_invertible(tmp_path: Path) -> None:
    """Store tracks survive the M3U leg unchanged apart from path spelling."""
    from traktor_m3u_sync.formats.m3u.exporter import M3uExporter
    from traktor_m3u_sync.formats.m3u.importer import M3uImporter
    from traktor_m3u_sync.paths.m3u import M3uPathMapping

    collection_path = _write_invertible_collection(tmp_path)
    traktor = TraktorPathMapping(_nml_root())
    read = _playlists_from(collection_path, traktor)

    with PlaylistStore(tmp_path / "store.db") as store:
        store.rebuild(read, source_format="m3u")
        loaded = store.load_playlists()

    out_dir = tmp_path / "m3u"
    out_dir.mkdir()
    M3uExporter(M3uPathMapping(_m3u_root()), out_dir).write(loaded)
    back = M3uImporter(M3uPathMapping(_m3u_root()), out_dir).read()

    assert [(p.folder_path, p.name) for p in back.playlists] == [
        (p.folder_path, p.name) for p in loaded
    ]
    assert [t.path for p in back.playlists for t in p.tracks] == [
        t.path for p in loaded for t in p.tracks
    ]


# ── helpers ─────────────────────────────────────────────────────────────


def _query_track_ids(path: Path) -> list[int]:
    with sqlite3.connect(path) as connection:
        return [row[0] for row in connection.execute("SELECT id FROM tracks")]


def _nml_root() -> PureWindowsPath:
    return PureWindowsPath("C:/Music")


def _m3u_root() -> PurePosixPath:
    return PurePosixPath("../music")


def _playlists_from(collection_path: Path, mapping: TraktorPathMapping) -> tuple[Playlist, ...]:
    """The importer, not the raw reader, is what hands identified tracks to the store."""
    from traktor_m3u_sync.formats.nml.importer import NmlImporter

    return tuple(NmlImporter(mapping, collection_path).read().playlists)


def _sandbox_keys(nml: Nml, sandbox_name: str = "") -> list[str]:
    node = _sandbox_node(nml, sandbox_name)
    if node is None:
        return []
    return _entry_keys(node)


def _sandbox_folder_names(nml: Nml, sandbox_name: str) -> list[str]:
    node = _sandbox_node(nml, sandbox_name)
    assert node is not None and node.subnodes is not None
    return [str(child.name) for child in node.subnodes.node]


def _sandbox_node(nml: Nml, sandbox_name: str) -> Nodetype | None:
    from traktor_m3u_sync.formats.nml.nodes import find_sandbox

    if nml.playlists is None or nml.playlists.node is None:
        return None
    return find_sandbox(nml.playlists.node, sandbox_name)


def _entry_keys(node: Nodetype) -> list[str]:
    if node.playlist is not None:
        return [str(entry.primarykey.key) for entry in node.playlist.entry if entry.primarykey]
    keys: list[str] = []
    if node.subnodes is not None:
        for child in node.subnodes.node:
            keys.extend(_entry_keys(child))
    return keys


def _write_invertible_collection(tmp_path: Path) -> Path:
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
        <NODE TYPE="FOLDER" NAME="House">
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
        <NODE TYPE="FOLDER" NAME="Techno">
          <SUBNODES>
            <NODE TYPE="PLAYLIST" NAME="Peak">
              <PLAYLIST ENTRIES="1" TYPE="LIST">
                <ENTRY>
                  <PRIMARYKEY TYPE="TRACK" KEY="C:/Music/Techno/gamma.mp3"></PRIMARYKEY>
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
