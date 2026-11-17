"""Create a USB export job from selected tracks in an Engine 3.0.2 snapshot."""

import argparse
import base64
import json
import math
import sqlite3
import struct
import zlib
from pathlib import Path
from typing import Any


def unpack_blob(blob: bytes) -> bytes:
    data = zlib.decompress(blob[4:])
    if len(data) != int.from_bytes(blob[:4], "big"):
        raise ValueError("Engine blob length mismatch")
    return data


def adjusted_grid(blob: bytes) -> tuple[float, int, list[tuple[int, int, int]]]:
    data = unpack_blob(blob)
    rate, samples, enabled = struct.unpack_from(">ddB", data)
    default_count = struct.unpack_from(">Q", data, 17)[0]
    offset = 25 + 24 * default_count
    count = struct.unpack_from(">Q", data, offset)[0]
    if not enabled or count != 2 or len(data) != offset + 8 + 24 * count + 9:
        raise ValueError("Spike requires a two-marker adjusted Engine grid")
    start, index, _, _ = struct.unpack_from("<dqII", data, offset + 8)
    end, last, _, _ = struct.unpack_from("<dqII", data, offset + 32)
    if not (rate > 0 and samples > 0 and end > start and last > index):
        raise ValueError("Invalid Engine grid")
    step = (end - start) / (last - index)
    bpm = round(6000 * rate / step)
    if not 0 < bpm <= 65535:
        raise ValueError("Grid tempo is outside Pioneer range")
    # Beat index zero is assumed to be beat one of a bar; confirm on hardware.
    beats = [
        ((index + i) % 4 + 1, bpm, round((start + i * step) * 1000 / rate))
        for i in range(math.ceil(-start / step), math.ceil((samples - start) / step))
    ]
    return rate, bpm, beats


def cue(
    kind: int, start: float, rate: float, label: str, end: float | None = None
) -> dict[str, Any]:
    return {
        "kind": kind,
        "time_ms": round(start * 1000 / rate),
        "loop_time_ms": None if end is None else round(end * 1000 / rate),
        "comment": label,
    }


def cues(hot: bytes, loops: bytes, rate: float) -> list[dict[str, Any]]:
    result = []
    data = unpack_blob(hot)
    count = struct.unpack_from(">Q", data)[0]
    if count != 8 or loops[0] != 8:
        raise ValueError("Unexpected Engine cue or loop slot count")
    offset = 8
    for slot in range(1, count + 1):
        size = data[offset]
        offset += 1
        label = data[offset : offset + size].decode()
        offset += size
        start = struct.unpack_from(">d", data, offset)[0]
        offset += 12
        if start >= 0:
            result.append(cue(slot if slot <= 3 else slot + 1, start, rate, label))
    main, overridden, _ = struct.unpack_from(">dBd", data, offset)
    if main >= 0 and overridden:
        result.append(cue(0, main, rate, "Main cue"))
    offset = 8
    for _ in range(loops[0]):
        size = loops[offset]
        offset += 1
        label = loops[offset : offset + size].decode()
        offset += size
        start, end, start_set, end_set = struct.unpack_from("<ddBB", loops, offset)
        offset += 22
        if start_set and end_set and 0 <= start < end:
            result.append(cue(0, start, rate, label, end))
    return result


def read_track(db: sqlite3.Connection, library: Path, track_id: int) -> dict[str, Any]:
    row = db.execute(
        "SELECT t.path, t.title, t.artist, t.album, t.key, "
        "p.beatData, p.quickCues, p.loops, a.hash "
        "FROM Track t JOIN PerformanceData p ON p.trackId = t.id "
        "LEFT JOIN AlbumArt a ON a.id = t.albumArtId WHERE t.id = ? AND t.isAnalyzed = 1",
        (track_id,),
    ).fetchone()
    if row is None or row[5] is None:
        raise ValueError(f"Engine track {track_id} has no analysis")
    path, title, artist, album, key, grid, hot, loops, art = row
    source = (library / path.replace("\\", "/")).resolve(strict=True)
    rate, bpm, beats = adjusted_grid(grid)
    artwork = None
    if art is not None:
        name = base64.urlsafe_b64encode(art).rstrip(b"=").decode() + ".jpg"
        candidate = library / "Artwork" / name
        if candidate.is_file():
            artwork = str(candidate)
    return {
        "id": track_id,
        "source_path": str(source),
        "title": title or source.stem,
        "artist": artist or "",
        "album": album or "",
        "key": f"{(key // 2 + 7) % 12 + 1}{'B' if key % 2 == 0 else 'A'}"
        if key is not None and 0 <= key < 24
        else "",
        "bpm_x100": bpm,
        "beats": beats,
        "cues": cues(hot, loops, rate),
        "artwork": artwork,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "database", type=Path, help="copy of Engine m.db made while Engine was closed"
    )
    parser.add_argument(
        "library", type=Path, help="original Engine Library directory on the local mount"
    )
    parser.add_argument("track_ids", type=int, nargs="+", help="Engine Track IDs in desired order")
    args = parser.parse_args()
    if len(args.track_ids) != len(set(args.track_ids)):
        parser.error("Track IDs must be distinct")
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        version = db.execute(
            "SELECT schemaVersionMajor, schemaVersionMinor, schemaVersionPatch FROM Information"
        ).fetchone()
        if version != (3, 0, 2):
            raise ValueError(f"Spike requires Engine schema 3.0.2, got {version}")
        tracks = [read_track(db, args.library.resolve(), track_id) for track_id in args.track_ids]
    print(json.dumps({"playlist": "Engine analysis trial", "tracks": tracks}))


if __name__ == "__main__":
    main()
