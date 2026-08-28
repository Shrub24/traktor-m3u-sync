"""NML exporter: store playlists to a managed sandbox in collection.nml."""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from traktor_nml_utils import TraktorCollection
from traktor_nml_utils.models.collection import Entrytype

from ...contracts import AdapterWarning, SyncResult, playlist_label
from ...model import Playlist
from ...paths.traktor import CollectionIndex, TraktorPathMapping
from .nodes import (
    PlaylistEntry,
    SandboxValidationError,
    count_playlists,
    count_tracks,
    find_sandbox,
    primarykey_entry,
    rebuild_sandbox,
    subtree_playlists,
    validate_node_structure,
)
from .reader import NmlReadError, load_collection

FORMAT: Final[str] = "nml"


class SandboxWriteError(RuntimeError):
    """Raised when the collection cannot be loaded, saved, or validated."""


@dataclass(frozen=True)
class NmlExporter:
    mapping: TraktorPathMapping
    collection_path: Path
    sandbox_name: str

    def write(self, playlists: Sequence[Playlist]) -> SyncResult:
        try:
            collection = load_collection(self.collection_path)
        except NmlReadError as exc:
            raise SandboxWriteError(
                f"Collection file is missing or could not be loaded: {self.collection_path}"
            ) from exc

        index = self.mapping.index_collection(collection.nml)
        entries, warnings, skipped = _match(playlists, index)

        sandbox_nodes = rebuild_sandbox(collection.nml, self.sandbox_name, entries)
        expected_subtree = subtree_playlists(sandbox_nodes, prefix=self.sandbox_name)
        backup_path = _backup_and_save(collection, self.collection_path)

        try:
            _validate_save(self.collection_path, self.sandbox_name, expected_subtree)
        except (SandboxValidationError, NmlReadError) as exc:
            shutil.copy2(backup_path, self.collection_path)
            raise SandboxWriteError(f"Post-save validation failed: {exc}") from exc

        counts = {
            "playlists_written": count_playlists(sandbox_nodes),
            "tracks_matched": sum(count_tracks(node) for node in sandbox_nodes),
            "tracks_skipped": skipped,
            "warnings_emitted": len(warnings),
        }
        return SyncResult(counts=counts, warnings=warnings)


def _match(
    playlists: Sequence[Playlist],
    index: CollectionIndex,
) -> tuple[tuple[PlaylistEntry, ...], tuple[AdapterWarning, ...], int]:
    entries: list[PlaylistEntry] = []
    warnings: list[AdapterWarning] = []
    skipped = 0

    for playlist in playlists:
        matched: list[Entrytype] = []
        for track in playlist.tracks:
            reference = index.lookup(track)
            if reference is None:
                skipped += 1
                ambiguous = (
                    track.identity is not None and track.identity in index.ambiguous_fallbacks
                )
                warnings.append(
                    AdapterWarning(
                        code="ambiguous_fallback_identity" if ambiguous else "track_unmatched",
                        message=(
                            "Track matches multiple collection entries by artist+title; skipped"
                            if ambiguous
                            else "Track could not be matched to a collection entry"
                        ),
                        playlist=playlist_label(playlist.folder_path, playlist.name),
                        detail=track.raw_path or f"{track.artist} - {track.title}",
                    )
                )
                continue
            matched.append(primarykey_entry(reference.primarykey))
        entries.append(PlaylistEntry(playlist.folder_path, playlist.name, tuple(matched)))

    return tuple(entries), tuple(warnings), skipped


def _backup_and_save(collection: TraktorCollection, collection_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = collection_path.with_name(f"{collection_path.stem}.backup.{timestamp}.nml")
    shutil.copy2(collection_path, backup_path)
    try:
        collection.save()
    except Exception as exc:
        raise SandboxWriteError(f"Failed to save collection: {exc}") from exc
    return backup_path


def _validate_save(
    collection_path: Path,
    sandbox_name: str,
    expected_subtree: list[tuple[str, list[str]]],
) -> None:
    """Reload the saved collection and verify the sandbox subtree matches what was built.

    Compares playlist labels and ordered PRIMARYKEYs recursively, so a serializer
    that drops or reorders entries cannot pass validation and skip the restore.
    """
    reloaded = load_collection(collection_path)
    if reloaded.nml.playlists is None or reloaded.nml.playlists.node is None:
        raise SandboxValidationError("no PLAYLISTS found in reloaded file")

    sandbox = find_sandbox(reloaded.nml.playlists.node, sandbox_name)
    if sandbox is None:
        raise SandboxValidationError(f"sandbox folder '{sandbox_name}' not found after reload")

    validate_node_structure(sandbox, path=sandbox_name)
    actual_subtree = subtree_playlists(
        list(sandbox.subnodes.node) if sandbox.subnodes is not None else [],
        prefix=sandbox_name,
    )
    if actual_subtree != expected_subtree:
        expected_tracks = sum(len(keys) for _, keys in expected_subtree)
        actual_tracks = sum(len(keys) for _, keys in actual_subtree)
        raise SandboxValidationError(
            f"sandbox subtree mismatch: expected {len(expected_subtree)} playlists "
            f"with {expected_tracks} tracks, found {len(actual_subtree)} playlists "
            f"with {actual_tracks} tracks"
        )
