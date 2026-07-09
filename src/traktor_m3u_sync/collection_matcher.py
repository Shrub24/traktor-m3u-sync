"""Resolve imported M3U tracks back to existing Traktor collection entries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from traktor_nml_utils.models.collection import Entrytype, Nml

from .config import LibraryConfig
from .pathmap import (
    ReversePathTranslationError,
    normalize_for_collection_lookup,
    reverse_translate_track_path,
)

if TYPE_CHECKING:
    from .m3u_reader import ImportedTrack


@dataclass(frozen=True)
class CollectionIndex:
    """Prebuilt lookup for matching imported tracks to collection entries."""

    by_primarykey: dict[str, Entrytype]
    by_location: dict[str, Entrytype]


@dataclass(frozen=True)
class MatchResult:
    """Result of matching an imported track against the collection."""

    entry: Entrytype | None
    lookup_key: str | None = None
    error: str | None = None


def build_collection_index(nml: Nml, library: LibraryConfig) -> CollectionIndex:
    """Build a lookup index from existing collection entries.

    The index is keyed by normalized PRIMARYKEY, with a secondary index
    on reconstructed LOCATION paths for fallback matching.
    """
    by_primarykey: dict[str, Entrytype] = {}
    by_location: dict[str, Entrytype] = {}

    if nml.collection is None:
        return CollectionIndex(by_primarykey=by_primarykey, by_location=by_location)

    for entry in nml.collection.entry:
        if entry.primarykey is not None and entry.primarykey.key:
            normalized = _normalize_entry_primarykey(entry.primarykey.key)
            if normalized not in by_primarykey:
                by_primarykey[normalized] = entry

        loc = _reconstruct_entry_location(entry, library)
        if loc is not None and loc not in by_location:
            by_location[loc] = entry

    return CollectionIndex(by_primarykey=by_primarykey, by_location=by_location)


def match_track(
    track: ImportedTrack,
    index: CollectionIndex,
    library: LibraryConfig,
) -> MatchResult:
    """Match an imported track to a collection entry."""
    try:
        traktor_path = reverse_translate_track_path(track.path, library)
    except ReversePathTranslationError as exc:
        return MatchResult(entry=None, error=str(exc))

    lookup_key = normalize_for_collection_lookup(traktor_path)

    matched = index.by_primarykey.get(lookup_key)
    if matched is not None:
        return MatchResult(entry=matched, lookup_key=lookup_key)

    # Fallback: try reconstructed LOCATION keys
    matched = index.by_location.get(lookup_key)
    if matched is not None:
        return MatchResult(entry=matched, lookup_key=lookup_key)

    return MatchResult(entry=None, lookup_key=lookup_key, error="not_in_collection")


def _normalize_entry_primarykey(value: str) -> str:
    """Normalize a PRIMARYKEY value for index insertion."""
    return value.replace("\\", "/")


def _reconstruct_entry_location(entry: Entrytype, library: LibraryConfig) -> str | None:
    """Reconstruct a normalized location path from an entry's LOCATION fields."""
    if entry.location is None:
        return None
    loc = entry.location
    if not loc.dir or not loc.file:
        return None

    dir_str = loc.dir
    normalized_dir = dir_str.replace("/:", "/")
    if normalized_dir.startswith(":/"):
        normalized_dir = normalized_dir[2:]

    parts = [p for p in normalized_dir.split("/") if p]
    volume = loc.volume or ""
    if volume:
        volume_prefix = volume.rstrip("\\") + "/"
    else:
        volume_prefix = ""
    return volume_prefix + "/".join(parts) + "/" + loc.file
