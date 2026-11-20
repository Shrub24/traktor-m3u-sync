"""Deliver a USB generation to a stick over SFTP, and pull its library database back.

Only files whose content differs from what was last installed are sent. Media goes first,
the activation file (the library database) last, so an interrupted delivery leaves the
installed library working. A stick whose database no longer matches the one installed
(player edits, or a library this tool did not write) is never overwritten unless that
exact database was reviewed.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, cast

from paramiko import SFTPClient, SSHClient

from ..config import UsbDeviceConfig
from .generation import Generation

MARKER = ".playlist-sync-stick"
_CHUNK = 1024 * 1024
_SIDECARS = ("-journal", "-wal", "-shm")


class DeliveryError(RuntimeError):
    """Raised when delivery must stop without replacing the stick's library."""


@dataclass(frozen=True)
class Installed:
    database: str
    files: Mapping[str, str]


@dataclass(frozen=True)
class PushResult:
    files: tuple[str, ...]
    bytes: int
    applied: bool


@dataclass(frozen=True)
class PullResult:
    snapshot: Path
    baseline: Path | None
    changed: bool


class StickState:
    """Per-stick record of what was installed, plus the databases delivered and pulled."""

    def __init__(self, device: UsbDeviceConfig) -> None:
        self.path = device.state_dir / str(device.stick)
        self.path.mkdir(mode=0o700, parents=True, exist_ok=True)

    def installed(self) -> Installed | None:
        record = self.path / "installed.json"
        if not record.is_file():
            return None
        raw = cast(dict[str, Any], json.loads(record.read_text()))
        return Installed(str(raw["database"]), cast(dict[str, str], raw["files"]))

    def record(self, installed: Installed) -> None:
        _write(
            self.path / "installed.json",
            json.dumps({"database": installed.database, "files": dict(installed.files)}).encode(),
        )

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
def connect(device: UsbDeviceConfig) -> Generator[SFTPClient]:
    """Open SFTP at the stick root, pinned to a known host key, after checking its marker."""
    lock_path = device.state_dir / f"{device.stick}.lock"
    device.state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    with lock_path.open("a") as lock, SSHClient() as ssh:
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
            banner_timeout=15,
            auth_timeout=15,
        )
        with ssh.open_sftp() as sftp:
            channel = sftp.get_channel()
            assert channel is not None
            channel.settimeout(60)
            sftp.chdir(device.remote_root)
            try:
                with sftp.open(MARKER, "rb") as stream:
                    marker = stream.read(80).strip()
            except FileNotFoundError as exc:
                raise DeliveryError(f"No {MARKER} at {device.remote_root}") from exc
            if marker != str(device.stick).encode():
                raise DeliveryError("Wrong USB stick")
            yield sftp


def pull(sftp: SFTPClient, state: StickState, activation: str) -> PullResult:
    """Copy the stick's library database to the state directory for review."""
    digest, snapshot = state.keep(_read(sftp, activation))
    installed = state.installed()
    baseline = None if installed is None else state.database(installed.database)
    changed = installed is None or digest != installed.database
    return PullResult(snapshot, baseline, changed)


