"""Deliver a USB generation over SFTP to a stick root given per run.

Each stick is identified by the UUID in its marker file, written on its first delivery.
Delivery sends only content the stick lacks, installs the database last, and never
replaces a stick database other than the one it installed or one that was reviewed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import uuid
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import cast

from paramiko import SFTPClient, SSHClient

from ..config import UsbDeviceConfig
from .generation import Generation

MARKER = ".playlist-sync-stick"
_CHUNK = 1024 * 1024


class DeliveryError(RuntimeError):
    """Raised when delivery must stop without replacing the stick's library."""


@dataclass(frozen=True)
class PushResult:
    files: tuple[str, ...]
    bytes: int
    applied: bool


@dataclass(frozen=True)
class PullResult:
    snapshot: Path
    sha256: str
    changed: bool


class StickState:
    """What was installed on one stick, plus every database delivered to or pulled from it."""

    def __init__(self, state_dir: Path, stick: uuid.UUID, format: str = "engine") -> None:
        self.path = state_dir / str(stick)
        if format != "engine":
            self.path /= format
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)

    def hashes(self, record: str) -> dict[str, str]:
        path = self.path / record
        if not path.is_file():
            return {}
        return cast(dict[str, str], json.loads(path.read_text())["files"])

    def record(self, record: str, files: Mapping[str, str | tuple[str | None, str]]) -> None:
        _write(self.path / record, json.dumps({"files": dict(files)}).encode())

    def accept(self, sha256: str) -> None:
        """Allow the next push to replace this stick database, whose edits were reviewed."""
        _write(self.path / "reviewed", sha256.encode())

    def accepted(self) -> str | None:
        record = self.path / "reviewed"
        return record.read_text() if record.is_file() else None

    def database(self, sha256: str) -> Path:
        return self.path / "databases" / f"{sha256}.db"

    def keep(self, data: bytes) -> tuple[str, Path]:
        digest = hashlib.sha256(data).hexdigest()
        path = self.database(digest)
        path.parent.mkdir(mode=0o700, exist_ok=True)
        if not path.is_file():
            _write(path, data)
        return digest, path


@contextmanager
def session(device: UsbDeviceConfig) -> Generator[SFTPClient]:
    """SFTP to the device, pinned to its known host key; one session per state directory."""
    device.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (device.state_dir / "lock").open("a") as lock, SSHClient() as ssh:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        ssh.load_host_keys(str(device.known_hosts))
        ssh.connect(
            device.host,
            port=device.port,
            username=device.user,
            key_filename=str(device.key_file),
            look_for_keys=False,
            allow_agent=False,
            timeout=15,
        )
        with ssh.open_sftp() as sftp:
            channel = sftp.get_channel()
            assert channel is not None
            channel.settimeout(60)
            yield sftp


def enter_stick(sftp: SFTPClient, root: str, *, mark: bool) -> uuid.UUID:
    """Enter the stick at ``root`` and return the ID in its marker, writing one if ``mark``."""
    sftp.chdir(root)
    try:
        with sftp.open(MARKER, "rb") as stream:
            return uuid.UUID(stream.read(64).decode().strip())
    except FileNotFoundError:
        if not mark:
            raise DeliveryError(f"No {MARKER} at {root}: nothing was delivered there") from None
    stick = uuid.uuid4()
    with sftp.open(MARKER, "wx") as stream:
        stream.write(f"{stick}\n")
    return stick


def pull(sftp: SFTPClient, state: StickState, activation: str) -> PullResult:
    digest, snapshot = state.keep(_read(sftp, activation))
    return PullResult(snapshot, digest, digest != state.hashes("installed.json").get(activation))


