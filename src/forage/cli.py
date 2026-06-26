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

auth_app = typer.Typer(no_args_is_help=True, help="Freesound OAuth2 (needed to download originals).")
app.add_typer(auth_app, name="auth")


@config_app.command("show")
def config_show() -> None:
    """Show resolved paths, the pinned CLAP checkpoint, and auth state."""
    cfg = config.load_config()
    typer.echo(f"forage version : {__version__}")
    typer.echo(f"FORAGE_HOME    : {config.forage_home()}")
    typer.echo(f"samples        : {config.samples_dir()}")
    typer.echo(f"metadata       : {config.metadata_dir()}")
    typer.echo(f"library.db     : {config.db_path()}")
    typer.echo(f"config.json    : {config.config_path()}")
    typer.echo(f"clap checkpoint: {config.CLAP_CHECKPOINT}")
    typer.echo(f"freesound token: {'set' if cfg.get('freesound_token') else 'MISSING'}")
    typer.echo(f"oauth client id: {'set' if cfg.get('freesound_client_id') else 'missing'}")
    typer.echo(f"oauth session  : {'authorized' if config.oauth_path().exists() else 'not logged in'}")


@auth_app.command("login")
def auth_login() -> None:
    """Authorize Forage to download Freesound originals (one-time, in browser)."""
    import webbrowser

    from .sources.freesound import FreesoundAuthError, FreesoundClient

    client = FreesoundClient()
    try:
        url = client.authorize_url()
    except FreesoundAuthError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo("Opening your browser to authorize Forage with Freesound:")
    typer.echo(f"  {url}")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    typer.echo("\nAfter approving, your browser is redirected to a URL containing `code=...`.")
    code = typer.prompt("Paste the authorization code").strip()
    try:
        client.exchange_code(code)
    except FreesoundAuthError as e:
        typer.secho(f"Auth failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(1)
    st = client.oauth_status()
    typer.secho(f"Authorized (scope={st.get('scope')}). Token cached at {config.oauth_path()}",
                fg=typer.colors.GREEN)


@auth_app.command("status")
def auth_status() -> None:
    """Show whether downloads are authorized."""
    from .sources.freesound import FreesoundClient

    st = FreesoundClient().oauth_status()
    if not st.get("authorized"):
        typer.echo("Not authorized for downloads. Run `forage auth login`.")
        raise typer.Exit(1)
    typer.echo(f"Authorized. scope={st.get('scope')} expires_in={st.get('expires_in_s')}s")


def _todo(phase: str) -> None:
    typer.secho(f"[not implemented yet — arrives in {phase}]", fg=typer.colors.YELLOW)
    raise typer.Exit(code=1)


@app.command()
def grow(
    query: str = typer.Option(..., "--query", "-q", help="Search term to fetch from Freesound."),
    count: int = typer.Option(5, "--count", "-n", help="How many NEW sounds to add."),
    license: str = typer.Option(None, "--license", help="Only keep licenses matching, e.g. cc0 / by / free."),
) -> None:
    """Fetch CC sounds from Freesound (originals), embed, and index them."""
    from . import grow as grow_mod
    from .index import SqliteVecStore
    from .sources.freesound import FreesoundAuthError

    store = SqliteVecStore()
    try:
        kept, skipped = grow_mod.grow(
            query, count, store=store,
            license_filter=_license_filter(license),
            progress=lambda s: typer.echo(s),
        )
    except FreesoundAuthError as e:
        typer.secho(str(e), fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(f"Grew {kept} new sound(s); skipped {skipped}. Library total: {store.count()}")


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
    """Reconcile orphaned files / sidecars / index rows (read-only report)."""
    from . import grow as grow_mod

    rep = grow_mod.doctor()
    typer.echo(f"Indexed sounds            : {rep['indexed']}")
    typer.echo(f"DB rows with missing audio: {len(rep['missing_audio'])}")
    for x in rep["missing_audio"][:10]:
        typer.echo(f"   missing audio: {x}")
    typer.echo(f"Orphan sample files       : {len(rep['orphan_files'])}")
    for x in rep["orphan_files"][:10]:
        typer.echo(f"   orphan file: {x}")
    typer.echo(f"Sidecars not indexed      : {len(rep['sidecars_not_indexed'])}")
    ok = not (rep["missing_audio"] or rep["orphan_files"] or rep["sidecars_not_indexed"])
    typer.secho("Library is consistent." if ok else "Inconsistencies found (see above; `forage reindex` can help).",
                fg=typer.colors.GREEN if ok else typer.colors.YELLOW)


if __name__ == "__main__":  # pragma: no cover
    app()
