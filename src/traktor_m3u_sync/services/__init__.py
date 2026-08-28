"""Import and export orchestration: adapters in, store out, store in, adapters out."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Final

from ..config import AppConfig, ConfigError
from ..contracts import Exporter, Importer, ImportResult, SyncResult
from ..formats import itunes, m3u, nml
from ..paths.m3u import M3uPathMapping
from ..paths.traktor import TraktorPathMapping
from ..store import PlaylistStore, StoreNotPopulatedError

SUPPORTED_IMPORT_FORMATS: Final[tuple[str, ...]] = ("nml", "m3u")
SUPPORTED_EXPORT_FORMATS: Final[tuple[str, ...]] = ("m3u", "nml", "itunes")


class UnknownFormatError(ValueError):
    """Raised when a CLI format selector has no registered adapter."""


def run_import(config: AppConfig, format: str) -> SyncResult:
    """Read one source format wholesale and rebuild the store snapshot."""
    result = _importer_for(config, format).read()
    with PlaylistStore(config.store.path) as store:
        store.rebuild(result.playlists)
    return SyncResult(counts=_import_counts(result), warnings=result.warnings)


def run_export(config: AppConfig, format: str, *, dry_run: bool = False) -> SyncResult:
    """Write the store snapshot to one target format using exporters only."""
    _exporter_for(config, format)
    opener = PlaylistStore.open_readonly if dry_run else PlaylistStore.open
    with opener(config.store) as store:
        if store.count_playlists() == 0:
            raise StoreNotPopulatedError(
                f"Store at {config.store.path} holds no playlists; run import first"
            )
        playlists = store.load_playlists()
    if dry_run:
        with tempfile.TemporaryDirectory(prefix=f"traktor-m3u-sync-{format}-dry-run-") as sandbox:
            sandboxed = _dry_run_config(config, format, Path(sandbox))
            result = _exporter_for(sandboxed, format).write(playlists)
    else:
        result = _exporter_for(config, format).write(playlists)
    return SyncResult(counts=result.counts, warnings=result.warnings)


def _dry_run_config(config: AppConfig, format: str, sandbox: Path) -> AppConfig:
    """Point the export target at an isolated sandbox; real exporter runs unchanged."""
    if format == "m3u":
        return replace(config, m3u=replace(config.m3u, output_dir=sandbox / "m3u"))
    if format == "itunes":
        return replace(config, itunes=replace(config.itunes, output_file=sandbox / "Library.xml"))
    collection = _require(config.nml.collection_path, "collection_path")
    copy = sandbox / collection.name
    if collection.is_file():
        shutil.copy2(collection, copy)
    return replace(config, nml=replace(config.nml, collection_path=copy))


def _import_counts(result: ImportResult) -> Mapping[str, int]:
    tracks = [track for playlist in result.playlists for track in playlist.tracks]
    return {
        "playlists_imported": len(result.playlists),
        "tracks_stored": len(tracks),
        "tracks_skipped": sum(1 for track in tracks if not track.resolved),
        "warnings_emitted": len(result.warnings),
    }


def _importer_for(config: AppConfig, format: str) -> Importer:
    factory = _IMPORTERS.get(format)
    if factory is None:
        raise UnknownFormatError(_unknown(format, SUPPORTED_IMPORT_FORMATS, "import"))
    return factory(config)


def _exporter_for(config: AppConfig, format: str) -> Exporter:
    factory = _EXPORTERS.get(format)
    if factory is None:
        raise UnknownFormatError(_unknown(format, SUPPORTED_EXPORT_FORMATS, "export"))
    return factory(config)


def _unknown(format: str, supported: tuple[str, ...], command: str) -> str:
    return f"Unsupported format '{format}' for {command}; supported formats: {', '.join(supported)}"


_IMPORTERS: Final[Mapping[str, Callable[[AppConfig], Importer]]] = {
    "nml": lambda config: nml.NmlImporter(
        TraktorPathMapping(config.library),
        _require(config.nml.collection_path, "collection_path"),
    ),
    "m3u": lambda config: m3u.M3uImporter(
        M3uPathMapping(config.library), _require(config.m3u.import_dir, "import_dir")
    ),
}

_EXPORTERS: Final[Mapping[str, Callable[[AppConfig], Exporter]]] = {
    "m3u": lambda config: m3u.M3uExporter(
        TraktorPathMapping(config.library), _require(config.m3u.output_dir, "output_dir")
    ),
    "nml": lambda config: nml.NmlExporter(
        TraktorPathMapping(config.library),
        _require(config.nml.collection_path, "collection_path"),
        config.nml.sandbox_name,
    ),
    "itunes": lambda config: itunes.ItunesExporter(
        _require(config.itunes.base_path, "base_path"),
        _require(config.itunes.output_file, "output_file"),
    ),
}


def _require(path: Path | None, field: str) -> Path:
    if path is None:
        raise ConfigError(f"{field} is required for this command")
    return path
