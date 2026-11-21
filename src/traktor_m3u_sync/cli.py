"""Typer CLI entry point for traktor-m3u-sync."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path

import typer

from .config import (
    DEFAULT_CONFIG_PATH,
    AppConfig,
    ConfigError,
    apply_export_overrides,
    apply_import_overrides,
    load_config,
    load_usb_config,
    load_usb_device_config,
)
from .contracts import AdapterWarning, SyncResult
from .formats.engine import usb
from .formats.engine.analysis import managed_analysis_saved
from .formats.engine.performance import capture
from .formats.engine.start_cues import prepare
from .formats.rekordbox.performance import write_snapshot
from .model.performance import select
from .paths.uri import FileUriMapping
from .reporting import utc_now, write_run_report
from .services import run_export, run_import
from .usb import generation, pioneer, review_report, sftp

app = typer.Typer(
    help="Sync playlists between Traktor NML and M3U through a rebuildable local store.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the current bootstrap version marker."""
    typer.echo("traktor-m3u-sync bootstrap")


@app.command(name="import")
def import_command(  # noqa: A001 - shadows built-in intentionally for CLI name
    format: str = typer.Option(..., "--format", help="Source format: nml, m3u"),  # noqa: A002
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    store: Path | None = typer.Option(None, "--store"),
    collection: Path | None = typer.Option(None, "--collection"),
    import_dir: Path | None = typer.Option(None, "--import-dir"),
    report_file: Path | None = typer.Option(
        None,
        "--report-file",
        help="Write a JSON run report to this path after the run",
    ),
    fail_on_warning: bool = typer.Option(
        False, "--fail-on-warning", help="Exit with status 2 if any warnings are emitted"
    ),
) -> None:
    """Read a source format wholesale into the store."""
    _run(
        "import_failed",
        lambda cfg: run_import(cfg, format),
        lambda cfg: apply_import_overrides(
            cfg,
            format=format,
            store_path=store,
            collection_path=collection,
            import_dir=import_dir,
        ),
        config,
        command_name="import",
        format=format,
        report_file=report_file,
        fail_on_warning=fail_on_warning,
    )


