"""Adapter contract: importer/exporter protocols, path mapping, shared result types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .model import Playlist


@dataclass(frozen=True)
class AdapterWarning:
    code: str
    message: str
    playlist: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class StoreProvenance:
    """Origin of the store snapshot: importing format and wholesale-rebuild time."""

    source_format: str
    imported_at: str


@dataclass(frozen=True)
class ImportResult:
    playlists: Sequence[Playlist]
    warnings: Sequence[AdapterWarning] = ()


@dataclass(frozen=True)
class SyncResult:
    """Counts and warnings from one adapter or store-mediated run.

    ``provenance`` is only set by store-mediated service runs (import records the
    just-written origin, export reads it back); raw adapters leave it unset.
    """

    counts: Mapping[str, int]
    warnings: Sequence[AdapterWarning] = ()
    provenance: StoreProvenance | None = None


@runtime_checkable
class PathMapping(Protocol):
    """Normalization between a source path spelling and a library-relative path."""

    def to_rel_path(self, raw_path: str) -> str | None:
        """Return the library-relative path, or None when the path is not mappable."""
        ...

    def to_full_path(self, rel_path: str) -> str:
        """Render a library-relative path in the target format's path space."""
        ...


class Importer(Protocol):
    """Read one whole source of playlists into store models."""

    def read(self) -> ImportResult: ...


class Exporter(Protocol):
    """Write store models to one whole target."""

    def write(self, playlists: Sequence[Playlist]) -> SyncResult: ...


def playlist_label(folder_path: Sequence[str], name: str) -> str:
    return "/".join((*folder_path, name))
