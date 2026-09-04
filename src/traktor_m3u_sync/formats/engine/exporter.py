"""Engine DJ exporter adapter: shared SyncResult over the direct-SQLite writer."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...contracts import SyncResult
from ...model import Playlist
from .writer import WriteOutcome, write_database

FORMAT: Final[str] = "engine"


@dataclass(frozen=True)
class EngineExporter:
    database_path: Path
    track_path_prefix: str = ".."
    managed_root: str = "Playlist Sync"
    # Optional worker-side mount; used only for file_missing warnings, never for matching.
    check_base_path: Path | None = None

    def write(self, playlists: Sequence[Playlist]) -> SyncResult:
        outcome = write_database(
            self.database_path,
            playlists,
            managed_root=self.managed_root,
            track_path_prefix=self.track_path_prefix,
            check_base_path=self.check_base_path,
        )
        return _result(outcome)


def _result(outcome: WriteOutcome) -> SyncResult:
    counts = {
        "playlists_written": outcome.playlists_written,
        "tracks_matched": outcome.tracks_matched,
        "memberships_written": outcome.memberships_written,
        "memberships_skipped": (
            outcome.skipped_unresolved
            + outcome.skipped_missing
            + outcome.skipped_ambiguous
            + outcome.skipped_duplicate
        ),
        "skipped_unresolved": outcome.skipped_unresolved,
        "skipped_missing": outcome.skipped_missing,
        "skipped_ambiguous": outcome.skipped_ambiguous,
        "skipped_duplicate": outcome.skipped_duplicate,
        "warnings_emitted": len(outcome.warnings),
    }
    return SyncResult(counts=counts, warnings=outcome.warnings)
