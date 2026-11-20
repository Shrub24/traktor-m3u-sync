"""TOML configuration for traktor-m3u-sync."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Final, cast
from uuid import UUID

from .paths.uri import FileUriError, FileUriMapping

DEFAULT_CONFIG_PATH: Final = Path("traktor-m3u-sync.toml")
DEFAULT_STORE_PATH: Final = Path("~/.local/state/traktor-m3u-sync/store.db")
DEFAULT_SANDBOX_NAME: Final = "Imported Playlists"
DEFAULT_ENGINE_TRACK_PATH_PREFIX: Final = ".."
DEFAULT_ENGINE_MANAGED_ROOT: Final = "Playlist Sync"


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
class LibraryXmlConfig:
    # One library XML export target ([itunes] or [rekordbox]), validated only when its
    # format is selected. location_base is a complete absolute file: URI; check_base_path
    # is the optional worker-side mount used only for missing-file warnings.
    output_file: Path | None = None
    location_base: str | None = None
    check_base_path: Path | None = None


@dataclass(frozen=True)
class EngineConfig:
    # Required only for the Engine export command, validated per command.
    # database_path must point at an existing Engine DJ media-drive m.db;
    # check_base_path is the optional worker-side library mount used for
    # missing-file warnings and for inserting tracks Engine does not know yet.
    database_path: Path | None = None
    track_path_prefix: str = DEFAULT_ENGINE_TRACK_PATH_PREFIX
    managed_root: str = DEFAULT_ENGINE_MANAGED_ROOT
    check_base_path: Path | None = None


@dataclass(frozen=True)
class AppConfig:
    nml: NmlConfig
    store: StoreConfig = StoreConfig()
    m3u: M3uConfig = M3uConfig()
    itunes: LibraryXmlConfig = LibraryXmlConfig()
    rekordbox: LibraryXmlConfig = LibraryXmlConfig()
    engine: EngineConfig = EngineConfig()


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    raw = _read_toml(path)
    store_table = _require_table(raw, "store")
    nml_table = _optional_table(raw, "nml")
    m3u_table = _optional_table(raw, "m3u")
    engine_table = _optional_table(raw, "engine")

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
        itunes=_library_xml(raw, "itunes"),
        rekordbox=_library_xml(raw, "rekordbox"),
        engine=EngineConfig(
            database_path=_optional_path(engine_table, "database_path", "engine"),
            track_path_prefix=(
                _optional_string(engine_table, "track_path_prefix", "engine")
                or DEFAULT_ENGINE_TRACK_PATH_PREFIX
            ),
            managed_root=(
                _optional_string(engine_table, "managed_root", "engine")
                or DEFAULT_ENGINE_MANAGED_ROOT
            ),
            check_base_path=_optional_path(engine_table, "check_base_path", "engine"),
        ),
    )


@dataclass(frozen=True)
class EngineUsbConfig:
    library: Path
    output_dir: Path
    # Top-level Engine playlist to export with its descendants; None exports every playlist.
    playlist_root: str | None = None


@dataclass(frozen=True)
class UsbDeviceConfig:
    host: str
    user: str
    key_file: Path
    known_hosts: Path
    remote_root: str
    stick: UUID
    state_dir: Path
    port: int = 22


def load_engine_usb_config(path: Path) -> EngineUsbConfig:
    table = _usb_table(path, "engine")
    library = _optional_path(table, "library", "usb.engine")
    output_dir = _optional_path(table, "output_dir", "usb.engine")
    if library is None or output_dir is None:
        raise ConfigError("[usb.engine] requires library and output_dir")
    return EngineUsbConfig(
        library, output_dir, _optional_string(table, "playlist_root", "usb.engine")
    )


def load_usb_device_config(path: Path) -> UsbDeviceConfig:
    table = _usb_table(path, "device")
    section = "usb.device"
    values = {
        key: _optional_string(table, key, section)
        for key in ("host", "user", "key_file", "known_hosts", "remote_root", "stick", "state_dir")
    }
    missing = sorted(key for key, value in values.items() if value is None)
    if missing:
        raise ConfigError(f"[{section}] requires {', '.join(missing)}")
    port = table.get("port", 22)
    if isinstance(port, bool) or not isinstance(port, int) or not 0 < port < 65536:
        raise ConfigError(f"Field 'port' in [{section}] must be a TCP port")
    try:
        stick = UUID(cast(str, values["stick"]))
    except ValueError as exc:
        raise ConfigError(f"Field 'stick' in [{section}] must be a UUID") from exc
    return UsbDeviceConfig(
        host=cast(str, values["host"]),
        user=cast(str, values["user"]),
        key_file=Path(cast(str, values["key_file"])).expanduser(),
        known_hosts=Path(cast(str, values["known_hosts"])).expanduser(),
        remote_root=cast(str, values["remote_root"]),
        stick=stick,
        state_dir=Path(cast(str, values["state_dir"])).expanduser(),
        port=port,
    )


def _usb_table(path: Path, name: str) -> dict[str, Any]:
    """USB commands read only their own [usb.<name>] table, not the playlist store config."""
    return _require_table(_require_table(_read_toml(path), "usb"), name)


def _read_toml(path: Path) -> dict[str, Any]:
    expanded_path = path.expanduser()
    if not expanded_path.is_file():
        raise ConfigError(f"Config file not found: {expanded_path}")
    try:
        with expanded_path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Invalid TOML in {expanded_path}: {exc}") from exc


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
    engine_database: Path | None = None,
    engine_track_prefix: str | None = None,
    engine_managed_root: str | None = None,
    engine_check_base_path: Path | None = None,
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
    library_xml = {"itunes": config.itunes, "rekordbox": config.rekordbox}
    selected = library_xml.get(format)
    if selected is not None:
        selected = LibraryXmlConfig(
            output_file=output_file.expanduser() if output_file else selected.output_file,
            location_base=location_base or selected.location_base,
            check_base_path=(
                check_base_path.expanduser() if check_base_path else selected.check_base_path
            ),
        )
        _require_library_xml(selected, format)
        library_xml[format] = selected
    engine = EngineConfig(
        database_path=(
            engine_database.expanduser() if engine_database else config.engine.database_path
        ),
        track_path_prefix=engine_track_prefix or config.engine.track_path_prefix,
        managed_root=engine_managed_root or config.engine.managed_root,
        check_base_path=(
            engine_check_base_path.expanduser()
            if engine_check_base_path
            else config.engine.check_base_path
        ),
    )
    if format == "engine" and engine.database_path is None:
        raise ConfigError(
            "database_path is required for Engine export: "
            "pass --engine-database or set [engine].database_path"
        )
    return replace(
        config,
        store=_override_store(config.store, store_path),
        nml=replace(nml, sandbox_name=sandbox_name or nml.sandbox_name),
        m3u=m3u,
        itunes=library_xml["itunes"],
        rekordbox=library_xml["rekordbox"],
        engine=engine,
    )


def _library_xml(raw: dict[str, Any], section: str) -> LibraryXmlConfig:
    table = _optional_table(raw, section)
    return LibraryXmlConfig(
        output_file=_optional_path(table, "output_file", section),
        location_base=_optional_string(table, "location_base", section),
        check_base_path=_optional_path(table, "check_base_path", section),
    )


def _require_library_xml(config: LibraryXmlConfig, section: str) -> None:
    label = _LIBRARY_XML_LABELS[section]
    if config.output_file is None:
        raise ConfigError(
            f"output_file is required for {label} export: "
            f"pass --output-file or set [{section}].output_file"
        )
    if config.location_base is None:
        raise ConfigError(
            f"location_base is required for {label} export: "
            f"pass --location-base or set [{section}].location_base"
        )
    try:
        FileUriMapping(config.location_base)
    except FileUriError as exc:
        raise ConfigError(str(exc)) from exc


_LIBRARY_XML_LABELS: Final[dict[str, str]] = {"itunes": "iTunes", "rekordbox": "rekordbox"}


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
