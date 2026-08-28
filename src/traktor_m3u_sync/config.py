"""TOML configuration for traktor-m3u-sync."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Final, cast

DEFAULT_CONFIG_PATH: Final = Path("traktor-m3u-sync.toml")
DEFAULT_STORE_PATH: Final = Path("~/.local/state/traktor-m3u-sync/store.db")
DEFAULT_SANDBOX_NAME: Final = "Imported Playlists"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class LibraryConfig:
    traktor_root: PureWindowsPath
    m3u_root: PurePosixPath


@dataclass(frozen=True)
class StoreConfig:
    path: Path = DEFAULT_STORE_PATH


@dataclass(frozen=True)
class NmlConfig:
    # Required only for NML import/export commands, validated per command.
    collection_path: Path | None = None
    sandbox_name: str = DEFAULT_SANDBOX_NAME


@dataclass(frozen=True)
class M3uConfig:
    output_dir: Path | None = None
    import_dir: Path | None = None


@dataclass(frozen=True)
class ItunesConfig:
    # Required only for the iTunes export command, validated per command.
    output_file: Path | None = None
    base_path: Path | None = None


@dataclass(frozen=True)
class AppConfig:
    library: LibraryConfig
    nml: NmlConfig
    store: StoreConfig = StoreConfig()
    m3u: M3uConfig = M3uConfig()
    itunes: ItunesConfig = ItunesConfig()


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    expanded_path = path.expanduser()
    if not expanded_path.is_file():
        raise ConfigError(f"Config file not found: {expanded_path}")

    try:
        with expanded_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {expanded_path}: {exc}") from exc

    library_table = _require_table(raw, "library")
    store_table = _require_table(raw, "store")
    nml_table = _require_table(raw, "nml")
    m3u_table = _require_table(raw, "m3u")
    itunes_table = _optional_table(raw, "itunes")

    return AppConfig(
        library=LibraryConfig(
            traktor_root=PureWindowsPath(_require_string(library_table, "traktor_root", "library")),
            m3u_root=PurePosixPath(_require_string(library_table, "m3u_root", "library")),
        ),
        store=StoreConfig(
            path=_optional_path(store_table, "path", "store") or DEFAULT_STORE_PATH.expanduser()
        ),
        nml=NmlConfig(
            collection_path=_optional_path(nml_table, "collection_path", "nml"),
            sandbox_name=_optional_string(nml_table, "sandbox_name", "nml") or DEFAULT_SANDBOX_NAME,
        ),
        m3u=M3uConfig(
            output_dir=_optional_path(m3u_table, "output_dir", "m3u"),
            import_dir=_optional_path(m3u_table, "import_dir", "m3u"),
        ),
        itunes=ItunesConfig(
            output_file=_optional_path(itunes_table, "output_file", "itunes"),
            base_path=_optional_path(itunes_table, "base_path", "itunes"),
        ),
    )


def apply_import_overrides(
    config: AppConfig,
    *,
    format: str,
    store_path: Path | None = None,
    collection_path: Path | None = None,
    import_dir: Path | None = None,
) -> AppConfig:
    """Apply CLI overrides for `import` and validate what that command needs."""
    m3u = replace(config.m3u, import_dir=import_dir or config.m3u.import_dir)
    nml = _override_nml(config.nml, collection_path)
    if format == "m3u" and m3u.import_dir is None:
        raise ConfigError(
            "import_dir is required for M3U import: pass --import-dir or set [m3u].import_dir"
        )
    if format == "nml":
        _require_nml_collection(nml, "import")
    return replace(
        config,
        store=_override_store(config.store, store_path),
        nml=nml,
        m3u=m3u,
    )


def apply_export_overrides(
    config: AppConfig,
    *,
    format: str,
    store_path: Path | None = None,
    collection_path: Path | None = None,
    output_dir: Path | None = None,
    sandbox_name: str | None = None,
    output_file: Path | None = None,
    base_path: Path | None = None,
) -> AppConfig:
    """Apply CLI overrides for `export` and validate what that command needs."""
    m3u = replace(config.m3u, output_dir=output_dir or config.m3u.output_dir)
    if format == "m3u" and m3u.output_dir is None:
        raise ConfigError(
            "output_dir is required for M3U export: pass --output-dir or set [m3u].output_dir"
        )
    nml = _override_nml(config.nml, collection_path)
    if format == "nml":
        _require_nml_collection(nml, "export")
    itunes = ItunesConfig(
        output_file=(output_file.expanduser() if output_file else config.itunes.output_file),
        base_path=(base_path.expanduser() if base_path else config.itunes.base_path),
    )
    if format == "itunes":
        if itunes.output_file is None:
            raise ConfigError(
                "output_file is required for iTunes export: "
                "pass --output-file or set [itunes].output_file"
            )
        if itunes.base_path is None:
            raise ConfigError(
                "base_path is required for iTunes export: "
                "pass --base-path or set [itunes].base_path"
            )
        if not itunes.base_path.is_absolute():
            raise ConfigError(
                f"base_path must be an absolute path for iTunes export, got: {itunes.base_path}"
            )
    return replace(
        config,
        store=_override_store(config.store, store_path),
        nml=replace(nml, sandbox_name=sandbox_name or nml.sandbox_name),
        m3u=m3u,
        itunes=itunes,
    )


def _require_nml_collection(nml: NmlConfig, command: str) -> None:
    if nml.collection_path is None:
        raise ConfigError(
            f"collection_path is required for NML {command}: "
            "pass --collection or set [nml].collection_path"
        )


def _override_store(store: StoreConfig, store_path: Path | None) -> StoreConfig:
    return replace(store, path=(store_path or store.path).expanduser())


def _override_nml(nml: NmlConfig, collection_path: Path | None) -> NmlConfig:
    if collection_path is None:
        return nml
    return replace(nml, collection_path=collection_path.expanduser())


def _require_table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    table = raw.get(name)
    if not isinstance(table, dict):
        raise ConfigError(f"Missing required [{name}] table")
    return cast("dict[str, Any]", table)


def _optional_table(raw: dict[str, Any], name: str) -> dict[str, Any]:
    table = raw.get(name)
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise ConfigError(f"Field '{name}' must be a table")
    return cast("dict[str, Any]", table)


def _require_string(table: dict[str, Any], key: str, section: str) -> str:
    value = _optional_string(table, key, section)
    if value is None:
        raise ConfigError(f"Missing required string field '{key}' in [{section}]")
    return value


def _optional_string(table: dict[str, Any], key: str, section: str) -> str | None:
    value = table.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ConfigError(f"Field '{key}' in [{section}] must be a non-empty string")
    return value


def _optional_path(table: dict[str, Any], key: str, section: str) -> Path | None:
    value = _optional_string(table, key, section)
    return None if value is None else Path(value).expanduser()
