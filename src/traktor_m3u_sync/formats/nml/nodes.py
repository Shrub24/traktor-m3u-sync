"""Build and validate the NML sandbox subtree."""

from __future__ import annotations

from dataclasses import dataclass

from traktor_nml_utils.models.collection import (
    Entrytype,
    Nml,
    Nodetype,
    Playlisttype,
    Primarykeytype,
    Subnodestype,
)


class SandboxValidationError(RuntimeError):
    """Raised when the sandbox subtree cannot be built or reloaded correctly."""


@dataclass(frozen=True)
class PlaylistEntry:
    folder_path: tuple[str, ...]
    name: str
    entries: tuple[Entrytype, ...]

    @property
    def label(self) -> str:
        return "/".join((*self.folder_path, self.name))


def rebuild_sandbox(
    nml: Nml, sandbox_name: str, playlists: tuple[PlaylistEntry, ...]
) -> list[Nodetype]:
    """Replace the sandbox folder under $ROOT with nodes built from the given playlists."""
    if nml.playlists is None or nml.playlists.node is None:
        raise SandboxValidationError("Collection has no PLAYLISTS section")

    root_node = nml.playlists.node
    if root_node.subnodes is None:
        root_node.subnodes = Subnodestype(node=[], count=0)

    sandbox_nodes = build_sandbox_nodes(playlists)
    root_node.subnodes.node = [
        child
        for child in root_node.subnodes.node
        if not (child.type == "FOLDER" and child.name == sandbox_name)
    ]
    root_node.subnodes.node.append(
        Nodetype(
            type="FOLDER",
            name=sandbox_name,
            subnodes=Subnodestype(node=sandbox_nodes, count=len(sandbox_nodes)),
        )
    )
    root_node.subnodes.count = len(root_node.subnodes.node)
    return sandbox_nodes


def build_sandbox_nodes(playlists: tuple[PlaylistEntry, ...]) -> list[Nodetype]:
    """Turn folder-pathed playlists into the sandbox node list, preserving first-seen order."""
    return _nodes_at_depth(list(playlists), depth=0)


def subtree_playlists(nodes: list[Nodetype], *, prefix: str = "") -> list[tuple[str, list[str]]]:
    """Ordered (label, PRIMARYKEY keys) pairs for every playlist in a subtree, in tree order."""
    found: list[tuple[str, list[str]]] = []
    for node in nodes:
        label = f"{prefix}/{node.name or 'unnamed'}"
        if node.type == "PLAYLIST":
            entries = node.playlist.entry if node.playlist is not None else []
            keys = [str(entry.primarykey.key) if entry.primarykey else "" for entry in entries]
            found.append((label, keys))
        elif node.subnodes is not None:
            found.extend(subtree_playlists(node.subnodes.node, prefix=label))
    return found


def _nodes_at_depth(items: list[PlaylistEntry], depth: int) -> list[Nodetype]:
    children: dict[str | None, list[PlaylistEntry]] = {}
    for playlist in items:
        key = playlist.folder_path[depth] if depth < len(playlist.folder_path) else None
        children.setdefault(key, []).append(playlist)

    nodes: list[Nodetype] = []
    for name, bucket in children.items():
        if name is None:
            nodes.extend(_playlist_node(p.name, p.entries) for p in bucket)
            continue
        subnodes = _nodes_at_depth(bucket, depth + 1)
        nodes.append(
            Nodetype(
                type="FOLDER",
                name=name,
                subnodes=Subnodestype(node=subnodes, count=len(subnodes)),
            )
        )
    return nodes


def count_playlists(nodes: list[Nodetype]) -> int:
    """Count PLAYLIST nodes across a full subtree."""
    total = 0
    for node in nodes:
        if node.type == "PLAYLIST":
            total += 1
        elif node.subnodes is not None:
            total += count_playlists(node.subnodes.node)
    return total


def count_tracks(node: Nodetype) -> int:
    """Count all tracks in a node and its children recursively."""
    if node.type == "PLAYLIST" and node.playlist is not None:
        return len(node.playlist.entry)
    if node.subnodes is not None:
        return sum(count_tracks(child) for child in node.subnodes.node)
    return 0


def find_sandbox(root_node: Nodetype, sandbox_name: str) -> Nodetype | None:
    if root_node.subnodes is None:
        return None
    return next(
        (
            child
            for child in root_node.subnodes.node
            if child.type == "FOLDER" and child.name == sandbox_name
        ),
        None,
    )


def validate_node_structure(node: Nodetype, *, path: str) -> int:
    """Recursively validate node structure, returning the playlist count."""
    if node.type == "PLAYLIST":
        if node.playlist is None:
            raise SandboxValidationError(f"PLAYLIST node at '{path}' has no playlist data")
        return 1

    if node.type == "FOLDER":
        if node.subnodes is None:
            raise SandboxValidationError(f"FOLDER node at '{path}' has no subnodes")
        return sum(
            validate_node_structure(child, path=f"{path}/{child.name or f'[index {i}]'}")
            for i, child in enumerate(node.subnodes.node)
        )

    raise SandboxValidationError(f"unexpected node type '{node.type}' at '{path}'")


def primarykey_entry(primarykey: str) -> Entrytype:
    return Entrytype(primarykey=Primarykeytype(type="TRACK", key=primarykey))


def _playlist_node(name: str, entries: tuple[Entrytype, ...]) -> Nodetype:
    return Nodetype(
        type="PLAYLIST",
        name=name,
        playlist=Playlisttype(entry=list(entries), entries=len(entries), type="LIST"),
    )
