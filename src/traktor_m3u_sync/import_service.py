"""Import M3U playlists into a managed sandbox inside Traktor collection.nml."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from traktor_nml_utils import TraktorCollection
from traktor_nml_utils.models.collection import (
    Entrytype,
    Nml,
    Nodetype,
    Playlisttype,
    Primarykeytype,
    Subnodestype,
)

from .collection_matcher import (
    CollectionIndex,
    MatchResult,
    build_collection_index,
    match_track,
)
from .config import AppConfig, ImportConfig, LibraryConfig
from .m3u_reader import ImportedPlaylist, M3uReadError, read_import_tree
from .nml_reader import NmlReadError, load_collection


@dataclass(frozen=True)
class ImportWarning:
    code: str
    message: str
    playlist: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ImportSummary:
    playlists_imported: int
    tracks_matched: int
    tracks_skipped: int
    warnings_emitted: int


@dataclass(frozen=True)
class ImportResult:
    summary: ImportSummary
    warnings: tuple[ImportWarning, ...]


class ImportError(RuntimeError):
    """Raised when the import workflow encounters an unrecoverable failure."""


def run_import(config: AppConfig) -> ImportResult:
    """Execute the full M3U-to-NML sandbox import workflow."""
    import_cfg = config.import_

    imported_playlists = _read_imports(import_cfg)
    collection = _load_collection(import_cfg)
    index = build_collection_index(collection.nml, config.library)

    sandbox_nodes, warnings = _build_sandbox_nodes(
        imported_playlists, index, config.library, import_cfg.sandbox_name
    )

    _rebuild_sandbox_in_nml(collection.nml, sandbox_nodes, import_cfg.sandbox_name)

    backup_path = _backup_and_save(collection, import_cfg.collection_path)

    actual_playlists = _count_playlists_recursive(sandbox_nodes)
    try:
        _validate_save(
            import_cfg.collection_path,
            import_cfg.sandbox_name,
            expected_top_level=len(sandbox_nodes),
            expected_playlists=actual_playlists,
        )
    except ImportError:
        # Validation failed after a successful save — restore the backup
        shutil.copy2(backup_path, import_cfg.collection_path)
        raise

    tracks_matched = sum(_count_all_tracks(node) for node in sandbox_nodes)
    tracks_skipped = sum(1 for w in warnings if w.code == "track_unmatched")

    return ImportResult(
        summary=ImportSummary(
            playlists_imported=actual_playlists,
            tracks_matched=tracks_matched,
            tracks_skipped=tracks_skipped,
            warnings_emitted=len(warnings),
        ),
        warnings=tuple(warnings),
    )


def _read_imports(import_cfg: ImportConfig) -> list[ImportedPlaylist]:
    """Read M3U8 files from the import directory."""
    if import_cfg.import_dir is None:
        msg = "import_dir is required: pass --import-dir or set [import].import_dir"
        raise ImportError(msg)
    try:
        return read_import_tree(import_cfg.import_dir)
    except M3uReadError as exc:
        raise ImportError(f"Failed to read import directory: {exc}") from exc


def _load_collection(import_cfg: ImportConfig) -> TraktorCollection:
    """Load the Traktor collection."""
    if not import_cfg.collection_path.is_file():
        raise ImportError(f"Collection file does not exist: {import_cfg.collection_path}")
    try:
        return load_collection(import_cfg.collection_path)
    except NmlReadError as exc:
        raise ImportError(f"Failed to load collection: {exc}") from exc


def _build_sandbox_nodes(
    imported_playlists: list[ImportedPlaylist],
    index: CollectionIndex,
    library: LibraryConfig,
    sandbox_name: str,
) -> tuple[list[Nodetype], list[ImportWarning]]:
    """Build NML playlist/folder nodes from imported M3U playlists."""
    warnings: list[ImportWarning] = []

    dir_groups: dict[Path, list[tuple[ImportedPlaylist, list[Entrytype]]]] = {}
    for playlist in imported_playlists:
        matched_entries: list[Entrytype] = []
        for track in playlist.tracks:
            result = match_track(track, index, library)
            if result.entry is not None:
                entry = _make_playlist_entry(result)
                matched_entries.append(entry)
            else:
                rel_dir_str = str(playlist.relative_dir)
                playlist_label = (
                    str(playlist.relative_dir / playlist.name)
                    if rel_dir_str != "."
                    else playlist.name
                )
                warnings.append(
                    ImportWarning(
                        code="track_unmatched",
                        message="Track could not be matched to a collection entry",
                        playlist=playlist_label,
                        detail=result.error,
                    )
                )

        dir_groups.setdefault(playlist.relative_dir, []).append((playlist, matched_entries))

    sandbox_nodes: list[Nodetype] = []

    all_flat = all(str(rel_dir) == "." for rel_dir in dir_groups)

    if all_flat:
        for playlist, entries in dir_groups.get(Path("."), []):
            sandbox_nodes.append(_make_playlist_node(playlist.name, entries))
    else:
        top_level: dict[str, list[tuple[Path, ImportedPlaylist, list[Entrytype]]]] = {}
        for rel_dir, playlist_entries in dir_groups.items():
            parts = rel_dir.parts
            if not parts:
                for playlist, entries in playlist_entries:
                    sandbox_nodes.append(_make_playlist_node(playlist.name, entries))
            else:
                top_level.setdefault(parts[0], []).extend(
                    (rel_dir, playlist, entries) for playlist, entries in playlist_entries
                )

        for folder_name, items in sorted(top_level.items()):
            folder_node = _build_folder_node(folder_name, items)
            sandbox_nodes.append(folder_node)

    return sandbox_nodes, warnings


def _make_playlist_node(name: str, entries: list[Entrytype]) -> Nodetype:
    """Create a PLAYLIST Nodetype with the given entries."""
    return Nodetype(
        type="PLAYLIST",
        name=name,
        playlist=Playlisttype(
            entry=entries,
            entries=len(entries),
            type="LIST",
        ),
    )


def _build_folder_node(
    folder_name: str,
    items: list[tuple[Path, ImportedPlaylist, list[Entrytype]]],
) -> Nodetype:
    """Build a nested folder node from a group of playlists sharing a top-level dir."""
    children: list[Nodetype] = []
    sub_items: dict[str, list[tuple[Path, ImportedPlaylist, list[Entrytype]]]] = {}

    for rel_dir, playlist, entries in items:
        parts = rel_dir.parts
        if len(parts) <= 1:
            children.append(_make_playlist_node(playlist.name, entries))
        else:
            sub_key = parts[1]
            sub_items.setdefault(sub_key, []).append((Path(*parts[1:]), playlist, entries))

    for sub_name, sub_group in sorted(sub_items.items()):
        children.append(_build_folder_node(sub_name, sub_group))

    return Nodetype(
        type="FOLDER",
        name=folder_name,
        subnodes=Subnodestype(node=children, count=len(children)),
    )


def _make_playlist_entry(result: MatchResult) -> Entrytype:
    """Create a PRIMARYKEY-only playlist entry referencing a matched collection track."""
    assert result.lookup_key is not None
    return Entrytype(
        primarykey=Primarykeytype(type="TRACK", key=result.lookup_key),
    )


def _rebuild_sandbox_in_nml(
    nml: Nml,
    sandbox_nodes: list[Nodetype],
    sandbox_name: str,
) -> None:
    """Locate or create the sandbox folder under $ROOT and replace its contents."""
    if nml.playlists is None or nml.playlists.node is None:
        raise ImportError("Collection has no PLAYLISTS section")

    root_node = nml.playlists.node
    if root_node.subnodes is None:
        root_node.subnodes = Subnodestype(node=[], count=0)

    root_node.subnodes.node = [
        child
        for child in root_node.subnodes.node
        if not (child.type == "FOLDER" and child.name == sandbox_name)
    ]

    sandbox_folder = Nodetype(
        type="FOLDER",
        name=sandbox_name,
        subnodes=Subnodestype(
            node=sandbox_nodes,
            count=len(sandbox_nodes),
        ),
    )

    root_node.subnodes.node.append(sandbox_folder)
    root_node.subnodes.count = len(root_node.subnodes.node)


def _backup_and_save(collection: TraktorCollection, collection_path: Path) -> Path:
    """Backup the collection file before saving, then save the mutated NML.

    Returns the path to the backup file so callers can restore on validation failure.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = collection_path.with_name(f"{collection_path.stem}.backup.{timestamp}.nml")
    shutil.copy2(collection_path, backup_path)

    try:
        collection.save()
    except Exception as exc:
        raise ImportError(f"Failed to save collection: {exc}") from exc

    return backup_path


