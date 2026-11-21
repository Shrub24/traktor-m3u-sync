"""Prepare Hot Cue A once, from Engine's saved downbeat."""

import math
import sqlite3
from collections.abc import Collection
from contextlib import closing
from dataclasses import replace
from pathlib import Path

from .analysis import managed_analysis_saved
from .performance import BeatData, QuickCue, decode_beat_data, decode_quick_cues, encode_quick_cues
from .writer import preflight_target, publish


def _first_downbeat(grid: BeatData) -> float:
    if grid.grid_set:
        for a, b in zip(grid.adjusted_grid, grid.adjusted_grid[1:]):
            if b.sample <= a.sample or b.beat <= a.beat:
                continue
            interval = (b.sample - a.sample) / (b.beat - a.beat)
            first = a.beat + max(0, math.ceil(-a.sample / interval))
            downbeat = first + (-first % 4)
            sample = a.sample + (downbeat - a.beat) * interval
            if downbeat <= b.beat and 0 <= sample < grid.samples:
                return round(sample)
    return 0.0


def _pending(db: sqlite3.Connection, ids: set[int]) -> list[tuple[int, str, float, bytes]]:
    changes: list[tuple[int, str, float, bytes]] = []
    for track_id, path, beat, blob in db.execute(
        "SELECT t.id, t.path, p.beatData, p.quickCues FROM Track t "
        "JOIN PerformanceData p ON p.trackId = t.id WHERE t.isAnalyzed = 1 ORDER BY t.id"
    ):
        if track_id not in ids or blob is None:
            continue
        cues = decode_quick_cues(blob)
        if cues.cues[0].sample >= 0:
            continue
        grid = decode_beat_data(beat)
        sample = _first_downbeat(grid)
        slot = QuickCue("", sample, (255, 255, 0, 0))
        updated = replace(cues, cues=(slot, *cues.cues[1:]))
        changes.append(
            (int(track_id), str(path), sample / grid.sample_rate, encode_quick_cues(updated))
        )
    return changes


def prepare(
    database: Path, root: str, track_ids: Collection[int], *, apply: bool
) -> list[tuple[str, float]]:
    preflight_target(database)
    ids = {i for i, saved in managed_analysis_saved(database, root).items() if saved}
    if track_ids:
        ids.intersection_update(track_ids)
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        changes = _pending(db, ids)
    if apply and changes:

        def edit(db: sqlite3.Connection) -> None:
            db.executemany(
                "UPDATE PerformanceData SET quickCues = ? WHERE trackId = ?",
                ((blob, track_id) for track_id, _, _, blob in _pending(db, ids)),
            )

        publish(database, edit)
    return [(path, seconds) for _, path, seconds, _ in changes]


def project_main_cues(db: sqlite3.Connection) -> None:
    updates: list[tuple[bytes, int]] = []
    for track_id, blob in db.execute("SELECT trackId, quickCues FROM PerformanceData"):
        if blob is None:
            continue
        cues = decode_quick_cues(blob)
        if (sample := cues.cues[0].sample) >= 0:
            updates.append(
                (
                    encode_quick_cues(
                        replace(cues, adjusted_main_cue=sample, main_cue_adjusted=True)
                    ),
                    track_id,
                )
            )
    db.executemany("UPDATE PerformanceData SET quickCues = ? WHERE trackId = ?", updates)
