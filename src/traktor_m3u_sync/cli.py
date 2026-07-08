from __future__ import annotations

import typer

app = typer.Typer(
    help="Synchronize Traktor playlist state with UTF-8 M3U8 playlists.",
    no_args_is_help=True,
)


@app.command()
def version() -> None:
    """Show the current bootstrap version marker."""
    typer.echo("traktor-m3u-sync bootstrap")


def main() -> None:
    app()
