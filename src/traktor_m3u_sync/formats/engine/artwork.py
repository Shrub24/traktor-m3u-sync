"""Embedded album-art identity as Engine DJ keys it.

Engine's ``AlbumArt.hash`` is the SHA-1 of the first embedded picture's raw bytes, so a
row inserted with that hash links the thumbnail Engine already holds for the same image.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Tags


def embedded_picture_hash(path: Path) -> bytes | None:
    """Return the SHA-1 digest of the file's first embedded picture, or None without one."""
    audio = mutagen.File(path)
    if audio is None:
        return None
    picture = _first_picture(audio)
    return hashlib.sha1(picture).digest() if picture else None


def _first_picture(audio: mutagen.FileType) -> bytes | None:
    if isinstance(audio, FLAC) and audio.pictures:
        return audio.pictures[0].data
    tags = audio.tags
    if isinstance(tags, ID3):
        frames = tags.getall("APIC")
        return frames[0].data if frames else None
    if isinstance(tags, MP4Tags) and "covr" in tags:
        return bytes(tags["covr"][0])
    return None
