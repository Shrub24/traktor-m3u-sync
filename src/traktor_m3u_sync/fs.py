"""Same-directory atomic publication for generated export targets."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def write_atomic(path: Path, data: bytes) -> None:
    """Write data to a sibling temp file and replace path only after success."""
    # ponytail: atomic against process failures; add fsync before replace only
    # if power-loss durability of generated targets ever matters.
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        mode = os.stat(path).st_mode & 0o777
    except FileNotFoundError:
        umask = os.umask(0o022)
        os.umask(umask)
        mode = 0o666 & ~umask
    fd, temp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.chmod(temp_name, mode)
        os.replace(temp_name, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp_name)
        raise
