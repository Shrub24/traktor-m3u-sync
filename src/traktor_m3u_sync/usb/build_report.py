"""Per-format outcome of a USB build, for the terminal and for clients."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ..fs import write_atomic
from . import generation

VERSION = 1


@dataclass(frozen=True)
class Outcome:
    format: str
    previous: str | None
    generation: str | None
    error: str | None
    seconds: float

    def summary(self) -> str:
        if self.error is None:
            return (
                f"SUMMARY format={self.format} generation={self.generation} seconds={self.seconds}"
            )
        kept = f"previous {self.previous} kept" if self.previous else "no previous export"
        return f"FAILED format={self.format} seconds={self.seconds} ({kept}) detail={self.error}"


def published_name(output_dir: Path) -> str | None:
    try:
        return generation.current(output_dir).path.name
    except generation.GenerationError:
        return None


def write(path: Path, started: str, finished: str, outcomes: list[Outcome]) -> None:
    failed = sum(o.error is not None for o in outcomes)
    document = {
        "version": VERSION,
        "command": "usb build",
        "started": started,
        "finished": finished,
        "status": "failed" if failed == len(outcomes) else "partial" if failed else "succeeded",
        "formats": [asdict(outcome) for outcome in outcomes],
    }
    write_atomic(path, (json.dumps(document, indent=2) + "\n").encode())
