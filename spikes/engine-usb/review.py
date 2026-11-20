"""Preview and apply performance edits from a delivered Engine USB snapshot."""

import argparse
import hashlib
import shutil
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from uuid import UUID

FIELDS = ("cues", "loops", "grid")


def checksum(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def require_closed(path):
    for suffix in ("-wal", "-journal", "-shm"):
        if Path(str(path) + suffix).exists():
            raise ValueError(f"SQLite sidecar present: {path}{suffix}")


def read_only(path):
    return closing(sqlite3.connect(path.resolve(strict=True).as_uri() + "?mode=ro", uri=True))


def library_id(db):
    (row,) = db.execute(
        "SELECT uuid, schemaVersionMajor, schemaVersionMinor, schemaVersionPatch FROM Information"
    ).fetchall()
    value, *version = row
    if version != [3, 0, 2]:
        raise ValueError(f"Unsupported Engine schema: {version}")
    return str(UUID(value))


def tracks(db, source_id):
    rows = {}
    for origin, track_id, title, cues, loops, active, grid, bpm in db.execute(
        """SELECT t.originTrackId, t.id, t.title, p.quickCues, p.loops,
                  p.activeOnLoadLoops, p.beatData, t.bpmAnalyzed
           FROM Track t JOIN PerformanceData p ON p.trackId = t.id
           WHERE t.originDatabaseUuid = ?""",
        (source_id,),
    ):
        if origin in rows:
            raise ValueError(f"Duplicate Engine origin: {origin}")
        rows[origin] = (track_id, title, ((cues,), (loops, active), (grid, bpm)))
    return rows


def plan(source, baseline, device, *, conflicts="review"):
    with read_only(source) as current, read_only(baseline) as exported, read_only(device) as usb:
        source_id = library_id(current)
        device_id = library_id(usb)
        if library_id(exported) != device_id or device_id == source_id:
            raise ValueError("USB and baseline must share a device UUID distinct from the source")
        before = tracks(exported, source_id)
        if not before:
            raise ValueError("Baseline has no tracks from this source database")
        after = tracks(usb, source_id)
        local = tracks(current, source_id)
    result = []
    for origin, (_, title, old_fields) in sorted(before.items()):
        if origin not in after:
            continue
        usb_fields = after[origin][2]
        local_row = local.get(origin)
        for i, (name, old, new) in enumerate(zip(FIELDS, old_fields, usb_fields, strict=True)):
            if old == new:
                continue
            if local_row is None:
                result.append((origin, title, name, "missing source", new))
                continue
            local_value = local_row[2][i]
            if local_value == new:
                continue
            if local_value == old or conflicts == "usb":
                action = "apply"
            elif conflicts == "source":
                action = "keep source"
            else:
                action = "conflict"
            if name == "grid" and not new[0]:
                action = "missing USB grid"
            result.append((local_row[0], title, name, action, new))
    return result


def apply(source, source_hash, edits):
    if not edits:
        return None
    with tempfile.TemporaryDirectory(prefix=".engine-review-", dir=source.parent) as tmp:
        staged = Path(tmp) / "m.db"
        shutil.copy2(source, staged)
        if checksum(staged) != source_hash:
            raise ValueError("Source changed after review")
        with closing(sqlite3.connect(staged)) as db, db:
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA recursive_triggers = ON")
            for track_id, _, field, _, value in edits:
                match field:
                    case "cues":
                        db.execute(
                            "UPDATE PerformanceData SET quickCues = ? WHERE trackId = ?",
                            (*value, track_id),
                        )
                    case "loops":
                        db.execute(
                            "UPDATE PerformanceData SET loops = ?, activeOnLoadLoops = ? "
                            "WHERE trackId = ?",
                            (*value, track_id),
                        )
                    case "grid":
                        db.execute(
                            "UPDATE PerformanceData SET beatData = ? WHERE trackId = ?",
                            (value[0], track_id),
                        )
                        db.execute(
                            "UPDATE Track SET bpmAnalyzed = ? WHERE id = ?", (value[1], track_id)
                        )
            if (
                db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]
                or db.execute("PRAGMA foreign_key_check").fetchone()
            ):
                raise ValueError("Edited database failed integrity checks")
        require_closed(source)
        backup = source.with_name(f"{source.name}.before-usb-{source_hash}.bak")
        if checksum(source) != source_hash:
            raise ValueError("Source changed after review")
        # Link the original inode before replacing it; do not overwrite a previous backup.
        if not backup.exists():
            backup.hardlink_to(source)
        staged.replace(source)
    return backup


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, help="Engine m.db; close Engine and stop other writers"
    )
    parser.add_argument("baseline", type=Path, help="database originally delivered to the stick")
    parser.add_argument("device", type=Path, help="current USB database snapshot")
    parser.add_argument(
        "--conflicts",
        choices=("review", "usb", "source"),
        default="review",
        help="whether to block conflicts or prefer one side",
    )
    parser.add_argument("--approve", help="apply the exact review with this token")
    args = parser.parse_args()
    source, baseline, device = (
        p.resolve(strict=True) for p in (args.source, args.baseline, args.device)
    )
    for path in (source, baseline, device):
        require_closed(path)
    fingerprints = tuple(checksum(path) for path in (source, baseline, device))
    edits = plan(source, baseline, device, conflicts=args.conflicts)
    if tuple(checksum(path) for path in (source, baseline, device)) != fingerprints:
        raise ValueError("A database changed during review")
    token = hashlib.sha256((":".join(fingerprints) + f":{args.conflicts}").encode()).hexdigest()
    for track_id, title, field, action, _ in edits:
        print(f"{action}: {track_id} {title or '(untitled)'} — {field}")
    applicable = [edit for edit in edits if edit[3] == "apply"]
    blocked = [edit for edit in edits if edit[3] not in ("apply", "keep source")]
    if args.approve is not None:
        if args.approve != token:
            raise ValueError("Review changed; preview again")
        backup = apply(source, fingerprints[0], applicable)
        print(f"Applied {len(applicable)} changes" + (f"; backup: {backup}" if backup else ""))
    else:
        print(f"{len(applicable)} applicable, {len(blocked)} blocked; approval token: {token}")
    if not blocked and (args.approve is not None or not edits):
        print(f"USB replacement token (after applying edits): {fingerprints[1]}:{fingerprints[2]}")


if __name__ == "__main__":
    main()