@app.command()
def export(
    format: str = typer.Option(  # noqa: A002
        ..., "--format", help="Target format: m3u, nml, itunes, rekordbox, engine"
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    store: Path | None = typer.Option(None, "--store"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    collection: Path | None = typer.Option(None, "--collection"),
    sandbox_name: str | None = typer.Option(None, "--sandbox-name"),
    output_file: Path | None = typer.Option(None, "--output-file"),
    location_base: str | None = typer.Option(
        None,
        "--location-base",
        help="Absolute file: URI base for consumer Locations",
    ),
    check_base_path: Path | None = typer.Option(
        None,
        "--check-base-path",
        help="Local mount used only for missing-file warnings",
    ),
    engine_database: Path | None = typer.Option(
        None,
        "--engine-database",
        help="Existing Engine DJ media database (m.db) target",
    ),
    engine_track_prefix: str | None = typer.Option(
        None,
        "--engine-track-prefix",
        help="Engine track path prefix, default ..",
    ),
    engine_managed_root: str | None = typer.Option(
        None,
        "--engine-managed-root",
        help="Owned Engine top-level playlist, default 'Playlist Sync'",
    ),
    engine_check_base_path: Path | None = typer.Option(
        None,
        "--engine-check-base-path",
        help="Local mount used only for missing-file warnings",
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Rehearse the export against isolated temporary targets"
    ),
    report_file: Path | None = typer.Option(
        None,
        "--report-file",
        help="Write a JSON run report to this path after the run",
    ),
    fail_on_warning: bool = typer.Option(
        False, "--fail-on-warning", help="Exit with status 2 if any warnings are emitted"
    ),
) -> None:
    """Write the store to a target format; store-only, no source format is read."""
    _run(
        "export_failed",
        lambda cfg: run_export(cfg, format, dry_run=dry_run),
        lambda cfg: apply_export_overrides(
            cfg,
            format=format,
            store_path=store,
            collection_path=collection,
            output_dir=output_dir,
            sandbox_name=sandbox_name,
            output_file=output_file,
            location_base=location_base,
            check_base_path=check_base_path,
            engine_database=engine_database,
            engine_track_prefix=engine_track_prefix,
            engine_managed_root=engine_managed_root,
            engine_check_base_path=engine_check_base_path,
        ),
        config,
        command_name="export",
        format=format,
        report_file=report_file,
        fail_on_warning=fail_on_warning,
        dry_run=dry_run,
    )


@app.command(name="engine-analysis")
def engine_analysis(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    engine_database: Path | None = typer.Option(
        None, "--engine-database", help="Engine DJ media database (m.db) to read"
    ),
    engine_managed_root: str | None = typer.Option(
        None, "--engine-managed-root", help="Owned Engine top-level playlist"
    ),
) -> None:
    """Print JSON mapping each managed Engine track ID to whether its analysis is saved.

    Read-only and safe while Engine DJ is open; exits 75 if the database stays locked.
    """
    try:
        engine = apply_export_overrides(
            load_config(config),
            format="engine",
            engine_database=engine_database,
            engine_managed_root=engine_managed_root,
        ).engine
        assert engine.database_path is not None
        saved = managed_analysis_saved(engine.database_path, engine.managed_root)
    except sqlite3.OperationalError as exc:
        if exc.sqlite_errorcode != sqlite3.SQLITE_BUSY:
            typer.echo(f"ERROR code=engine_analysis_failed detail={exc}", err=True)
            raise typer.Exit(code=1) from exc
        typer.echo("ERROR code=engine_busy detail=database is locked", err=True)
        raise typer.Exit(code=75) from exc
    except ConfigError as exc:
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR code=engine_analysis_failed detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps({str(track_id): done for track_id, done in saved.items()}))


@app.command(name="engine-start-cues")
def engine_start_cues(
    engine_database: Path = typer.Option(..., "--engine-database"),
    engine_managed_root: str = typer.Option("Playlist Sync", "--engine-managed-root"),
    track_ids: list[int] | None = typer.Option(None, "--track-id"),
    apply: bool = typer.Option(False, "--apply"),
) -> None:
    """Preview or seed empty Hot Cue A slots while Engine is closed."""
    changes = _usb_step(
        lambda: prepare(engine_database, engine_managed_root, track_ids or (), apply=apply)
    )
    for path, seconds in changes:
        typer.echo(f"{seconds:.3f}s  {path}")
    typer.echo(f"SUMMARY start_cues={len(changes)} applied={str(apply).lower()}")


usb_app = typer.Typer(help="Build USB library exports and deliver them over SFTP.")
app.add_typer(usb_app, name="usb")


USB_FORMAT_OPTION = typer.Option(None, "--format", help="Select engine or pioneer (repeatable)")


@usb_app.command(name="build")
def usb_build(
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    formats: list[str] | None = USB_FORMAT_OPTION,
) -> None:
    """Stage USB generations from the closed Engine library."""

    def run() -> None:
        settings = load_usb_config(config, formats)
        with generation.lock(settings.output_dir):
            for name in settings.formats:
                args = (settings.library, settings.output_dir / name, settings.playlist_root)
                result = usb.build(*args).generation if name == "engine" else pioneer.build(*args)
                typer.echo(f"SUMMARY format={name} generation={result.path.name}")

    _usb_step(run)


@usb_app.command(name="rekordbox-xml")
def usb_rekordbox_xml(
    output: Path = typer.Option(..., "--output-file"),
    location_base: str = typer.Option(
        ..., "--location-base", help="Engine Library folder's file: URI in rekordbox"
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
) -> None:
    """Export the closed Engine library to XML for a native rekordbox reference build."""

    def run() -> None:
        settings = load_usb_config(config)
        locations = FileUriMapping(location_base)
        snapshot = select(capture(settings.library / "Database2/m.db"), settings.playlist_root)
        write_snapshot(snapshot, locations, output)
        typer.echo(f"SUMMARY tracks={len(snapshot.tracks)} output={output}")

    _usb_step(run)


@usb_app.command(name="push")
def usb_push(
    root: str = typer.Option(..., "--root", help="Stick root path on the SFTP server"),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    formats: list[str] | None = USB_FORMAT_OPTION,
    apply: bool = typer.Option(False, "--apply", help="Write to the stick; default previews"),
    reviewed: str | None = typer.Option(
        None, "--reviewed", help="SHA-256 of an edited Engine stick database that may be replaced"
    ),
) -> None:
    """Send the selected libraries to the same stick, databases last."""

    def run() -> None:
        settings = load_usb_config(config, formats)
        if reviewed is not None and "engine" not in settings.formats:
            raise ConfigError("--reviewed applies only to Engine")
        device = load_usb_device_config(config)
        with generation.lock(settings.output_dir):
            exports = {
                name: generation.current(settings.output_dir / name) for name in settings.formats
            }
            with sftp.session(device) as client:
                stick = sftp.enter_stick(client, root, mark=apply)
                for name, export in exports.items():
                    result = sftp.push(
                        client,
                        export,
                        sftp.StickState(device.state_dir, stick, name),
                        apply=apply,
                        reviewed=reviewed,
                    )
                    for path in result.files:
                        typer.echo(path)
                    typer.echo(
                        f"SUMMARY format={name} files={len(result.files)} bytes={result.bytes} "
                        f"applied={str(result.applied).lower()}"
                    )
        if apply:
            typer.echo("Delivery complete. Stop the SFTP server, then eject the drive.")

    _usb_step(run)


@usb_app.command(name="review")
def usb_review(
    root: str = typer.Option(..., "--root", help="Stick root path on the SFTP server"),
    approve: str | None = typer.Option(
        None, "--approve", help="Approval code from a previous review; writes it into Engine"
    ),
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    diff: bool = typer.Option(False, "--diff", help="Show all eligible changes"),
    report: Path | None = typer.Option(None, "--report", help="Write the full JSON diff"),
) -> None:
    """Review stick edits or apply them, excluding the main cue."""

    def run() -> usb.Review:
        engine = load_usb_config(config, ["engine"])
        device = load_usb_device_config(config)
        with sftp.session(device) as client:
            stick = sftp.enter_stick(client, root, mark=False)
            state = sftp.StickState(device.state_dir, stick)
            pulled = sftp.pull(client, state, usb.DATABASE)
            if approve is None:
                return usb.review(engine.library, pulled.snapshot)
            result = usb.apply_review(engine.library, pulled.snapshot, approve)
            if stick is not None:
                state.accept(pulled.sha256)
            else:
                typer.echo(
                    "For the first push, confirm the existing Engine database with "
                    f"--reviewed {pulled.sha256}."
                )
            return result

    result = _usb_step(run)
    if report is not None:
        _usb_step(lambda: review_report.write_review(report, result))
    review_report.show(result, full=diff, applied=approve is not None)


def _usb_step[T](step: Callable[[], T]) -> T:
    try:
        return step()
    except ConfigError as exc:
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR code=usb_failed detail={exc}", err=True)
        raise typer.Exit(code=1) from exc


def _run(
    error_code: str,
    command: Callable[[AppConfig], SyncResult],
    resolve: Callable[[AppConfig], AppConfig],
    config_path: Path,
    *,
    command_name: str,
    format: str,  # noqa: A002
    fail_on_warning: bool = False,
    report_file: Path | None = None,
    dry_run: bool = False,
) -> None:
    started = utc_now()
    try:
        result = command(resolve(load_config(config_path)))
    except ConfigError as exc:
        _write_failure_report(
            report_file, "config_error", exc, command_name, format, started, dry_run
        )
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        _write_failure_report(report_file, error_code, exc, command_name, format, started, dry_run)
        typer.echo(f"ERROR code={error_code} detail={exc}", err=True)
        raise typer.Exit(code=1) from exc

    _emit(result)
    exit_status = 2 if fail_on_warning and result.warnings else 0
    if report_file is not None:
        warning = write_run_report(
            report_file,
            command=command_name,
            format=format,
            started=started,
            finished=utc_now(),
            result=result,
            exit_status=exit_status,
            dry_run=dry_run,
        )
        if warning is not None:
            detail = f' detail="{warning.detail}"' if warning.detail else ""
            typer.echo(f"WARNING code={warning.code}{detail}", err=True)
    if exit_status == 2:
        raise typer.Exit(code=2)


def _write_failure_report(
    report_file: Path | None,
    error_code: str,
    exc: Exception,
    command_name: str,
    format: str,  # noqa: A002
    started: str,
    dry_run: bool,
) -> None:
    """Record a hard failure in the run report before the CLI exits 1."""
    if report_file is None:
        return
    warning = write_run_report(
        report_file,
        command=command_name,
        format=format,
        started=started,
        finished=utc_now(),
        result=None,
        exit_status=1,
        error=AdapterWarning(code=error_code, message=str(exc)),
        dry_run=dry_run,
    )
    if warning is not None:
        detail = f' detail="{warning.detail}"' if warning.detail else ""
        typer.echo(f"WARNING code={warning.code}{detail}", err=True)


def _emit(result: SyncResult) -> None:
    for warning in result.warnings:
        detail = f' detail="{warning.detail}"' if warning.detail else ""
        playlist = f' playlist="{warning.playlist}"' if warning.playlist else ""
        typer.echo(f"WARNING code={warning.code}{playlist}{detail}", err=True)

    counts = " ".join(f"{key}={value}" for key, value in result.counts.items())
    if result.provenance is not None:
        counts += (
            f" source_format={result.provenance.source_format}"
            f" imported_at={result.provenance.imported_at}"
        )
    typer.echo(f"SUMMARY {counts}")


def main() -> None:
    app()


__all__ = ["AdapterWarning", "app", "main"]