def push(
    sftp: SFTPClient,
    generation: Generation,
    state: StickState,
    *,
    apply: bool,
    reviewed: str | None = None,
) -> PushResult:
    """``reviewed`` is the SHA-256 of a stick database that may be replaced although it is
    not the one this tool installed."""
    previous = state.hashes("installed.json")
    pending_file = state.path / "pending.json"
    pending = (
        cast(dict[str, list[str | None]], json.loads(pending_file.read_text())["files"])
        if pending_file.is_file()
        else {}
    )
    desired = {name: entry.sha256 for name, entry in generation.files.items()}
    assets = sorted(
        name
        for name in desired
        if name not in generation.activation
        and (previous.get(name) != desired[name] or name in pending)
    )
    databases: list[str] = []
    switching: dict[str, tuple[str | None, str]] = {}
    for name in generation.activation:
        digest = None
        if _mode(sftp, name) is not None:
            digest, copy = state.keep(_read(sftp, name))
            known = (previous.get(name), *pending.get(name, ()))
            if len(generation.activation) == 1:
                known += (reviewed, state.accepted())
            if digest not in known:
                raise DeliveryError(
                    f"The stick database {name} is not the one last installed; saved it to {copy}. "
                    "Review its edits before replacing it."
                )
        if digest != desired[name]:
            databases.append(name)
        switching[name] = (digest, desired[name])

    for name in tuple(assets):
        if not name.startswith("PIONEER/USBANLZ/"):
            switching[name] = (previous.get(name), desired[name])
            continue
        digest = (
            None if _mode(sftp, name) is None else hashlib.sha256(_read(sftp, name)).hexdigest()
        )
        if digest not in (None, previous.get(name), desired[name], *pending.get(name, ())):
            raise DeliveryError(f"Pioneer analysis has changed on the stick: {name}")
        if digest == desired[name]:
            assets.remove(name)
        switching[name] = (digest, desired[name])

    changes = (*assets, *databases)
    size = sum(generation.files[name].size for name in changes)
    if not apply:
        return PushResult(changes, size, applied=False)
    if changes:
        made: set[str] = set()
        _check_replace(sftp, generation.activation[0], made)
        # SFTP renames are atomic individually, not as a group.
        state.record("pending.json", switching)
        for name in assets:
            entry = generation.files[name]
            _make_dirs(sftp, PurePosixPath(name), made)
            # Engine media is content-addressed and appears only after a complete upload.
            if entry.source is not None and _mode(sftp, name) is not None:
                continue
            _upload(sftp, generation.local(name), name, entry.sha256)

        for name in databases:
            database = generation.local(name)
            state.keep(database.read_bytes())
            _upload(sftp, database, name, desired[name])
    state.record("installed.json", desired)
    (state.path / "pending.json").unlink(missing_ok=True)
    return PushResult(changes, size, applied=bool(changes))


def _upload(sftp: SFTPClient, source: Path, name: str, sha256: str) -> None:
    temp = str(PurePosixPath(name).with_name(f".playlist-sync-{sha256[:32]}.part"))
    digest = hashlib.sha256()
    try:
        with source.open("rb") as local, sftp.open(temp, "wb") as remote:
            remote.set_pipelined(True)
            while block := local.read(_CHUNK):
                digest.update(block)
                remote.write(block)
        if digest.hexdigest() != sha256:
            raise DeliveryError(f"Source changed since the build; rebuild: {source}")
        # Plain SFTP rename needs a hard link, which FAT32 lacks.
        sftp.posix_rename(temp, name)
    finally:
        if _mode(sftp, temp) is not None:
            sftp.remove(temp)


def _check_replace(sftp: SFTPClient, activation: str, made: set[str]) -> None:
    """Database-last publication relies on atomic replacement; prove it before sending."""
    _make_dirs(sftp, PurePosixPath(activation), made)
    parent = PurePosixPath(activation).parent
    new, old = (str(parent / f".playlist-sync-probe-{name}") for name in ("new", "old"))
    try:
        for path, value in ((new, b"new"), (old, b"old")):
            with sftp.open(path, "wb") as stream:
                stream.write(value)
        sftp.posix_rename(new, old)
        with sftp.open(old, "rb") as stream:
            if stream.read() != b"new":
                raise DeliveryError("The SFTP server cannot replace an existing file")
    finally:
        for path in (new, old):
            if _mode(sftp, path) is not None:
                sftp.remove(path)


def _read(sftp: SFTPClient, name: str) -> bytes:
    for suffix in ("-journal", "-wal", "-shm"):
        if _mode(sftp, name + suffix) is not None:
            raise DeliveryError(f"{name}{suffix} is present: the library was not closed cleanly")
    with sftp.open(name, "rb") as stream:
        stream.prefetch()
        return stream.read()


def _mode(sftp: SFTPClient, name: str) -> int | None:
    try:
        return sftp.lstat(name).st_mode
    except FileNotFoundError:
        return None


def _make_dirs(sftp: SFTPClient, path: PurePosixPath, made: set[str]) -> None:
    for parent in reversed(path.parents):
        name = str(parent)
        if name == "." or name in made:
            continue
        mode = _mode(sftp, name)
        if mode is None:
            sftp.mkdir(name)
        elif not stat.S_ISDIR(mode):
            raise DeliveryError(f"Not a directory on the stick: {name}")
        made.add(name)


def _write(path: Path, data: bytes) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_bytes(data)
    os.replace(temp, path)
