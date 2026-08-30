"""TOML configuration for traktor-m3u-sync."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Final, cast

from .paths.uri import FileUriError, FileUriMapping

DEFAULT_CONFIG_PATH: Final = Path("traktor-m3u-sync.toml")
DEFAULT_STORE_PATH: Final = Path("~/.local/state/traktor-m3u-sync/store.db")
DEFAULT_SANDBOX_NAME: Final = "Imported Playlists"


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class StoreConfig:
    path: Path = DEFAULT_STORE_PATH


@dataclass(frozen=True)
class NmlConfig:
    # Required only for NML import/export commands, validated per command.
    library_root: PureWindowsPath | None = None
    collection_path: Path | None = None
    sandbox_name: str = DEFAULT_SANDBOX_NAME


@dataclass(frozen=True)
class M3uConfig:
    # Required only for M3U import/export commands, validated per command.
    library_root: PurePosixPath | None = None
    output_dir: Path | None = None
    import_dir: Path | None = None


@dataclass(frozen=True)
class ItunesConfig:
    # Required only for the iTunes export command, validated per command.
    # location_base is a complete absolute file: URI; check_base_path is the
    # optional worker-side mount used only for missing-file warnings.
    output_file: Path | None = None
    location_base: str | None = None
    check_base_path: Path | None = None


@dataclass(frozen=True)
class AppConfig:
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

    store_table = _require_table(raw, "store")
    nml_table = _optional_table(raw, "nml")
    m3u_table = _optional_table(raw, "m3u")
    itunes_table = _optional_table(raw, "itunes")

    nml_library_root = _optional_string(nml_table, "library_root", "nml")
    m3u_library_root = _optional_string(m3u_table, "library_root", "m3u")

    return AppConfig(
        store=StoreConfig(
            path=_optional_path(store_table, "path", "store") or DEFAULT_STORE_PATH.expanduser()
        ),
        nml=NmlConfig(
            library_root=PureWindowsPath(nml_library_root) if nml_library_root else None,
            collection_path=_optional_path(nml_table, "collection_path", "nml"),
            sandbox_name=_optional_string(nml_table, "sandbox_name", "nml") or DEFAULT_SANDBOX_NAME,
        ),
        m3u=M3uConfig(
            library_root=PurePosixPath(m3u_library_root) if m3u_library_root else None,
            output_dir=_optional_path(m3u_table, "output_dir", "m3u"),
            import_dir=_optional_path(m3u_table, "import_dir", "m3u"),
        ),
        itunes=ItunesConfig(
            output_file=_optional_path(itunes_table, "output_file", "itunes"),
            location_base=_optional_string(itunes_table, "location_base", "itunes"),
            check_base_path=_optional_path(itunes_table, "check_base_path", "itunes"),
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
    if format == "m3u":
        if m3u.import_dir is None:
            raise ConfigError(
                "import_dir is required for M3U import: pass --import-dir or set [m3u].import_dir"
            )
        _require_m3u_root(m3u, "import")
    if format == "nml":
        _require_nml_collection(nml, "import")
        _require_nml_root(nml, "import")
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
    location_base: str | None = None,
    check_base_path: Path | None = None,
) -> AppConfig:
    """Apply CLI overrides for `export` and validate what that command needs."""
    m3u = replace(config.m3u, output_dir=output_dir or config.m3u.output_dir)
    if format == "m3u":
        if m3u.output_dir is None:
            raise ConfigError(
                "output_dir is required for M3U export: pass --output-dir or set [m3u].output_dir"
            )
        _require_m3u_root(m3u, "export")
    nml = _override_nml(config.nml, collection_path)
    if format == "nml":
        _require_nml_collection(nml, "export")
        _require_nml_root(nml, "export")
    itunes = ItunesConfig(
        output_file=(output_file.expanduser() if output_file else config.itunes.output_file),
        location_base=location_base or config.itunes.location_base,
        check_base_path=(
            check_base_path.expanduser() if check_base_path else config.itunes.check_base_path
        ),
    )
    if format == "itunes":
        if itunes.output_file is None:
            raise ConfigError(
                "output_file is required for iTunes export: "
                "pass --output-file or set [itunes].output_file"
            )
        if itunes.location_base is None:
            raise ConfigError(
                "location_base is required for iTunes export: "
                "pass --location-base or set [itunes].location_base"
            )
        try:
            FileUriMapping(itunes.location_base)
        except FileUriError as exc:
            raise ConfigError(str(exc)) from exc
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


def _require_nml_root(nml: NmlConfig, command: str) -> None:
    if nml.library_root is None:
        raise ConfigError(f"library_root is required for NML {command}: set [nml].library_root")


def _require_m3u_root(m3u: M3uConfig, command: str) -> None:
    if m3u.library_root is None:
        raise ConfigError(f"library_root is required for M3U {command}: set [m3u].library_root")


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