def _validate_save(
    collection_path: Path,
    sandbox_name: str,
    *,
    expected_top_level: int,
    expected_playlists: int,
) -> None:
    """Reload the saved NML and verify the sandbox subtree parses correctly.

    Validates:
    - File reloads without parse errors
    - Sandbox folder exists
    - Top-level child count matches expected
    - Recursive playlist count matches expected (catches nested structure issues)
    - Every PLAYLIST node has valid substructure (playlist attribute with entries)
    - Every FOLDER node has a valid subnodes container
    """
    try:
        reloaded = load_collection(collection_path)
    except NmlReadError as exc:
        raise ImportError(f"Post-save reload validation failed: {exc}") from exc

    if reloaded.nml.playlists is None or reloaded.nml.playlists.node is None:
        raise ImportError("Post-save validation: no PLAYLISTS found in reloaded file")

    sandbox = _find_sandbox(reloaded.nml.playlists.node, sandbox_name)
    if sandbox is None:
        raise ImportError(
            f"Post-save validation: sandbox folder '{sandbox_name}' not found after reload"
        )

    actual_top_level = len(sandbox.subnodes.node) if sandbox.subnodes is not None else 0
    if actual_top_level != expected_top_level:
        raise ImportError(
            f"Post-save validation: expected {expected_top_level} "
            f"sandbox children, found {actual_top_level}"
        )

    # Validate recursive structure and count actual playlists
    actual_playlists = _validate_node_structure(sandbox, path=sandbox_name)
    if actual_playlists != expected_playlists:
        raise ImportError(
            f"Post-save validation: expected {expected_playlists} playlists "
            f"in sandbox, found {actual_playlists}"
        )


