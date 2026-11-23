"""Interactive frontend to the stick manager."""

import curses
import sqlite3
from dataclasses import dataclass

from paramiko import SSHException

from ..formats.engine.performance import EnginePerformanceError
from ..formats.engine.usb import EngineUsbError
from ..formats.engine.writer import EngineWriteError
from . import review_report
from .generation import GenerationError
from .manager import Manager, PlaylistPath, Playlists, marker
from .sftp import DeliveryError, PushResult

_OPERATION_ERRORS = (
    DeliveryError,
    EnginePerformanceError,
    EngineUsbError,
    EngineWriteError,
    GenerationError,
    OSError,
    sqlite3.Error,
    SSHException,
)

_LABEL = {"engine": "Engine DJ", "pioneer": "rekordbox"}


@dataclass
class Selection:
    local: Playlists
    remote: Playlists
    desired: set[PlaylistPath]


def _draw(screen: curses.window, lines: list[str], footer: str, row: int = 0) -> int:
    height, width = screen.getmaxyx()
    screen.erase()
    count = max(1, height - 2)
    for index, line in enumerate(lines[:count]):
        screen.addnstr(index, 0, line, width - 1, curses.A_REVERSE if index == row else 0)
    if height > 1:
        screen.addnstr(height - 1, 0, footer, width - 1)
    screen.refresh()
    return count


def _confirm(
    screen: curses.window, heading: str, lines: list[str], *, approve: bool = True
) -> bool:
    start = 0
    footer = "↑/↓ Scroll · y Confirm · Esc Cancel" if approve else "↑/↓ Scroll · Enter Close"
    while True:
        size = _draw(screen, [heading, *lines[start:]], footer)
        key = screen.getch()
        if key == curses.KEY_DOWN and start < len(lines) - size + 1:
            start += 1
        elif key == curses.KEY_UP:
            start = max(0, start - 1)
        elif approve and key == ord("y"):
            return True
        elif key in (27, ord("q"), ord("n"), 10):
            return False


def _preview(
    screen: curses.window, name: str, selection: Selection, plan: PushResult, reviewed: str | None
) -> bool:
    lines = [
        f"{len(plan.files)} files · {plan.bytes:,} bytes",
        f"Audio: {plan.audio_reused} reused · {plan.audio_missing} missing"
        f" · {plan.audio_changed} changed"
        if name == "engine"
        else "Includes rekordbox library and any changed assets",
    ]
    if name == "engine" and any(path.endswith("/m.db") for path in plan.files):
        lines.append("Publishes the Engine library database after assets.")
    if name == "pioneer" and any(path.startswith("PIONEER/rekordbox/") for path in plan.files):
        lines.append("Publishes the rekordbox databases after assets; retry if interrupted.")
    if reviewed is not None:
        lines += [
            "Replaces an unrecognized Engine database and its player edits.",
            f"Database SHA-256: {reviewed}",
        ]
    for path in sorted(selection.local.keys() | selection.remote.keys()):
        action = marker(path, selection.desired, selection.local, selection.remote)
        if action != " ":
            lines.append(f"{action} {' / '.join(path)}")
    return _confirm(screen, f"Export {_LABEL[name]} →", lines)


def run(manager: Manager) -> None:
    curses.wrapper(_run, manager)


def _run(screen: curses.window, manager: Manager) -> None:
    formats = manager.settings.formats
    selections: dict[str, Selection] = {}
    tab = cursor = 0
    message = ""

    def load(name: str) -> Selection:
        if name not in selections:
            _draw(screen, [f"Reading {_LABEL[name]} libraries…"], "")
            local, remote = manager.inspect(name)
            selections[name] = Selection(local, remote, set(local.keys() & remote.keys()))
        return selections[name]

    while True:
        name = formats[tab]
        selection = load(name)
        paths = sorted(selection.local.keys() | selection.remote.keys())
        rows: list[tuple[PlaylistPath, str]] = []
        folders: set[PlaylistPath] = set()
        for path in paths:
            for depth in range(1, len(path)):
                parent = path[:depth]
                if parent not in folders:
                    folders.add(parent)
                    rows.append(((), f"{'  ' * (depth - 1)}▾ {parent[-1]}"))
            action = marker(path, selection.desired, selection.local, selection.remote)
            check = "x" if path in selection.desired else " "
            rows.append((path, f"{'  ' * (len(path) - 1)}[{check}] {action} {path[-1]}"))
        cursor = min(cursor, max(0, len(rows) - 1))
        offset = max(0, cursor - max(0, screen.getmaxyx()[0] - 5))
        _draw(
            screen,
            [
                f"Sync Manager · {_LABEL[name]} · {manager.root}",
                message,
                *(label for _, label in rows[offset:]),
            ],
            "↑/↓ Move · Space Select · Tab Format · ← Import · → Export · b Both · q Quit",
            cursor - offset + 2,
        )
        key = screen.getch()
        if key in (27, ord("q")):
            return
        if key == 9:
            tab, cursor = (tab + 1) % len(formats), 0
        elif key == curses.KEY_DOWN:
            cursor = min(cursor + 1, max(0, len(rows) - 1))
        elif key == curses.KEY_UP:
            cursor = max(0, cursor - 1)
        elif key == ord(" ") and rows and rows[cursor][0] in selection.local:
            selection.desired.symmetric_difference_update({rows[cursor][0]})
        elif key == curses.KEY_LEFT and name == "engine":
            _draw(screen, ["Reading Engine player edits…"], "")

            def review(changes: review_report.Review) -> bool:
                return _confirm(
                    screen, "← Import player edits", review_report.lines(changes, full=True)
                )

            try:
                imported = manager.review(review)
            except _OPERATION_ERRORS as exc:
                _confirm(screen, "Import stopped", [str(exc)], approve=False)
            else:
                message = (
                    "Imported. Refresh exports before delivering the updated library."
                    if imported
                    else "No edits imported."
                )
        elif key in (curses.KEY_RIGHT, ord("b")):
            for chosen in formats if key == ord("b") else (name,):
                choices = load(chosen)
                _draw(screen, [f"Preparing {_LABEL[chosen]} transfer preview…"], "")

                def confirm(plan: PushResult, reviewed: str | None) -> bool:
                    approved = _preview(screen, chosen, choices, plan, reviewed)
                    if approved:
                        _draw(screen, [f"Delivering {_LABEL[chosen]}…"], "")
                    return approved

                def progress(stage: str, sent: int, size: int) -> None:
                    _draw(screen, [f"{stage} · {_LABEL[chosen]}", f"{sent:,} / {size:,} bytes"], "")

                try:
                    result = manager.export(
                        chosen, choices.desired, (choices.local, choices.remote), confirm, progress
                    )
                except _OPERATION_ERRORS as exc:
                    _confirm(screen, f"{_LABEL[chosen]} export stopped", [str(exc)], approve=False)
                    break
                if result.applied:
                    del selections[chosen]
                    message = f"{_LABEL[chosen]} delivered."
                elif result.files:
                    message = "Delivery cancelled."
                    break
                else:
                    message = "No files to transfer."
