"""Inspect and deliver prepared libraries without refreshing the source."""

import sqlite3
from collections.abc import Callable, Iterable
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import UUID

from paramiko import SFTPClient, SSHException

from ..config import UsbConfig, UsbDeviceConfig
from ..formats.engine import usb
from ..formats.engine.performance import EnginePerformanceError, capture
from ..formats.engine.writer import EngineWriteError, preflight_target
from ..model.performance import PlaylistNode, Snapshot, SnapshotError, loads
from . import generation, pioneer, sftp

# Failures an operator can act on; anything else is a bug and propagates.
OPERATION_ERRORS = (
    sftp.DeliveryError,
    EnginePerformanceError,
    usb.EngineUsbError,
    EngineWriteError,
    generation.GenerationError,
    SnapshotError,
    OSError,
    sqlite3.Error,
    SSHException,
)

type PlaylistPath = tuple[str, ...]
type PlaylistTracks = tuple[object, ...]
type Playlists = dict[PlaylistPath, PlaylistTracks]


def playlists(nodes: Iterable[PlaylistNode], parent: PlaylistPath = ()) -> Playlists:
    result: Playlists = {}
    for node in nodes:
        path = (*parent, node.name)
        listing = playlists(node.children, path)
        if node.tracks or not node.children:
            listing = {path: node.tracks, **listing}
        if result.keys() & listing.keys():
            raise generation.GenerationError(f"Ambiguous playlist name: {' / '.join(path)}")
        result.update(listing)
    return result


def _subset(snapshot: Snapshot, selected: set[PlaylistPath]) -> Snapshot:
    def select(nodes: Iterable[PlaylistNode], parent: PlaylistPath) -> tuple[PlaylistNode, ...]:
        kept: list[PlaylistNode] = []
        for node in nodes:
            path = (*parent, node.name)
            children = select(node.children, path)
            if children or path in selected:
                kept.append(
                    PlaylistNode(node.name, node.tracks if path in selected else (), children)
                )
        return tuple(kept)

    nodes = select(snapshot.playlists, ())
    refs = {ref for tracks in playlists(nodes).values() for ref in tracks}
    return Snapshot(
        snapshot.library, snapshot.sha256, tuple(t for t in snapshot.tracks if t.ref in refs), nodes
    )


def marker(
    path: PlaylistPath, desired: set[PlaylistPath], local: Playlists, remote: Playlists
) -> str:
    if path not in desired:
        return "-" if path in remote else " "
    if path not in remote:
        return "+"
    return "^" if local[path] != remote[path] else " "


