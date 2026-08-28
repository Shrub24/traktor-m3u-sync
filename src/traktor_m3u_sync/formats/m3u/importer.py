"""M3U importer: .m3u8 directory to store."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from ...contracts import AdapterWarning, ImportResult
from ...model import Playlist, Track
from ...model.identity import identify_playlists
from ...paths.m3u import M3uPathMapping, ReversePathTranslationError
from .parser import ParsedPlaylist, ParsedTrack, read_import_tree

FORMAT: Final[str] = "m3u"


@dataclass(frozen=True)
class M3uImporter:
    mapping: M3uPathMapping
    import_dir: Path

    def read(self) -> ImportResult:
        warnings: list[AdapterWarning] = []
        playlists: list[Playlist] = []

        for parsed in read_import_tree(self.import_dir):
            playlists.append(_to_playlist(parsed, self.mapping, warnings))

        identified, identity_warnings = identify_playlists(playlists)
        return ImportResult(playlists=identified, warnings=tuple(warnings) + identity_warnings)


def _to_playlist(
    parsed: ParsedPlaylist,
    mapping: M3uPathMapping,
    warnings: list[AdapterWarning],
) -> Playlist:
    return Playlist(
        name=parsed.name,
        folder_path=() if str(parsed.relative_dir) == "." else parsed.relative_dir.parts,
        tracks=tuple(_to_track(item, parsed.name, mapping, warnings) for item in parsed.tracks),
    )


def _to_track(
    item: ParsedTrack,
    playlist: str,
    mapping: M3uPathMapping,
    warnings: list[AdapterWarning],
) -> Track:
    try:
        path = mapping.to_rel_path(item.path)
    except ReversePathTranslationError as exc:
        warnings.append(
            AdapterWarning(
                code="path_translation_failed",
                message="Stored track with unmappable path as unresolved",
                playlist=playlist,
                detail=str(exc),
            )
        )
        return Track(
            title=item.title,
            artist=item.artist,
            raw_path=item.path,
            duration_seconds=item.duration_seconds,
        )
    return Track(
        title=item.title,
        artist=item.artist,
        path=path,
        raw_path=item.path,
        duration_seconds=item.duration_seconds,
    )
