"""Track metadata and artwork read from audio files the way Engine DJ's own import does.

Engine joins multi-valued tags with a single space, keys ``AlbumArt.hash`` by the SHA-1 of
the first embedded picture's raw bytes, and caches each picture as a 256-pixel JPEG under
``<Engine Library>/Artwork/<unpadded base64url(hash)>.jpg``.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import mutagen
from mutagen.flac import FLAC
from mutagen.id3 import ID3
from mutagen.mp4 import MP4Tags
from PIL import Image

# Engine Track column -> (ID3 frame, Vorbis comment keys in priority order, MP4 atom).
_COLUMNS: Final[dict[str, tuple[str, tuple[str, ...], str | None]]] = {
    "title": ("TIT2", ("title",), "\xa9nam"),
    "artist": ("TPE1", ("artist",), "\xa9ART"),
    "album": ("TALB", ("album",), "\xa9alb"),
    "genre": ("TCON", ("genre",), "\xa9gen"),
    "composer": ("TCOM", ("composer",), "\xa9wrt"),
    "remixer": ("TPE4", ("remixer",), None),
    "label": ("TPUB", ("label", "organization", "publisher"), None),
    "comment": ("COMM", ("comment", "description"), "\xa9cmt"),
    "year": ("TDRC", ("date", "year"), "\xa9day"),
}
_THUMBNAIL_SIZE: Final = (256, 256)
_THUMBNAIL_QUALITY: Final = 25


@dataclass(frozen=True)
class Media:
    columns: dict[str, str | int]
    picture: bytes | None


def read_media(path: Path) -> Media | None:
    """Return the Engine Track columns and first embedded picture, or None if unreadable."""
    try:
        audio = mutagen.File(path)
    except mutagen.MutagenError:
        return None
    if audio is None:
        return None
    tags = audio.tags
    picture: bytes | None = None
    if isinstance(tags, ID3):
        values = {column: _id3_values(tags, frame) for column, (frame, _, _) in _COLUMNS.items()}
        pictures = tags.getall("APIC")
        picture = pictures[0].data if pictures else None
    elif isinstance(tags, MP4Tags):
        values = {
            column: _list(tags.get(atom)) for column, (_, _, atom) in _COLUMNS.items() if atom
        }
        covers = tags.get("covr")
        picture = bytes(covers[0]) if covers else None
    elif tags is not None:
        values = {column: _vorbis_values(tags, keys) for column, (_, keys, _) in _COLUMNS.items()}
    else:
        values = {}
    if isinstance(audio, FLAC) and audio.pictures:
        picture = audio.pictures[0].data

    columns: dict[str, str | int] = {}
    for column, raw in values.items():
        text = " ".join(value for value in raw if value)
        if column == "year":
            if text[:4].isdigit() and int(text[:4]):
                columns[column] = int(text[:4])
        elif text:
            columns[column] = text
    bitrate = getattr(audio.info, "bitrate", 0)
    if bitrate:
        columns["bitrate"] = round(bitrate / 1000)
    return Media(columns, picture)


def render_thumbnail(picture: bytes) -> bytes:
    """Render Engine's artwork-cache thumbnail: fit within 256x256, never upscaled."""
    with Image.open(io.BytesIO(picture)) as image:
        image.thumbnail(_THUMBNAIL_SIZE)
        output = io.BytesIO()
        image.convert("L" if image.mode == "L" else "RGB").save(
            output, "JPEG", quality=_THUMBNAIL_QUALITY
        )
    return output.getvalue()


def thumbnail_name(digest: bytes) -> str:
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode() + ".jpg"


def _id3_values(tags: ID3, frame: str) -> list[str]:
    frames = tags.getall(frame)
    if not frames:
        return []
    if frame == "COMM":
        # Engine reads the plain comment, not iTunes' described COMM frames.
        chosen = next((comment for comment in frames if not comment.desc), frames[0])
        return [str(text) for text in chosen.text]
    if frame == "TCON":
        return list(frames[0].genres)
    return [str(text) for text in frames[0].text]


def _vorbis_values(tags: Any, keys: tuple[str, ...]) -> list[str]:
    for key in keys:
        values = _list(tags.get(key))
        if any(values):
            return values
    return []


def _list(value: list[Any] | None) -> list[str]:
    return [str(item) for item in value or []]
