"""Focused tests for file-mode handling in the atomic publication helper."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from traktor_m3u_sync.fs import write_atomic


def test_replacement_preserves_existing_target_mode(tmp_path: Path) -> None:
    target = tmp_path / "Library.xml"
    target.write_bytes(b"stale")
    os.chmod(target, 0o640)

    write_atomic(target, b"fresh")

    assert target.read_bytes() == b"fresh"
    assert stat.S_IMODE(target.stat().st_mode) == 0o640


def test_new_target_gets_umask_derived_mode_not_owner_only(tmp_path: Path) -> None:
    original_umask = os.umask(0o027)
    try:
        write_atomic(tmp_path / "playlist.m3u8", b"#EXTM3U\n")
    finally:
        os.umask(original_umask)

    assert stat.S_IMODE((tmp_path / "playlist.m3u8").stat().st_mode) == 0o640
