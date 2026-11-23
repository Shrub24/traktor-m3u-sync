"""Stage a verified Pioneer export from Engine's performance snapshot."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import cast

from paramiko import SFTPClient

from ..formats.engine.performance import capture
from ..model.performance import Snapshot, dumps, select
from . import generation, sftp
from .generation import Entry, Generation, HashCache

DATABASES = tuple(
    f"PIONEER/rekordbox/{name}" for name in ("exportExt.pdb", "export.pdb", "exportLibrary.db")
)


def inspect(tree: Path) -> dict[tuple[str, ...], tuple[object, ...]]:
    data = _helper("inspect", tree)
    rows = cast(list[tuple[list[str], list[list[object]]]], json.loads(data))
    result: dict[tuple[str, ...], tuple[object, ...]] = {}
    for parts, tracks in rows:
        path = tuple(parts)
        if path in result:
            raise generation.GenerationError(f"Ambiguous Pioneer playlist: {' / '.join(path)}")
        result[path] = tuple(tuple(track) for track in tracks)
    return result


def inspect_stick(
    client: SFTPClient, state: sftp.StickState, tree: Path
) -> dict[tuple[str, ...], tuple[object, ...]]:
    for name in DATABASES[1:]:
        try:
            pulled = sftp.pull(client, state, name)
        except FileNotFoundError:
            continue
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pulled.snapshot, target)
        return inspect(tree)
    return {}


def build(library: Path, output_dir: Path, playlist_root: str | None) -> Generation:
    library = library.resolve(strict=True)
    snapshot = select(capture(library / "Database2/m.db"), playlist_root)
    path = generation.start(output_dir)
    hashes = HashCache(output_dir / "hashes.json")
    try:
        staged = _stage(
            snapshot, library, path, output_dir / "work", output_dir / "waveforms", hashes
        )
        hashes.save()
        return generation.publish(path, staged.files, staged.activation)
    except BaseException:
        shutil.rmtree(path)
        raise


def assemble(snapshot: Snapshot, library: Path, output_dir: Path, path: Path) -> Generation:
    return _stage(
        snapshot,
        library.resolve(strict=True),
        path,
        path / "work",
        output_dir / "waveforms",
        HashCache(output_dir / "hashes.json"),
        prepared=True,
    )


def _stage(
    snapshot: Snapshot,
    library: Path,
    path: Path,
    work: Path,
    cache: Path,
    hashes: HashCache,
    *,
    prepared: bool = False,
) -> Generation:
    snapshot_file = path / "snapshot.json"
    snapshot_file.write_text(dumps(snapshot), encoding="utf-8")
    args = (snapshot_file, library, work, cache)
    _helper(*(("assemble", *args) if prepared else args))
    return Generation(path, _files(work, path / generation.TREE, hashes), DATABASES)


def _helper(*args: str | Path) -> str:
    result = subprocess.run(["pioneer-usb", *args], capture_output=True, text=True, check=False)
    if result.returncode:
        raise generation.GenerationError(result.stderr.strip() or "Pioneer helper failed")
    return result.stdout


def _files(work: Path, tree: Path, hashes: HashCache) -> dict[str, Entry]:
    files: dict[str, Entry] = {}
    for directory in ("Contents", "PIONEER"):
        for source in sorted((work / directory).rglob("*")):
            if not source.is_file():
                continue
            relative = source.relative_to(work)
            if relative.is_relative_to("PIONEER/rbxport"):
                continue
            target = tree / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if directory == "Contents":
                # rbxport replaces staged audio by rename, leaving linked generations intact.
                os.link(source, target)
                digest, size = hashes.sha256(source)
            else:
                shutil.copy2(source, target)
                digest, size = generation.file_sha256(target), target.stat().st_size
            files[relative.as_posix()] = Entry(digest, size)
    if not all(name in files for name in DATABASES):
        raise generation.GenerationError("Pioneer export is missing library files")
    return files
