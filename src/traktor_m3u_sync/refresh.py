"""Run the configured refresh units in order and report one outcome."""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, time
from typing import cast

from .config import RefreshConfig
from .fs import write_atomic
from .reporting import utc_now

VERSION = 1


@dataclass(frozen=True)
class Step:
    unit: str
    status: str
    seconds: float
    detail: str | None = None
    report: dict[str, object] | None = None


def run(config: RefreshConfig) -> tuple[str, list[Step]]:
    started = utc_now()
    steps: list[Step] = []
    for unit in config.units:
        if steps and steps[-1].status != "succeeded":
            steps.append(Step(unit, "skipped", 0.0))
            continue
        began, wall = monotonic(), time()
        # A oneshot start returns when the unit finishes; its own conflicts still apply.
        started_unit = subprocess.run(
            ["systemctl", "start", unit], capture_output=True, text=True, check=False
        )
        report = _report(config.reports.get(unit), wall)
        status = "succeeded" if started_unit.returncode == 0 else "failed"
        if report is not None and report.get("status") == "partial":
            status = "partial"
        detail = None if status == "succeeded" else _detail(unit, started_unit.stderr)
        steps.append(Step(unit, status, round(monotonic() - began, 1), detail, report))
    outcome = _outcome(steps)
    if config.report_file is not None:
        document = {
            "version": VERSION,
            "command": "refresh",
            "started": started,
            "finished": utc_now(),
            "status": outcome,
            "steps": [step.__dict__ for step in steps],
        }
        write_atomic(config.report_file, (json.dumps(document, indent=2) + "\n").encode())
    return outcome, steps


def _outcome(steps: list[Step]) -> str:
    statuses = {step.status for step in steps}
    if "failed" in statuses:
        return "failed"
    return "partial" if "partial" in statuses else "succeeded"


def _report(path: Path | None, since: float) -> dict[str, object] | None:
    # A report left by an earlier run would describe the wrong outcome.
    if path is None or not path.is_file() or path.stat().st_mtime < since:
        return None
    return cast(dict[str, object], json.loads(path.read_text()))


def _detail(unit: str, stderr: str) -> str:
    result = subprocess.run(
        ["systemctl", "show", "--property=Result", "--value", unit],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    message = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    return "; ".join(filter(None, (f"result={result}" if result else "", message)))
