"""Read-only check of whether Engine has saved analysis for the managed playlist tracks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from .writer import SCHEMA_VERSION, EngineWriteError

_MANAGED_TRACKS = """
WITH RECURSIVE managed(id) AS (
  SELECT id FROM Playlist WHERE parentListId = 0 AND title = ?
  UNION
  SELECT p.id FROM Playlist p JOIN managed m ON p.parentListId = m.id
)
SELECT DISTINCT e.trackId,
       t.isAnalyzed IS 1 AND coalesce(length(p.beatData), 0) > 0
FROM PlaylistEntity e
JOIN managed m ON e.listId = m.id
LEFT JOIN Track t ON t.id = e.trackId
LEFT JOIN PerformanceData p ON p.trackId = t.id
WHERE e.databaseUuid = (SELECT uuid FROM Information)
"""


def managed_analysis_saved(
    database_path: Path, managed_root: str, *, busy_timeout: float = 5.0
) -> dict[int, bool]:
    """Map each local track in the managed subtree to whether its analysis is saved.

    Opens the database read-only so it is safe while Engine holds it; a writer holding the
    lock past ``busy_timeout`` raises ``sqlite3.OperationalError`` (SQLITE_BUSY).
    """
    uri = database_path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=busy_timeout) as connection:
        row = connection.execute(
            "SELECT schemaVersionMajor, schemaVersionMinor, schemaVersionPatch FROM Information"
        ).fetchone()
        version = tuple(int(value) for value in row) if row is not None else ()
        if version != SCHEMA_VERSION:
            raise EngineWriteError(f"Engine schema {version!r} is unsupported; expected 3.0.2")
        (roots,) = connection.execute(
            "SELECT COUNT(*) FROM Playlist WHERE parentListId = 0 AND title = ?", (managed_root,)
        ).fetchone()
        if roots != 1:
            raise EngineWriteError(
                f"Expected exactly one top-level playlist named {managed_root!r}, found {roots}"
            )
        return {
            int(track_id): bool(saved)
            for track_id, saved in connection.execute(_MANAGED_TRACKS, (managed_root,))
        }
