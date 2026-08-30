"""Consumer-facing file: URI mapping, independent of the worker filesystem namespace."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote

# RFC 3986 reg-name; percent-escapes are validated separately before this match.
# No userinfo, port, or IPv6 literals: a file: base addresses an empty host,
# localhost, or a plain host/UNC server name.
_AUTHORITY_RE = re.compile(r"[A-Za-z0-9._~!$&'()*+,;=%-]+")
_INVALID_PCT_RE = re.compile(r"%(?![0-9A-Fa-f]{2})")


class FileUriError(ValueError):
    """Raised when a configured file: URI base is invalid."""


@dataclass(frozen=True)
class FileUriMapping:
    """Renders library-relative paths onto a complete absolute file: URI base."""

    base: str

    def __post_init__(self) -> None:
        text = self.base
        if not text.lower().startswith("file:"):
            raise FileUriError(f"location_base must be an absolute file: URI, got '{text}'")
        if any(ch <= " " or ch > "~" for ch in text):
            raise FileUriError(
                f"location_base must contain no whitespace or non-printable characters, "
                f"got '{text}'"
            )
        if "?" in text or "#" in text:
            raise FileUriError(f"location_base must not carry a query or fragment, got '{text}'")
        if _INVALID_PCT_RE.search(text):
            raise FileUriError(f"location_base has a malformed percent-escape, got '{text}'")
        rest = text[len("file:") :]
        if rest.startswith("//"):
            authority, slash, tail = rest[2:].partition("/")
            path = f"/{tail}" if slash else ""
        else:
            authority, path = "", rest
        if not path.startswith("/"):
            raise FileUriError(f"location_base must be an absolute file: URI, got '{text}'")
        if authority and not _AUTHORITY_RE.fullmatch(authority):
            raise FileUriError(f"location_base has an invalid file: URI authority, got '{text}'")
        object.__setattr__(self, "base", text.rstrip("/"))

    def to_uri(self, rel_path: str) -> str:
        """Append a library-relative POSIX path with UTF-8 percent encoding."""
        return f"{self.base}/{quote(rel_path, safe='/:')}"

    def music_folder(self) -> str:
        """The normalized base with a trailing slash."""
        return f"{self.base}/"
