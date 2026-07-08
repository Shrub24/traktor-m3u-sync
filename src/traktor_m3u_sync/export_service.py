from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .m3u_writer import write_m3u8
from .nml_reader import load_collection
from .pathmap import PathTranslationError, translate_track_path
from .playlist_tree import ExportTrack, ExportWarning, extract_playlist_nodes, sanitize_component


@dataclass(frozen=True)
class ExportSummary:
    playlists_written: int
    tracks_exported: int
    warnings_emitted: int


@dataclass(frozen=True)
class ExportResult:
    summary: ExportSummary
    warnings: tuple[ExportWarning, ...]
    output_files: tuple[Path, ...]


@dataclass(frozen=True)
class ExportPlaylist:
    folder_parts: tuple[str, ...]
    playlist_name: str
    tracks: tuple[ExportTrack, ...]


def run_export(config: AppConfig) -> ExportResult:
    collection = load_collection(config.export.collection_path)
    playlist_nodes, warnings = extract_playlist_nodes(collection.nml)

    materialized_playlists: list[ExportPlaylist] = []
    for playlist_node in playlist_nodes:
        translated_tracks: list[ExportTrack] = []
        playlist_label = "/".join((*playlist_node.folder_parts, playlist_node.playlist_name))

        for track in playlist_node.tracks:
            try:
                translated_path = translate_track_path(track, config.library)
            except PathTranslationError as exc:
                warnings.append(
                    ExportWarning(
                        code="path_translation_failed",
                        message="Skipping track with unmappable path",
                        playlist=playlist_label,
                        detail=str(exc),
                    )
                )
                continue

            translated_tracks.append(
                ExportTrack(
                    path=translated_path,
                    title=track.title,
                    artist=track.artist,
                    duration_seconds=track.duration_seconds,
                )
            )

        materialized_playlists.append(
            ExportPlaylist(
                folder_parts=playlist_node.folder_parts,
                playlist_name=playlist_node.playlist_name,
                tracks=tuple(translated_tracks),
            )
        )

    output_files: list[Path] = []
    tracks_exported = 0
    for playlist in materialized_playlists:
        output_path = _playlist_output_path(config.export.output_dir, playlist)
        write_m3u8(output_path, playlist.tracks)
        output_files.append(output_path)
        tracks_exported += len(playlist.tracks)

    return ExportResult(
        summary=ExportSummary(
            playlists_written=len(output_files),
            tracks_exported=tracks_exported,
            warnings_emitted=len(warnings),
        ),
        warnings=tuple(warnings),
        output_files=tuple(output_files),
    )


def _playlist_output_path(output_dir: Path, playlist: ExportPlaylist) -> Path:
    folder_path = output_dir.joinpath(*(sanitize_component(part) for part in playlist.folder_parts))
    file_name = f"{sanitize_component(playlist.playlist_name)}.m3u8"
    return folder_path / file_name
