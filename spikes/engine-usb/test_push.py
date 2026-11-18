"""Run with Python + Paramiko and pass the path to OpenSSH sftp-server."""

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

from paramiko import SFTPClient
from push import ENGINE_DATABASE, manifest, push


class TestSocket(socket.socket):
    def get_name(self) -> str:
        return "local SFTP test"


class Client(SFTPClient):
    blocked = ""
    reject_replace = False

    def posix_rename(self, oldpath: str, newpath: str) -> None:
        if self.reject_replace:
            raise OSError("unsupported replacement")
        super().posix_rename(oldpath, newpath)

    def rename(self, oldpath: str, newpath: str) -> None:
        if newpath == self.blocked:
            raise OSError("interrupted before asset publication")
        super().rename(oldpath, newpath)


def exercise(sftp: Client, root: Path, stick: Path) -> None:
    tree, state = root / "tree", root / "state"
    state.mkdir()
    asset = "Engine Library/Music/10/a.mp3"
    new = "Engine Library/Music/11/b.mp3"
    db = stick / ENGINE_DATABASE

    def put(path: str, content: bytes) -> None:
        file = tree / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)

    def sync(*, apply: bool = True) -> None:
        push(sftp, tree, state, ENGINE_DATABASE, manifest(tree, ENGINE_DATABASE), apply=apply)

    def fails(message: str) -> None:
        try:
            sync()
        except (OSError, ValueError) as exc:
            assert message in str(exc), exc
        else:
            raise AssertionError(f"Expected failure: {message}")

    put(ENGINE_DATABASE, b"db1")
    put(asset, b"audio1")
    sync(apply=False)
    assert not db.exists()
    sync()
    assert db.read_bytes() == b"db1"
    os.utime(stick / asset, (100, 100))
    sync()
    assert (stick / asset).stat().st_mtime == 100
    put(new, b"audio2")
    put(ENGINE_DATABASE, b"db2")
    sftp.reject_replace = True
    fails("cannot replace an existing file")
    assert db.read_bytes() == b"db1" and not (stick / new).exists()
    sftp.reject_replace = False
    sftp.blocked = new
    fails("interrupted")
    assert db.read_bytes() == b"db1" and not (stick / new).exists()
    sftp.blocked = ""
    sync()
    assert db.read_bytes() == b"db2" and (stick / new).read_bytes() == b"audio2"
    put(asset, b"audio3")
    put(ENGINE_DATABASE, b"db3")
    fails("active asset")
    assert (stick / asset).read_bytes() == b"audio1"
    db.write_bytes(b"player edits")
    fails("Unrecognized stick database")
    assert b"player edits" in [path.read_bytes() for path in state.glob("*.db")]
    assert db.read_bytes() == b"player edits"


if __name__ == "__main__":
    peer, server = socket.socketpair()
    with tempfile.TemporaryDirectory() as tmp, TestSocket(fileno=peer.detach()) as client, server:
        root = Path(tmp)
        stick = root / "stick"
        stick.mkdir()
        with subprocess.Popen([sys.argv[1], "-d", str(stick)], stdin=server, stdout=server) as proc:
            server.close()
            try:
                with Client(client) as sftp:
                    exercise(sftp, root, stick)
            finally:
                client.close()
                assert proc.wait(timeout=5) == 0
    print("SFTP delivery checks passed")
