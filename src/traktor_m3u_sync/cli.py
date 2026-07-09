from __future__ import annotations

from pathlib import Path

import typer

from .config import ConfigError, apply_export_overrides, apply_import_overrides, load_config
from .export_service import ExportResult, run_export
from .import_service import ImportError, ImportResult, run_import

app = typer.Typer(
    help="Synchronize Traktor playlist state with UTF-8 M3U8 playlists.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the current bootstrap version marker."""
    typer.echo("traktor-m3u-sync bootstrap")


@app.command()
def export(
    config: Path = typer.Option(Path("traktor-m3u-sync.toml"), "--config"),
    collection: Path | None = typer.Option(None, "--collection"),
    output_dir: Path | None = typer.Option(None, "--output-dir"),
) -> None:
    """Export standard playlists from a Traktor collection.nml file."""
    try:
        loaded_config = load_config(config)
        resolved_config = apply_export_overrides(
            loaded_config,
            collection_path=collection,
            output_dir=output_dir,
        )
        result = run_export(resolved_config)
    except ConfigError as exc:
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR code=export_failed detail={exc}", err=True)
        raise typer.Exit(code=1) from exc

    _emit_export_result(result)


@app.command(name="import")
def import_(  # noqa: A001 - shadows built-in intentionally for CLI name
    config: Path = typer.Option(Path("traktor-m3u-sync.toml"), "--config"),
    collection: Path | None = typer.Option(None, "--collection"),
    import_dir: Path | None = typer.Option(None, "--import-dir"),
    sandbox_name: str | None = typer.Option(None, "--sandbox-name"),
) -> None:
    """Import .m3u8 playlists into a managed sandbox in collection.nml."""
    try:
        loaded_config = load_config(config)
        resolved_config = apply_import_overrides(
            loaded_config,
            collection_path=collection,
            import_dir=import_dir,
            sandbox_name=sandbox_name,
        )
        result = run_import(resolved_config)
    except ConfigError as exc:
        typer.echo(f"ERROR code=config_error detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except ImportError as exc:
        typer.echo(f"ERROR code=import_failed detail={exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"ERROR code=import_failed detail={exc}", err=True)
        raise typer.Exit(code=1) from exc

    _emit_import_result(result)


def main() -> None:
    app()


def _emit_export_result(result: ExportResult) -> None:
    for warning in result.warnings:
        detail = f' detail="{warning.detail}"' if warning.detail else ""
        playlist = f' playlist="{warning.playlist}"' if warning.playlist else ""
        typer.echo(f"WARNING code={warning.code}{playlist}{detail}", err=True)

    typer.echo(
        "SUMMARY "
        f"playlists_written={result.summary.playlists_written} "
        f"tracks_exported={result.summary.tracks_exported} "
        f"warnings_emitted={result.summary.warnings_emitted}"
    )


def _emit_import_result(result: ImportResult) -> None:
    for warning in result.warnings:
        detail = f' detail="{warning.detail}"' if warning.detail else ""
        playlist = f' playlist="{warning.playlist}"' if warning.playlist else ""
        typer.echo(f"WARNING code={warning.code}{playlist}{detail}", err=True)

    typer.echo(
        "SUMMARY "
        f"playlists_imported={result.summary.playlists_imported} "
        f"tracks_matched={result.summary.tracks_matched} "
        f"tracks_skipped={result.summary.tracks_skipped} "
        f"warnings_emitted={result.summary.warnings_emitted}"
    )