def push(
    sftp: SFTPClient,
    generation: Generation,
    state: StickState,
    *,
    apply: bool,
    reviewed: str | None = None,
) -> PushResult:
    """Send the files that differ from the installed generation, then the database.

    ``reviewed`` is the SHA-256 of a stick database whose edits were reviewed; only that
    exact database may be replaced when it is not the one this tool installed.
    """
    activation = generation.activation
    installed = state.installed()
    _check_sidecars(sftp, activation)
    current = False
    if _mode(sftp, activation) is not None:
        digest, copy = state.keep(_read(sftp, activation))
        current = installed is not None and digest == installed.database
        if not current and digest != reviewed:
            raise DeliveryError(
                f"The stick database is not the one last installed; saved it to {copy}. "
                "Review its edits before replacing it."
            )
    elif reviewed is not None:
        raise DeliveryError("The reviewed stick database is no longer on the stick")

    previous: Mapping[str, str] = {} if installed is None else installed.files
    desired = {name: entry.sha256 for name, entry in generation.files.items()}
    changes = sorted(name for name, sha in desired.items() if previous.get(name) != sha)
    assets = [name for name in changes if name != activation]
    if not current and activation not in changes:
        changes.append(activation)
    size = sum(generation.files[name].size for name in changes)
    if not apply or not changes:
        return PushResult(tuple(changes), size, applied=False)

    made: set[str] = set()
    _check_replace(sftp, activation, made)
    for name in assets:
        entry = generation.files[name]
        _make_dirs(sftp, PurePosixPath(name), made)
        mode = _mode(sftp, name)
        if entry.source is not None and mode is not None:
            # Media paths are content-addressed and only ever created by an atomic rename,
            # so a present file of the right size is a completed earlier upload.
            if not stat.S_ISREG(mode) or sftp.stat(name).st_size != entry.size:
                raise DeliveryError(f"Unexpected file at a media path on the stick: {name}")
            continue
        _upload(sftp, generation.local(name), name, entry.sha256)

    database = generation.local(activation)
    _make_dirs(sftp, PurePosixPath(activation), made)
    data = database.read_bytes()
    if hashlib.sha256(data).hexdigest() != desired[activation]:
        raise DeliveryError("The staged database changed after the build")
    state.keep(data)
    _check_sidecars(sftp, activation)
    _upload(sftp, database, activation, desired[activation])
    state.record(Installed(desired[activation], desired))
    return PushResult(tuple(changes), size, applied=True)


def _upload(sftp: SFTPClient, source: Path, name: str, sha256: str) -> None:
    temp = str(PurePosixPath(name).with_name(f".playlist-sync-{sha256[:32]}.part"))
    if _mode(sftp, temp) is not None:
        sftp.remove(temp)
    digest = hashlib.sha256()
    try:
        with source.open("rb") as local, sftp.open(temp, "wx") as remote:
            remote.set_pipelined(True)
            while block := local.read(_CHUNK):
                digest.update(block)
                remote.write(block)
        if digest.hexdigest() != sha256:
            raise DeliveryError(f"Source changed since the build; rebuild: {source}")
        if sftp.stat(temp).st_size != source.stat().st_size:
            raise DeliveryError(f"Upload size mismatch: {name}")
        # Standard SFTP rename can need a hard link, which FAT32 cannot create.
        sftp.posix_rename(temp, name)
    finally:
        if _mode(sftp, temp) is not None:
            sftp.remove(temp)


def _check_replace(sftp: SFTPClient, activation: str, made: set[str]) -> None:
    """Prove the server can atomically replace a file before anything is sent."""
    _make_dirs(sftp, PurePosixPath(activation), made)
    parent = PurePosixPath(activation).parent
    new, old = (str(parent / f".playlist-sync-probe-{name}") for name in ("new", "old"))
    try:
        for path, value in ((new, b"new"), (old, b"old")):
            with sftp.open(path, "wb") as stream:
                stream.write(value)
        try:
            sftp.posix_rename(new, old)
        except OSError as exc:
            raise DeliveryError("The SFTP server cannot replace an existing file") from exc
        with sftp.open(old, "rb") as stream:
            if stream.read() != b"new":
                raise DeliveryError("The SFTP replacement probe failed")
    finally:
        for path in (new, old):
            if _mode(sftp, path) is not None:
                sftp.remove(path)


def _check_sidecars(sftp: SFTPClient, activation: str) -> None:
    for suffix in _SIDECARS:
        if _mode(sftp, activation + suffix) is not None:
            raise DeliveryError(
                f"{activation}{suffix} is present: the library is open or was not closed cleanly"
            )


def _read(sftp: SFTPClient, name: str) -> bytes:
    _check_sidecars(sftp, name)
    mode = _mode(sftp, name)
    if mode is None or not stat.S_ISREG(mode):
        raise DeliveryError(f"No library database on the stick at {name}")
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
