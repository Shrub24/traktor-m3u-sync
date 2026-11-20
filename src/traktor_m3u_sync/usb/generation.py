"""Verified USB export generations: a small staged tree plus a manifest of every file.

Large media is not copied into the generation: its manifest entry names the source file,
and delivery reads it from there after checking it is unchanged. A generation is published
by atomically repointing ``current`` once it is complete; the previous one is kept.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast

MANIFEST = "manifest.json"
TREE = "tree"
CURRENT = "current"
_KEEP = 2


class GenerationError(RuntimeError):
    """Raised when a generation is missing, incomplete or inconsistent."""


@dataclass(frozen=True)
class Entry:
    sha256: str
    size: int
    # External media, read at delivery time and stored at a content-addressed path, so it
    # never replaces a file on the stick. None means a library file inside the staged tree,
    # which delivery may replace in place.
    source: Path | None = None


@dataclass(frozen=True)
class Generation:
    path: Path
    files: Mapping[str, Entry]
    # Published last, after every other file is present on the stick.
    activation: str

    @property
    def tree(self) -> Path:
        return self.path / TREE

    def local(self, name: str) -> Path:
        entry = self.files[name]
        if entry.source is None:
            return self.tree / name
        stat = entry.source.stat()
        if stat.st_size != entry.size:
            raise GenerationError(f"Source changed since the build; rebuild: {entry.source}")
        return entry.source


def file_sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class HashCache:
    """SHA-256 of external media, reused while a file's size and mtime are unchanged."""

    def __init__(self, path: Path) -> None:
        self._path = path
        raw: dict[str, Any] = json.loads(path.read_text()) if path.is_file() else {}
        self._entries = {name: tuple(value) for name, value in raw.items()}
        self._used: dict[str, tuple[int, int, str]] = {}

    def sha256(self, path: Path) -> tuple[str, int]:
        stat = path.stat()
        key = str(path)
        cached = self._entries.get(key)
        if cached is not None and cached[:2] == (stat.st_size, stat.st_mtime_ns):
            digest = str(cached[2])
        else:
            digest = file_sha256(path)
        self._used[key] = (stat.st_size, stat.st_mtime_ns, digest)
        return digest, stat.st_size

    def save(self) -> None:
        _write_json(self._path, self._used)


def start(output_dir: Path) -> Path:
    """Create an empty generation directory; nothing points at it until :func:`publish`."""
    generations = output_dir / "generations"
    generations.mkdir(parents=True, exist_ok=True)
    name = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = generations / name
    (path / TREE).mkdir(parents=True)
    return path


def publish(path: Path, files: Mapping[str, Entry], activation: str) -> Generation:
    tree = path / TREE
    names = {name.casefold() for name in files}
    if len(names) != len(files):
        raise GenerationError("Case-insensitive path collision in the generation")
    for name, entry in files.items():
        if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts:
            raise GenerationError(f"Unsafe generation path: {name}")
        if entry.source is None and file_sha256(tree / name) != entry.sha256:
            raise GenerationError(f"Staged file does not match its manifest: {name}")
    if activation not in files:
        raise GenerationError(f"Generation is missing its activation file {activation}")
    _write_json(
        path / MANIFEST,
        {
            "activation": activation,
            "files": {
                name: {
                    "sha256": entry.sha256,
                    "size": entry.size,
                    "source": None if entry.source is None else str(entry.source),
                }
                for name, entry in sorted(files.items())
            },
        },
    )
    output_dir = path.parent.parent
    link = output_dir / f".{CURRENT}.tmp"
    link.unlink(missing_ok=True)
    link.symlink_to(Path("generations") / path.name)
    link.replace(output_dir / CURRENT)
    _prune(path.parent, keep=path.name)
    return Generation(path, dict(files), activation)


def current(output_dir: Path) -> Generation:
    path = (output_dir / CURRENT).resolve()
    manifest = path / MANIFEST
    if not manifest.is_file():
        raise GenerationError(f"No published USB generation in {output_dir}; run a build first")
    raw = cast(dict[str, Any], json.loads(manifest.read_text()))
    files = {
        name: Entry(
            sha256=str(value["sha256"]),
            size=int(value["size"]),
            source=None if value["source"] is None else Path(value["source"]),
        )
        for name, value in cast(dict[str, dict[str, Any]], raw["files"]).items()
    }
    return Generation(path, files, str(raw["activation"]))


def _prune(generations: Path, *, keep: str) -> None:
    published = sorted(p for p in generations.iterdir() if (p / MANIFEST).is_file())
    stale = [p for p in published if p.name != keep][: max(0, len(published) - _KEEP)]
    unpublished = [p for p in generations.iterdir() if not (p / MANIFEST).is_file()]
    for path in (*stale, *(p for p in unpublished if p.name != keep)):
        shutil.rmtree(path)


def _write_json(path: Path, data: object) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(data, sort_keys=True))
    os.replace(temp, path)
