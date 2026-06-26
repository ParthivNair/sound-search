"""Forage command-line interface (Typer).

Phase 0 ships the `config show` command and stubs for the commands implemented
in later phases, so the CLI surface is visible and `forage --help` works as soon
as the package is installed (`pip install -e .`).
"""

from __future__ import annotations

import typer

from . import __version__, config

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Forage — grow and search a personal sample library.",
)

config_app = typer.Typer(no_args_is_help=True, help="Inspect Forage configuration.")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """Show resolved paths and the pinned CLAP checkpoint."""
    typer.echo(f"forage version : {__version__}")
    typer.echo(f"FORAGE_HOME    : {config.forage_home()}")
    typer.echo(f"samples        : {config.samples_dir()}")
    typer.echo(f"metadata       : {config.metadata_dir()}")
    typer.echo(f"library.db     : {config.db_path()}")
    typer.echo(f"config.json    : {config.config_path()}")
    typer.echo(f"clap checkpoint: {config.CLAP_CHECKPOINT}")


def _todo(phase: str) -> None:
    typer.secho(f"[not implemented yet — arrives in {phase}]", fg=typer.colors.YELLOW)
    raise typer.Exit(code=1)


@app.command()
def grow(
    query: str = typer.Option(..., "--query", "-q", help="Search term to fetch from Freesound."),
    count: int = typer.Option(5, "--count", "-n", help="How many candidates to fetch."),
) -> None:
    """(Phase 3) Fetch CC sounds from Freesound, embed, and index them."""
    _todo("Phase 3")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural-language query."),
    limit: int = typer.Option(10, "--limit", "-k"),
) -> None:
    """(Phase 2) Natural-language search over the local library (text -> audio)."""
    _todo("Phase 2")


@app.command()
def similar(
    ref: str = typer.Argument(..., help="A freesound id or library path to find neighbors of."),
    limit: int = typer.Option(10, "--limit", "-k"),
) -> None:
    """(Phase 2) Find audibly similar sounds (audio -> audio)."""
    _todo("Phase 2")


@app.command(name="list")
def list_cmd() -> None:
    """(Phase 2) List indexed sounds with license + obligation flags."""
    _todo("Phase 2")


@app.command(name="import")
def import_cmd(path: str = typer.Argument(..., help="Folder of audio to import.")) -> None:
    """(Phase 2) Import an existing folder of audio into the library."""
    _todo("Phase 2")


@app.command()
def credits() -> None:
    """(Phase 4) Generate a per-project attribution/obligations manifest."""
    _todo("Phase 4")


@app.command()
def reindex() -> None:
    """(Phase 4) Rebuild library.db from the per-file metadata sidecars."""
    _todo("Phase 4")


@app.command()
def doctor() -> None:
    """(Phase 3) Reconcile orphaned files / sidecars / index rows."""
    _todo("Phase 3")


if __name__ == "__main__":  # pragma: no cover
    app()
