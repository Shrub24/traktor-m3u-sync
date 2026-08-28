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
        fail_on_warning=fail_on_warning,
    )


@app.command()
def export(
    format: str = typer.Option(..., "--format", help="Target format: m3u, nml, itunes"),  # noqa: A002
    config: Path = typer.Option(DEFAULT_CONFIG_PATH, "--config"),
    store: Path | None = typer.Option(None, "--store"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
    collection: Path | None = typer.Option(None, "--collection"),
    sandbox_name: str | None = typer.Option(None, "--sandbox-name"),
    output_file: Path | None = typer.Option(None, "--output-file"),
    base_path: Path | None = typer.Option(None, "--base-path"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Rehearse the export against isolated temporary targets"
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
            base_path=base_path,
        ),
        config,
        fail_on_warning=fail_on_warning,
    )


def _run(
    error_code: str,
    command: Callable[[AppConfig], SyncResult],
    resolve: Callable[[AppConfig], AppConfig],
    config_path: Path,
    *,
    fail_on_warning: bool = False,
) -> None:
    try:
        result = command(resolve(load_config(config_path)))
    except ConfigError as exc:
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR code={error_code} detail={exc}", err=True)
        raise typer.Exit(code=1) from exc

    _emit(result)
    if fail_on_warning and result.warnings:
        raise typer.Exit(code=2)


def _emit(result: SyncResult) -> None:
    for warning in result.warnings:
        detail = f' detail="{warning.detail}"' if warning.detail else ""
        playlist = f' playlist="{warning.playlist}"' if warning.playlist else ""
        typer.echo(f"WARNING code={warning.code}{playlist}{detail}", err=True)

    counts = " ".join(f"{key}={value}" for key, value in result.counts.items())
    typer.echo(f"SUMMARY {counts}")


def main() -> None:
    app()


__all__ = ["AdapterWarning", "app", "main"]
