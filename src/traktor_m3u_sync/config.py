from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

DEFAULT_CONFIG_PATH = Path("traktor-m3u-sync.toml")


class ConfigError(ValueError):
    """Raised when configuration is missing or invalid."""


@dataclass(frozen=True)
class LibraryConfig:
    traktor_root: PureWindowsPath
    m3u_root: PurePosixPath


@dataclass(frozen=True)
class ExportConfig:
    collection_path: Path
    output_dir: Path


@dataclass(frozen=True)
class AppConfig:
    library: LibraryConfig
    export: ExportConfig


def load_config(config_path: Path | None = None) -> AppConfig:
    path = (config_path or DEFAULT_CONFIG_PATH).expanduser()
    try:
        with path.open("rb") as handle:
            raw_config = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc

    return _parse_config(raw_config, source_path=path)


def apply_export_overrides(
    config: AppConfig,
    *,
    collection_path: Path | None,
    output_dir: Path | None,
) -> AppConfig:
    return AppConfig(
        library=config.library,
        export=ExportConfig(
            collection_path=(collection_path or config.export.collection_path).expanduser(),
            output_dir=(output_dir or config.export.output_dir).expanduser(),
        ),
    )


def _parse_config(raw_config: dict[str, Any], *, source_path: Path) -> AppConfig:
    library = _require_table(raw_config, "library", source_path=source_path)
    export = _require_table(raw_config, "export", source_path=source_path)

    traktor_root = _require_string(library, "traktor_root", source_path=source_path)
    m3u_root = _require_string(library, "m3u_root", source_path=source_path)
    collection_path = _require_string(export, "collection_path", source_path=source_path)
    output_dir = _require_string(export, "output_dir", source_path=source_path)

    return AppConfig(
        library=LibraryConfig(
            traktor_root=_parse_windows_path(traktor_root),
            m3u_root=_parse_posix_path(m3u_root),
        ),
        export=ExportConfig(
            collection_path=Path(collection_path).expanduser(),
            output_dir=Path(output_dir).expanduser(),
        ),
    )


def _require_table(
    raw_config: dict[str, Any],
    key: str,
    *,
    source_path: Path,
) -> dict[str, Any]:
    value = raw_config.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing required [{key}] table in {source_path}")
    typed_value = cast(dict[object, object], value)
    return {str(inner_key): inner_value for inner_key, inner_value in typed_value.items()}


def _require_string(raw_table: dict[str, Any], key: str, *, source_path: Path) -> str:
    value = raw_table.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Missing required string field '{key}' in {source_path}")
    return value


def _parse_windows_path(value: str) -> PureWindowsPath:
    return PureWindowsPath(value.replace("/", "\\"))


def _parse_posix_path(value: str) -> PurePosixPath:
    return PurePosixPath(value.replace("\\", "/"))
