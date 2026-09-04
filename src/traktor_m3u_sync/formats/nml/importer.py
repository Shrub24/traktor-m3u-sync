"""NML importer: collection.nml to store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...contracts import AdapterWarning, ImportResult
from ...model.identity import identify_playlists
from ...paths.traktor import TraktorPathMapping
from .reader import NmlReadError, load_collection, read_playlists

FORMAT: Final[str] = "nml"


class CollectionReadError(RuntimeError):
    """Raised when the source collection cannot be loaded."""


@dataclass(frozen=True)
class NmlImporter:
    mapping: TraktorPathMapping
    collection_path: Path

    def read(self) -> ImportResult:
        try:
            collection = load_collection(self.collection_path)
        except NmlReadError as exc:
            raise CollectionReadError(f"Collection is missing or unreadable: {exc}") from exc
        extracted = read_playlists(collection.nml, self.mapping)
        playlists, warnings = identify_playlists(extracted.playlists)
        if not playlists:
            warnings = warnings + (
                AdapterWarning(
                    code="empty_import_source",
                    message="Import source is non-empty but stored no playlists",
                    detail=str(self.collection_path),
                ),
            )
        return ImportResult(playlists=playlists, warnings=extracted.warnings + warnings)
