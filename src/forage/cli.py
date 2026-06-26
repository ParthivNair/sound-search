"""Forage command-line interface (Typer).

Phase 0 ships the `config show` command and stubs for the commands implemented
in later phases, so the CLI surface is visible and `forage --help` works as soon
as the package is installed (`pip install -e .`).
"""

from __future__ import annotations

import sys

import typer

from . import __version__, config

# Make the CLI robust to non-ASCII titles on a cp1252 Windows console
# (Freesound titles can contain accents/emoji that would otherwise crash echo).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):  # stream not reconfigurable
    pass

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


def _flags(meta: dict) -> str:
    """Compact license + obligation badge shown next to every result."""
    parts = [meta.get("license_name") or "?"]
    if meta.get("requires_attribution"):
        parts.append("ATTRIB")
    if meta.get("non_commercial"):
        parts.append("NC")
    if meta.get("share_alike"):
        parts.append("SA")
    if meta.get("no_derivatives"):
        parts.append("ND")
    return ",".join(parts)


def _license_filter(spec: str | None):
    if not spec:
        return None
    s = spec.lower()
    if s == "free":  # no obligations: safe to use anywhere
        return lambda m: not (m.get("requires_attribution") or m.get("non_commercial") or m.get("no_derivatives"))
    return lambda m: s in (m.get("license_name") or "").lower()


def _print_hits(hits) -> None:
    from . import config

    for i, h in enumerate(hits, 1):
        path = config.samples_dir() / h.meta["filename"]
        typer.echo(f"{i:2}. {h.score:+.3f}  {(h.meta.get('title') or '')[:46]:46}  "
                   f"[{_flags(h.meta)}]  by {h.meta.get('attribution_username') or '-'}")
        typer.echo(f"      {path}")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural-language query."),
    limit: int = typer.Option(10, "--limit", "-k"),
    license: str = typer.Option(None, "--license", help="Filter by license, e.g. cc0 / by / free."),
) -> None:
    """Natural-language search over the local library (text -> audio)."""
    from . import embed
    from .index import SqliteVecStore

    store = SqliteVecStore()
    if store.count() == 0:
        typer.secho("Library is empty — run `forage import <folder>` or `forage grow` first.",
                    fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    hits = store.search(embed.embed_text(query), limit, license_filter=_license_filter(license))
    if not hits:
        typer.echo("No matches.")
        return
    _print_hits(hits)


@app.command()
def similar(
    ref: str = typer.Argument(..., help="A forage_id (e.g. freesound-12345) or bare freesound id."),
    limit: int = typer.Option(10, "--limit", "-k"),
    license: str = typer.Option(None, "--license", help="Filter by license, e.g. cc0 / by / free."),
) -> None:
    """Find audibly similar sounds (audio -> audio)."""
    from .index import SqliteVecStore

    store = SqliteVecStore()
    fid = ref
    if store.get_vector(fid) is None and ref.isdigit():
        fid = f"freesound-{ref}"
    hits = store.similar(fid, limit, license_filter=_license_filter(license))
    if not hits:
        typer.secho(f"No neighbors for '{ref}' (unknown id?).", fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    _print_hits(hits)


@app.command(name="list")
def list_cmd(
    license: str = typer.Option(None, "--license", help="Filter by license, e.g. cc0 / by / free."),
    limit: int = typer.Option(50, "--limit", "-k"),
) -> None:
    """List indexed sounds with license + obligation flags."""
    from .index import SqliteVecStore

    store = SqliteVecStore()
    rows = store.list_all()
    lf = _license_filter(license)
    if lf:
        rows = [m for m in rows if lf(m)]
    typer.echo(
        f"Library: {store.count()} total, {len(rows)} match filter; "
        f"showing {min(limit, len(rows))}:"
    )
    for m in rows[:limit]:
        typer.echo(f"  {m['forage_id']:24} [{_flags(m)}]  {(m.get('title') or '')[:50]}")


@app.command(name="import")
def import_cmd(path: str = typer.Argument(..., help="Folder of audio to import.")) -> None:
    """Import an existing folder of audio into the library + index."""
    from . import library
    from .index import SqliteVecStore

    store = SqliteVecStore()
    typer.echo(f"Importing audio from {path} ...")
    added, skipped = library.import_folder(path, store=store, progress=lambda s: typer.echo(s))
    typer.echo(f"Done. added={added}  skipped(dup)={skipped}  total in library={store.count()}")


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
