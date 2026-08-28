"""Traktor path space: VOLUME/DIR/FILE/PRIMARYKEY spellings to library-relative."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import PurePosixPath, PureWindowsPath

from traktor_nml_utils.models.collection import Entrytype, Nml

from ..config import LibraryConfig
from ..model import Track
from ..model.identity import fallback_identity, normalize_identity


class PathTranslationError(ValueError):
    """Raised when a Traktor path cannot be translated into library space."""


@dataclass(frozen=True)
class CollectionReference:
    """A collection entry plus the canonical PRIMARYKEY value for it."""

    entry: Entrytype
    primarykey: str


@dataclass(frozen=True)
class CollectionIndex:
    by_path: dict[str, CollectionReference] = field(default_factory=lambda: {})
    by_fallback: dict[str, CollectionReference] = field(default_factory=lambda: {})
    ambiguous_fallbacks: frozenset[str] = frozenset()

    def lookup(self, track: Track) -> CollectionReference | None:
        if track.identity is None:
            return None
        if track.path is not None:
            return self.by_path.get(track.identity)
        if track.identity in self.ambiguous_fallbacks:
            return None
        return self.by_fallback.get(track.identity)


@dataclass(frozen=True)
class TraktorPathMapping:
    library: LibraryConfig

    def to_rel_path(self, raw_path: str) -> str:
        """Translate a Traktor path spelling into a library-relative POSIX path."""
        source = PureWindowsPath(raw_path.replace("/", "\\"))
        try:
            relative = source.relative_to(self.library.traktor_root)
        except ValueError as exc:
            raise PathTranslationError(
                f"Track path '{source}' is outside configured "
                f"Traktor root '{self.library.traktor_root}'"
            ) from exc
        return relative.as_posix()

    def to_full_path(self, rel_path: str) -> str:
        """Render a library-relative path as a canonical PRIMARYKEY value."""
        rendered = str(self.library.traktor_root.joinpath(*PurePosixPath(rel_path).parts))
        return rendered.replace("\\", "/")

    def render_for_m3u(self, rel_path: str) -> str:
        """Render a library-relative path in M3U space."""
        return self.library.m3u_root.joinpath(*PurePosixPath(rel_path).parts).as_posix()

    def entry_path(self, entry: Entrytype) -> str:
        """Select the path spelling of a Traktor entry (PRIMARYKEY wins)."""
        if entry.primarykey is not None and entry.primarykey.key:
            return entry.primarykey.key
        location = entry.location
        if location is not None and location.volume and location.dir and location.file:
            return _reconstruct_location(
                volume=location.volume,
                directory=location.dir,
                file_name=location.file,
            )
        raise PathTranslationError("Track is missing both PRIMARYKEY and LOCATION path data")

    def index_collection(self, nml: Nml) -> CollectionIndex:
        """Index collection entries by path identity and by artist+title fallback.

        Fallback identities claimed by more than one collection path are recorded
        as ambiguous so lookups refuse to guess a reference for them.
        """
        index = CollectionIndex()
        if nml.collection is None:
            return index
        fallback_paths: dict[str, set[str]] = {}
        for entry in nml.collection.entry:
            try:
                rel_path = self.to_rel_path(self.entry_path(entry))
            except PathTranslationError:
                continue
            reference = CollectionReference(entry=entry, primarykey=self.to_full_path(rel_path))
            index.by_path.setdefault(normalize_identity(rel_path), reference)
            if entry.title and entry.artist:
                identity = fallback_identity(entry.title, entry.artist)
                index.by_fallback.setdefault(identity, reference)
                fallback_paths.setdefault(identity, set()).add(reference.primarykey)
        ambiguous = frozenset(i for i, keys in fallback_paths.items() if len(keys) > 1)
        return replace(index, ambiguous_fallbacks=ambiguous)


def _reconstruct_location(*, volume: str, directory: str, file_name: str) -> str:
    normalized_directory = directory.replace("/:", "/")
    if normalized_directory.startswith(":/"):
        normalized_directory = normalized_directory[2:]
    parts = [part for part in normalized_directory.split("/") if part]
    return PureWindowsPath(f"{volume}\\").joinpath(*parts, file_name).as_posix()