class Manager:
    def __init__(self, settings: UsbConfig, device: UsbDeviceConfig, root: str) -> None:
        self.settings = settings
        self.device = device
        self.root = root

    def inspect(self, name: str) -> tuple[Playlists, Playlists]:
        with generation.lock(self.settings.output_dir), sftp.session(self.device) as client:
            stick = sftp.enter_stick(client, self.root, mark=False)
            export = generation.current(self.settings.output_dir / name)
            state = sftp.StickState(self.device.state_dir, stick, name)
            if name == "engine":
                installed = self._engine(client, state)
                return (
                    playlists(capture(export.local(usb.DATABASE)).playlists),
                    {} if installed is None else playlists(capture(installed.snapshot).playlists),
                )
            with TemporaryDirectory() as directory:
                return pioneer.inspect(export.tree), pioneer.inspect_stick(
                    client, state, Path(directory)
                )

    def review(self, confirm: Callable[[usb.Review], bool]) -> bool:
        with generation.lock(self.settings.output_dir), sftp.session(self.device) as client:
            stick = sftp.enter_stick(client, self.root, mark=False)
            state = sftp.StickState(self.device.state_dir, stick)
            installed = sftp.pull(client, state, usb.DATABASE)
            review = usb.review(self.settings.library, installed.snapshot)
            if not review.selected or not confirm(review):
                return False
            self._check_target(client, stick)
            installed = sftp.pull(client, state, usb.DATABASE)
            usb.apply_review(self.settings.library, installed.snapshot, review.approval)
            if stick is not None:
                state.accept(installed.sha256)
            return True

    def export(
        self,
        name: str,
        desired: set[PlaylistPath],
        inspected: tuple[Playlists, Playlists],
        confirm: Callable[[sftp.PushResult, str | None], bool],
        progress: Callable[[str, int, int], None] | None = None,
    ) -> sftp.PushResult:
        output = self.settings.output_dir
        with (
            generation.lock(output),
            sftp.session(self.device) as client,
            TemporaryDirectory(dir=output) as directory,
        ):
            work = Path(directory)
            stick = sftp.enter_stick(client, self.root, mark=False)
            state = sftp.StickState(self.device.state_dir, stick, name)
            export = generation.current(output / name)
            source = self.settings.library / "Database2/m.db"
            reviewed: str | None = None
            if name == "engine":
                current = playlists(capture(export.local(usb.DATABASE)).playlists)
                prepared = export.path / "source.sha256"
                source_hash = prepared.read_text() if prepared.is_file() else ""
                installed = self._engine(client, state)
                if installed is not None:
                    reviewed = installed.sha256
                self._fresh(source, source_hash)
                remote = (
                    {} if installed is None else playlists(capture(installed.snapshot).playlists)
                )
                self._check_selection(desired, inspected, (current, remote))
                export = usb.adopt(
                    export,
                    installed.snapshot if installed else None,
                    work / "engine",
                    frozenset(desired),
                )
            else:
                current = pioneer.inspect(export.tree)
                remote = pioneer.inspect_stick(client, state, work / "stick")
                self._check_selection(desired, inspected, (current, remote))
                snapshot_path = export.path / "snapshot.json"
                if not snapshot_path.is_file():
                    raise generation.GenerationError(
                        "Refresh Pioneer exports before selecting playlists"
                    )
                snapshot = loads(snapshot_path.read_text())
                source_hash = snapshot.sha256
                self._fresh(source, source_hash)
                export = pioneer.assemble(
                    _subset(snapshot, desired), self.settings.library, output / name, work
                )

            def approve(plan: sftp.PushResult) -> bool:
                if not plan.files or not confirm(
                    plan,
                    reviewed
                    if reviewed != state.hashes("installed.json").get(usb.DATABASE)
                    else None,
                ):
                    return False
                self._fresh(source, source_hash)
                self._check_target(client, stick)
                if name == "engine":
                    actual = self._engine(client, state)
                    if (actual.sha256 if actual else None) != reviewed:
                        raise sftp.DeliveryError("Stick database changed; preview again")
                return True

            def register() -> sftp.StickState:
                root = client.getcwd()
                assert root is not None
                return sftp.StickState(
                    self.device.state_dir, sftp.enter_stick(client, root, mark=True), name
                )

            return sftp.push(
                client,
                export,
                state,
                apply=True,
                reviewed=reviewed,
                confirm=approve,
                progress=progress,
                register=register if stick is None else None,
            )

    def _check_target(self, client: SFTPClient, expected: UUID | None) -> None:
        root = client.getcwd()
        assert root is not None
        if sftp.enter_stick(client, root, mark=False) != expected:
            raise sftp.DeliveryError("Stick changed during confirmation; reopen Sync Manager")

    @staticmethod
    def _engine(client: SFTPClient, state: sftp.StickState) -> sftp.PullResult | None:
        try:
            return sftp.pull(client, state, usb.DATABASE)
        except FileNotFoundError:
            return None

    @staticmethod
    def _fresh(source: Path, digest: str) -> None:
        preflight_target(source)
        if generation.file_sha256(source) != digest:
            raise generation.GenerationError("Prepared export is outdated; refresh exports first")

    @staticmethod
    def _check_selection(
        desired: set[PlaylistPath],
        inspected: tuple[Playlists, Playlists],
        current: tuple[Playlists, Playlists],
    ) -> None:
        if inspected != current or desired - current[0].keys():
            raise generation.GenerationError(
                "Prepared or stick playlists changed; reopen Sync Manager"
            )
