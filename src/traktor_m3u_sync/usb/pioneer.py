"""Stage a verified Pioneer export from Engine's performance snapshot."""

import os
import shutil
import subprocess
from pathlib import Path

from ..formats.engine.performance import capture
from ..model.performance import dumps, select
from . import generation
from .generation import Entry, Generation, HashCache

DATABASES = tuple(
    f"PIONEER/rekordbox/{name}" for name in ("exportExt.pdb", "export.pdb", "exportLibrary.db")
)


def build(library: Path, output_dir: Path, playlist_root: str | None) -> Generation:
    library = library.resolve(strict=True)
    snapshot = select(capture(library / "Database2/m.db"), playlist_root)
    path = generation.start(output_dir)
    work = output_dir / "work"
    hashes = HashCache(output_dir / "hashes.json")
    try:
        snapshot_file = path / "snapshot.json"
        snapshot_file.write_text(dumps(snapshot), encoding="utf-8")
        subprocess.run(
            ["pioneer-usb", snapshot_file, library, work, output_dir / "waveforms"], check=True
        )
        snapshot_file.unlink()
        files: dict[str, Entry] = {}
        for directory in ("Contents", "PIONEER"):
            for source in sorted((work / directory).rglob("*")):
                if not source.is_file():
                    continue
                relative = source.relative_to(work)
                if relative.is_relative_to("PIONEER/rbxport"):
                    continue
                target = path / generation.TREE / relative
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
        hashes.save()
        return generation.publish(path, files, DATABASES)
    except BaseException:
        shutil.rmtree(path)
        raise
