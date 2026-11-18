"""Deliver an already staged USB export through a pinned SFTP connection."""

import argparse
import fcntl
import hashlib
import json
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import BinaryIO
from uuid import UUID

from paramiko import SFTPClient, SSHClient

MARKER = ".playlist-sync-stick"
ENGINE_DATABASE = "Engine Library/Database2/m.db"
CHUNK = 1024 * 1024


def digest(stream: BinaryIO) -> str:
    return hashlib.file_digest(stream, "sha256").hexdigest()


def manifest(tree: Path, activation: str) -> dict[str, str]:
    files: dict[str, str] = {}
    names: set[str] = set()
    for entry in tree.rglob("*"):
        name = entry.relative_to(tree).as_posix()
        if entry.is_symlink() or any(part.startswith(".") for part in Path(name).parts):
            raise ValueError(f"Unsupported export entry: {name}")
        if name.casefold() in names:
            raise ValueError(f"Case-insensitive path collision: {name}")
        names.add(name.casefold())
        if not entry.is_dir():
            with entry.open("rb") as stream:
                files[name] = digest(stream)
    if activation not in files:
        raise ValueError(f"Export is missing {activation}")
    return files


def remote_mode(sftp: SFTPClient, path: str) -> int | None:
    try:
        return sftp.lstat(path).st_mode
    except FileNotFoundError:
        return None


def remote_digest(sftp: SFTPClient, path: str) -> str:
    with sftp.open(path, "rb") as stream:
        stream.prefetch(max_concurrent_requests=32)
        return digest(stream)


def make_dirs(sftp: SFTPClient, path: PurePosixPath, made: set[str]) -> None:
    for parent in reversed(path.parents):
        name = str(parent)
        if name == "." or name in made:
            continue
        mode = remote_mode(sftp, name)
        if mode is None:
            sftp.mkdir(name)
        elif not stat.S_ISDIR(mode):
            raise ValueError(f"Not a directory on the stick: {name}")
        made.add(name)


@contextmanager
def upload(sftp: SFTPClient, source: Path, path: str) -> Iterator[str]:
    dest = PurePosixPath(path)
    suffix = hashlib.sha256(path.encode()).hexdigest()[:32]
    temp = str(dest.with_name(f".playlist-sync-{suffix}.part"))
    if remote_mode(sftp, temp) is not None:
        sftp.remove(temp)
    try:
        with source.open("rb") as local, sftp.open(temp, "wx") as remote:
            remote.set_pipelined(True)
            while block := local.read(CHUNK):
                remote.write(block)
        if sftp.stat(temp).st_size != source.stat().st_size:
            raise OSError(f"Upload size mismatch: {path}")
        yield temp
    finally:
        # A disconnected client may leave a temporary file; the next run can discard it.
        if remote_mode(sftp, temp) is not None:
            sftp.remove(temp)


def save(path: Path, data: bytes) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("wb") as stream:
        stream.write(data)
    temp.replace(path)


def check_replace(sftp: SFTPClient, activation: str) -> None:
    parent = PurePosixPath(activation).parent
    source, target = (str(parent / f".playlist-sync-probe-{name}") for name in ("new", "old"))
    try:
        for path, value in ((source, b"new"), (target, b"old")):
            with sftp.open(path, "wb") as stream:
                stream.write(value)
        try:
            sftp.posix_rename(source, target)
        except OSError as exc:
            raise ValueError(
                "SFTP server cannot replace an existing file; database left intact"
            ) from exc
        with sftp.open(target, "rb") as stream:
            if stream.read() != b"new":
                raise ValueError("SFTP replacement probe failed; database left intact")
    finally:
        for path in (source, target):
            if remote_mode(sftp, path) is not None:
                sftp.remove(path)


def check_sidecars(sftp: SFTPClient, activation: str) -> None:
    for suffix in ("-wal", "-journal", "-shm"):
        if remote_mode(sftp, activation + suffix) is not None:
            raise ValueError(
                f"SQLite sidecar present: {activation}{suffix}; close the library first"
            )


