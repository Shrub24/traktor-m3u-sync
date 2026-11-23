"""Human and JSON views of the same Engine USB review."""

import json
from collections import Counter
from dataclasses import asdict
from itertools import groupby
from pathlib import Path
from typing import cast

import typer

from ..formats.engine.usb import Review
from ..fs import write_atomic
from ..model.performance import Cue, GridMarker, Key, Loop

_LABELS = {"key": "Key", "grid": "Beat grid", "hot_cues": "Hot cue", "loops": "Saved loop"}
_NOTES = ("C", "D♭", "D", "E♭", "E", "F", "F♯", "G", "A♭", "A", "B♭", "B")


def _time(seconds: float) -> str:
    minutes, ms = divmod(round(abs(seconds) * 1000), 60_000)
    return f"{'−' if seconds < 0 else ''}{minutes}:{ms / 1000:06.3f}"


def _value(value: object) -> str:
    match value:
        case Key(tonic, minor):
            return f"{_NOTES[tonic]} {'minor' if minor else 'major'}"
        case Cue(position, label, _):
            return f"{_time(position)} {label}".rstrip()
        case Loop(start, end, label, _):
            return f"{_time(start)}–{_time(end)} {label}".rstrip()
        case tuple() if value:
            grid = cast(tuple[GridMarker, ...], value)
            return (
                "; ".join(
                    f"{60 * (b.beat - a.beat) / (b.position - a.position):.2f} BPM"
                    f" · beat {a.beat} at {_time(a.position)}"
                    for a, b in zip(grid, grid[1:])
                    if b.position > a.position
                )
                or "no tempo"
            )
        case None | ():
            return "unset"
        case _:
            return str(value)


def lines(review: Review, *, full: bool, applied: bool = False, color: bool = False) -> list[str]:
    selected = review.selected
    counts = Counter(change.field for change in selected)
    ignored = len(review.changes) - len(selected)
    action = "applied" if applied else "to approve"
    breakdown = ", ".join(
        f"{counts[field]} {label.lower()}" for field, label in _LABELS.items() if counts[field]
    )
    output = [
        f"{len(selected)} changes {action}"
        + (f" ({breakdown})" if breakdown else "")
        + (f" · {ignored} main cues ignored" if ignored else "")
    ]
    shown = selected if full else selected[:8]
    if shown:
        output.append("Engine → stick")
    for _, group in groupby(shown, key=lambda change: change.ref):
        changes = list(group)
        first = changes[0]
        output.append(
            " – ".join(filter(None, (first.artist, first.title or Path(first.path).name)))
        )
        for change in changes:
            label = _LABELS[change.field]
            if change.slot is not None:
                label += f" {change.slot}"
            before, after = _value(change.current), _value(change.device)
            if color:
                before = typer.style(before, fg=typer.colors.RED)
                after = typer.style(after, fg=typer.colors.GREEN)
            output.append(f"  {label}: {before} → {after}")
    if len(shown) < len(selected):
        output.append(f"… {len(selected) - len(shown)} more; use --diff to show all")
    return output


def show(review: Review, *, full: bool, applied: bool) -> None:
    for line in lines(review, full=full, applied=applied, color=True):
        typer.echo(line)
    if not applied:
        typer.echo(
            f"Approval: {review.approval} · applies all {len(review.selected)} eligible changes"
        )


def write_review(path: Path, review: Review) -> None:
    changes: list[dict[str, object]] = []
    for change in review.changes:
        entry = asdict(change)
        entry["ref"]["database"] = str(change.ref.database)
        entry["selected"] = change.field != "main_cue"
        changes.append(entry)
    report = {
        "version": 1,
        "engine_sha256": review.engine_sha256,
        "stick_sha256": review.stick_sha256,
        "approval": review.approval,
        "changes": changes,
    }
    write_atomic(path, (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode())
