from __future__ import annotations

from pathlib import Path

from traktor_nml_utils import TraktorCollection


class NmlReadError(RuntimeError):
    """Raised when a collection file cannot be loaded."""


def load_collection(path: Path) -> TraktorCollection:
    expanded_path = path.expanduser()
    try:
        return TraktorCollection(path=expanded_path)
    except Exception as exc:  # pragma: no cover - library error surface
        raise NmlReadError(f"Failed to load Traktor collection: {expanded_path}") from exc
