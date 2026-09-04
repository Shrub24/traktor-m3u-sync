"""Typer CLI entry point for traktor-m3u-sync."""

from __future__ import annotations

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
)
from .contracts import AdapterWarning, SyncResult
from .reporting import utc_now, write_run_report
from .services import run_export, run_import

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
        ..., "--format", help="Target format: m3u, nml, itunes, engine"
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
