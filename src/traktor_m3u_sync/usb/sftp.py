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
import re
import shlex
import stat
import uuid
from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from itertools import batched
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
    audio_reused: int
    audio_missing: int
    audio_changed: int


@dataclass(frozen=True)
class PullResult:
    snapshot: Path
    sha256: str
    changed: bool


class StickState:
    """What was installed on one stick, plus every database delivered to or pulled from it."""

    def __init__(self, state_dir: Path, stick: uuid.UUID | None, format: str = "engine") -> None:
        self.path = state_dir / (str(stick) if stick is not None else "unmarked")
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


def enter_stick(sftp: SFTPClient, root: str, *, mark: bool) -> uuid.UUID | None:
    """Enter the stick at ``root`` and return the ID in its marker, writing one if ``mark``."""
    sftp.chdir(root)
    try:
        with sftp.open(MARKER, "rb") as stream:
            return uuid.UUID(stream.read(64).decode().strip())
    except FileNotFoundError:
        if not mark:
            return None
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
    rescan: bool = False,
    register: Callable[[], StickState] | None = None,
    hash_audio: Callable[[SFTPClient, tuple[str, ...]], Mapping[str, str]] | None = None,
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
                    + (
                        f" Engine database SHA-256: {digest}"
                        if len(generation.activation) == 1
                        else ""
                    )
                )
        if digest != desired[name]:
            databases.append(name)
        switching[name] = (digest, desired[name])

    media = tuple(name for name, entry in generation.files.items() if entry.source is not None)
    audio_cache = "audio.json"
    scan = state.path / "audio-scan.json"
    key = hashlib.sha256(
        json.dumps(
            [sftp.getcwd(), switching, {name: desired[name] for name in media}], sort_keys=True
        ).encode()
    ).hexdigest()
    saved = (
        cast(dict[str, dict[str, str]], json.loads(scan.read_text())).get(key)
        if media and not rescan and scan.is_file()
        else None
    )
    digests = saved if saved is not None else {} if rescan else state.hashes(audio_cache)
    to_hash = tuple(name for name in media if name not in digests) if saved is None else ()
    if to_hash:
        digests.update((hash_audio or remote_audio_hashes)(sftp, to_hash))
    digests = {name: digests[name] for name in media if name in digests}
    missing = sum(name not in digests for name in media)
    changed = sum(name in digests and digests[name] != desired[name] for name in media)
    reused = len(media) - missing - changed
    assets = sorted(
        name
        for name, entry in generation.files.items()
        if name not in generation.activation
        and (
            digests.get(name) != desired[name]
            if entry.source is not None
            else previous.get(name) != desired[name] or name in pending
        )
    )
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
    result = PushResult(changes, size, apply and bool(changes), reused, missing, changed)
    if not apply:
        if media:
            _write(scan, json.dumps({key: digests}).encode())
        return result
    if register is not None:
        state = register()
    if media:
        scan.unlink(missing_ok=True)
        state.record(
            audio_cache,
            {name: digest for name, digest in digests.items() if digest == desired[name]},
        )
    if changes:
        made: set[str] = set()
        _check_replace(sftp, generation.activation[0], made)
        # SFTP renames are atomic individually, not as a group.
        state.record("pending.json", switching)
        for name in assets:
            entry = generation.files[name]
            _make_dirs(sftp, PurePosixPath(name), made)
            _upload(sftp, generation.local(name), name, entry.sha256)

        if media:
            state.record(audio_cache, {name: desired[name] for name in media})
        for name in databases:
            database = generation.local(name)
            state.keep(database.read_bytes())
            _upload(sftp, database, name, desired[name])
    state.record("installed.json", desired)
    (state.path / "pending.json").unlink(missing_ok=True)
    return result


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


def remote_audio_hashes(sftp: SFTPClient, names: tuple[str, ...]) -> dict[str, str]:
    root = sftp.getcwd()
    assert root is not None
    hashes: dict[str, str] = {}
    for batch in batched(names, 32):
        paths = shlex.join([str(PurePosixPath(root) / name) for name in batch])
        command = (
            "command -v sha256sum >/dev/null || exit 1; "
            f"for path in {paths}; do "
            'if [ -e "$path" ]; then '
            '[ -f "$path" ] && sha256sum < "$path" || exit 1; '
            "else printf '%s\\n' -; fi; done"
        )
        rows = _remote_command(sftp, command).splitlines()
        if len(rows) != len(batch):
            raise DeliveryError("Unexpected number of stick audio hashes")
        for name, row in zip(batch, rows, strict=True):
            if row == "-":
                continue
            match = re.fullmatch(r"([0-9a-f]{64})\s+-", row)
            if match is None:
                raise DeliveryError(f"Invalid stick audio hash for {name}")
            hashes[name] = match[1]
    return hashes


def _remote_command(sftp: SFTPClient, command: str) -> str:
    sftp_channel = sftp.get_channel()
    assert sftp_channel is not None
    transport = sftp_channel.get_transport()
    with transport.open_session(timeout=15) as channel:
        channel.settimeout(120)
        channel.set_combine_stderr(True)
        channel.exec_command(command)
        with channel.makefile("rb") as output:
            result = output.read().decode(errors="replace")
        if channel.recv_exit_status() != 0:
            raise DeliveryError(f"Could not hash stick audio over SSH: {result.strip()}")
        return result


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
        sidecar = name + suffix
        try:
            attrs = sftp.lstat(sidecar)
        except FileNotFoundError:
            continue
        if suffix == "-journal" and attrs.st_size == 0:
            continue
        raise DeliveryError(f"{sidecar} is present: the library was not closed cleanly")
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
