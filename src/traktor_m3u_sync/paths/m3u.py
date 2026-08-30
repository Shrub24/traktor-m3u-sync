"""M3U path space: relative/absolute file entries to library-relative."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from ..model.identity import to_posix


class ReversePathTranslationError(ValueError):
    """Raised when an M3U path cannot be mapped into library space."""


@dataclass(frozen=True)
class M3uPathMapping:
    library_root: PurePosixPath

    def to_rel_path(self, path_text: str) -> str:
        """Strip the M3U root prefix from a parsed entry path."""
        posix_path = PurePosixPath(to_posix(path_text))
        return _strip_root_prefix(posix_path, self.library_root).as_posix()

    def to_full_path(self, rel_path: str) -> str:
        """Render a library-relative path as an M3U entry line."""
        return self.library_root.joinpath(*PurePosixPath(rel_path).parts).as_posix()


def _strip_root_prefix(posix_path: PurePosixPath, m3u_root: PurePosixPath) -> PurePosixPath:
    m3u_parts = m3u_root.parts

    if not m3u_parts:
        return posix_path

    if m3u_root.is_absolute():
        if not posix_path.is_absolute():
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' is relative but m3u_root '{m3u_root}' is absolute"
            )
        path_parts = _collapse_absolute(posix_path).parts
        if len(path_parts) < len(m3u_parts):
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' is shorter than configured m3u_root '{m3u_root}'"
            )
        if path_parts[: len(m3u_parts)] != m3u_parts:
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' does not start with configured m3u_root '{m3u_root}'"
            )
        relative = PurePosixPath(*path_parts[len(m3u_parts) :])
        if ".." in relative.parts:
            raise ReversePathTranslationError(
                f"M3U path '{posix_path}' escapes configured m3u_root '{m3u_root}'"
            )
        return relative

    resolved_root = _resolve_relative_posix(m3u_root)
    resolved_path = _resolve_relative_posix(posix_path)
    root_parts = resolved_root.parts
    rp_parts = resolved_path.parts

    if len(rp_parts) < len(root_parts):
        raise ReversePathTranslationError(
            f"M3U path '{posix_path}' is shorter than resolved m3u_root '{m3u_root}'"
        )
    if rp_parts[: len(root_parts)] != root_parts:
        raise ReversePathTranslationError(
            f"M3U path '{posix_path}' does not fall beneath resolved m3u_root '{m3u_root}'"
        )
    return PurePosixPath(*rp_parts[len(root_parts) :])


def _resolve_relative_posix(path: PurePosixPath) -> PurePosixPath:
    """Collapse leading '..' segments by removing them and one preceding segment."""
    resolved: list[str] = []
    for part in path.parts:
        if part == ".." and resolved:
            resolved.pop()
        elif part != ".":
            resolved.append(part)
    return PurePosixPath(*resolved) if resolved else PurePosixPath("")


def _collapse_absolute(path: PurePosixPath) -> PurePosixPath:
    """Syntactically resolve '.' and '..' segments; '..' above '/' is clamped."""
    collapsed: list[str] = []
    for part in path.parts[1:]:
        if part == ".":
            continue
        if part == "..":
            if collapsed:
                collapsed.pop()
        else:
            collapsed.append(part)
    return PurePosixPath("/", *collapsed)