def _validate_node_structure(node: Nodetype, *, path: str) -> int:
    """Recursively validate a node's structure and return the playlist count.

    Ensures every PLAYLIST has a playlist attribute, every FOLDER has subnodes,
    and no node has an unexpected type. Returns the total number of PLAYLIST
    nodes found in this subtree.
    """
    if node.type == "PLAYLIST":
        if node.playlist is None:
            raise ImportError(
                f"Post-save validation: PLAYLIST node at '{path}' has no playlist data"
            )
        return 1

    if node.type == "FOLDER":
        if node.subnodes is None:
            raise ImportError(f"Post-save validation: FOLDER node at '{path}' has no subnodes")
        total = 0
        for i, child in enumerate(node.subnodes.node):
            child_path = f"{path}/{child.name or f'[index {i}]'}"
            total += _validate_node_structure(child, path=child_path)
        return total

    raise ImportError(f"Post-save validation: unexpected node type '{node.type}' at '{path}'")


def _find_sandbox(node: Nodetype, sandbox_name: str) -> Nodetype | None:
    """Find the sandbox folder node by name under $ROOT."""
    if node.subnodes is None:
        return None
    for child in node.subnodes.node:
        if child.type == "FOLDER" and child.name == sandbox_name:
            return child
    return None


def _count_all_tracks(node: Nodetype) -> int:
    """Count all tracks in a node and its children recursively."""
    if node.type == "PLAYLIST" and node.playlist is not None:
        return len(node.playlist.entry)
    if node.subnodes is not None:
        return sum(_count_all_tracks(child) for child in node.subnodes.node)
    return 0


def _count_playlists_recursive(nodes: list[Nodetype]) -> int:
    """Count the total number of PLAYLIST nodes across the full tree."""
    total = 0
    for node in nodes:
        if node.type == "PLAYLIST":
            total += 1
        elif node.subnodes is not None:
            total += _count_playlists_recursive(node.subnodes.node)
    return total