def push(
    sftp: SFTPClient,
    tree: Path,
    state: Path,
    activation: str,
    desired: dict[str, str],
    *,
    apply: bool,
) -> None:
    current: dict[str, str] = {}
    installed = remote_mode(sftp, activation)
    check_sidecars(sftp, activation)
    if installed is not None:
        if not stat.S_ISREG(installed):
            raise ValueError(f"Not a regular library file: {activation}")
        with sftp.open(activation, "rb") as stream:
            stream.prefetch(max_concurrent_requests=32)
            backup = stream.read()
        key = hashlib.sha256(backup).hexdigest()
        save(state / f"{key}.db", backup)
        record = state / f"{key}.json"
        if not record.is_file():
            raise ValueError(f"Unrecognized stick database; saved a copy to {state / f'{key}.db'}")
        current = json.loads(record.read_text())

    key = desired[activation]
    record = state / f"{key}.json"
    if record.exists() and json.loads(record.read_text()) != desired:
        raise ValueError("Same database with different assets; stage a fresh device generation")
    changes = sorted(path for path, value in desired.items() if current.get(path) != value)
    protected = {path.casefold() for path in current if path != activation}
    for path in changes:
        if path.casefold() in protected:
            raise ValueError(f"Would replace an active asset: {path}; stage a fresh asset path")
    assets = [path for path in changes if path != activation]
    print(f"{len(assets)} assets ({sum((tree / p).stat().st_size for p in assets):,} bytes)")
    for path in changes:
        print(path, flush=True)
    if not apply or not changes:
        return

    if installed is not None:
        check_replace(sftp, activation)
    made: set[str] = set()
    for path in assets:
        make_dirs(sftp, PurePosixPath(path), made)
        mode = remote_mode(sftp, path)
        if mode is not None:
            if not stat.S_ISREG(mode) or remote_digest(sftp, path) != desired[path]:
                raise ValueError(f"Unrecognized asset already exists: {path}")
            continue
        with upload(sftp, tree / path, path) as temp:
            sftp.rename(temp, path)

    make_dirs(sftp, PurePosixPath(activation), made)
    with upload(sftp, tree / activation, activation) as temp:
        check_sidecars(sftp, activation)
        if remote_digest(sftp, temp) != key:
            raise OSError("Uploaded library hash mismatch")
        # Record before renaming: a lost acknowledgement is recoverable by reading the live DB.
        save(record, json.dumps(desired, sort_keys=True).encode())
        if installed is None:
            sftp.rename(temp, activation)
        else:
            sftp.posix_rename(temp, activation)
    print("USB delivery complete. Stop SFTP and eject the drive on Android.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path, help="immutable staged USB export")
    parser.add_argument("host", help="phone address on the private network")
    parser.add_argument("stick", type=UUID, help=f"expected UUID in {MARKER} at the USB root")
    parser.add_argument("--port", type=int, default=2222)
    parser.add_argument("--user", required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--known-hosts", type=Path, required=True)
    parser.add_argument(
        "--state", type=Path, required=True, help="private home-forge state directory"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write to the stick (default: preview)"
    )
    args = parser.parse_args()
    tree = args.tree.resolve(strict=True)
    if not tree.is_dir():
        parser.error("tree must be a directory")
    desired = manifest(tree, ENGINE_DATABASE)
    state = args.state / str(args.stick)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (state / "lock").open("a") as lock, SSHClient() as ssh:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ssh.load_host_keys(str(args.known_hosts))
        ssh.connect(
            args.host,
            port=args.port,
            username=args.user,
            key_filename=str(args.key),
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )
        with ssh.open_sftp() as sftp:
            sftp.get_channel().settimeout(60)
            with sftp.open(MARKER, "rb") as stream:
                if stream.read(80).strip() != str(args.stick).encode():
                    raise ValueError("Wrong USB stick")
            push(sftp, tree, state, ENGINE_DATABASE, desired, apply=args.apply)


if __name__ == "__main__":
    main()
