"""Forage command-line interface (Typer).

Phase 0 ships the `config show` command and stubs for the commands implemented
in later phases, so the CLI surface is visible and `forage --help` works as soon
as the package is installed (`pip install -e .`).
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

from . import __version__, config
from .predicates import flags as _flags
from .predicates import license_filter as _license_filter
from .predicates import tags_filter as _tags_filter

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
    if hits[0].score < config.SEARCH_GAP_THRESHOLD:
        typer.secho(f'hint: nothing strong matched — try: forage grow --query "{query}"',
                    fg=typer.colors.YELLOW)


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
    tags: list[str] = typer.Option(None, "--tags", help="Filter by tag (substring, repeatable; OR)."),
    category: str = typer.Option(None, "--category", help="Filter by category (run `forage categorize` first)."),
    limit: int = typer.Option(50, "--limit", "-k"),
) -> None:
    """List indexed sounds with category + license + obligation flags."""
    from .index import SqliteVecStore

    store = SqliteVecStore()
    rows = store.list_all()
    lf = _license_filter(license)
    tf = _tags_filter(tags)
    if lf:
        rows = [m for m in rows if lf(m)]
    if tf:
        rows = [m for m in rows if tf(m)]
    if category:
        rows = [m for m in rows if (m.get("category") or "uncategorized").lower() == category.lower()]
    typer.echo(
        f"Library: {store.count()} total, {len(rows)} match filter; "
        f"showing {min(limit, len(rows))}:"
    )
    for m in rows[:limit]:
        cat = (m.get("category") or "-")
        typer.echo(f"  {m['forage_id']:20} {cat:12} [{_flags(m)}]  {(m.get('title') or '')[:44]}")


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
def credits(
    path: list[str] = typer.Argument(
        None, metavar="[PATH]...",
        help="Cakewalk project folder(s) or audio file(s) used. Omit = whole library."),
    out: str = typer.Option(None, "--out", "-o", help="Where to write credits.md."),
    to_stdout: bool = typer.Option(False, "--stdout", help="Print the manifest instead of writing a file."),
) -> None:
    """Write a per-project attribution/obligations manifest (credits.md)."""
    from . import credits as credits_mod

    result = credits_mod.scope_library(path)
    label = credits_mod.scope_label(path, result)
    md = credits_mod.render_markdown(result, label)

    typer.echo(f"Scope: {label} — {len(result.metas)} sound(s)")
    for m in result.metas:
        typer.echo(f"  {m['forage_id']:24} [{_flags(m)}]  {(m.get('title') or '')[:50]}")
    restricted = credits_mod.restricted_metas(result.metas)
    if restricted:
        typer.secho(f"⚠ Release warning: {len(restricted)} restricted sound(s) (NC/ND) in scope.",
                    fg=typer.colors.YELLOW)
    if result.unmatched_files:
        typer.secho(f"{len(result.unmatched_files)} file(s) not from Forage — listed as 'credit unknown'.",
                    fg=typer.colors.YELLOW)

    if to_stdout:
        typer.echo("")
        typer.echo(md)
        return
    out_path = Path(out) if out else credits_mod.default_out_path(path)
    out_path.write_text(md, encoding="utf-8")
    typer.secho(f"Wrote {out_path}", fg=typer.colors.GREEN)


@app.command()
def reindex() -> None:
    """Rebuild library.db from the per-file metadata sidecars (re-embeds audio)."""
    from . import grow as grow_mod

    typer.echo("Rebuilding index from sidecars (re-embedding audio)...")
    rep = grow_mod.reindex(progress=lambda s: typer.echo(s))
    typer.echo(f"Rebuilt index     : {rep['rebuilt']} sound(s)")
    typer.echo(f"Skipped invalid   : {rep['skipped_invalid']}")
    typer.echo(f"Missing audio     : {rep['missing_audio']}")
    typer.echo(f"Checkpoint updated: {rep['checkpoint_updated']}")
    typer.secho("Done.", fg=typer.colors.GREEN)


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


@app.command()
def categorize(
    recompute: bool = typer.Option(False, "--recompute", help="Re-categorize sounds that already have a category."),
    threshold: float = typer.Option(None, "--threshold", help="Min CLAP cosine to accept a category (else 'uncategorized')."),
) -> None:
    """Auto-assign a category + one-shot flag to every sound (CLAP zero-shot)."""
    from . import categorize as cat_mod
    from . import embed
    from .index import SqliteVecStore

    store = SqliteVecStore()
    thr = threshold if threshold is not None else config.CATEGORIZE_THRESHOLD
    counts = cat_mod.categorize(store, embed.embed_text, recompute=recompute, threshold=thr,
                                progress=lambda s: typer.echo(s))
    typer.echo("Categories:")
    for name in [*cat_mod.CATEGORY_NAMES, "uncategorized"]:
        if counts.get(name):
            typer.echo(f"  {name:14} {counts[name]}")
    typer.secho(f"Categorized {sum(counts.values())} sound(s).", fg=typer.colors.GREEN)


@app.command(name="export-sfz")
def export_sfz(
    forage_ids: list[str] = typer.Argument(None, help="Specific sound ids; default = all one-shots."),
    category: list[str] = typer.Option(None, "--category", help="Include only these categories (repeatable)."),
    drum_map: bool = typer.Option(False, "--drum-map", help="Map drum categories to General-MIDI keys."),
    name: str = typer.Option("forage-kit", "--name", help="Instrument name / output filename."),
) -> None:
    """Export one-shots as an .sfz instrument (maps samples to MIDI keys)."""
    from . import sfz as sfz_mod
    from .index import SqliteVecStore

    rows = SqliteVecStore().list_all()
    if forage_ids:
        want = set(forage_ids)
        metas = [m for m in rows if m["forage_id"] in want or m.get("source_id") in want]
    elif category:
        cats = {c.lower() for c in category}
        metas = [m for m in rows if (m.get("category") or "").lower() in cats]
    else:
        metas = [m for m in rows if m.get("is_oneshot")]
    if not metas:
        typer.secho("No sounds matched the selection (run `forage categorize` first?).",
                    fg=typer.colors.YELLOW)
        raise typer.Exit(1)
    if len(metas) > sfz_mod.MAX_KEY:
        typer.secho(f"Selection has {len(metas)} sounds; an SFZ kit maps at most {sfz_mod.MAX_KEY}. "
                    "Using the first ones.", fg=typer.colors.YELLOW)
        metas = metas[: sfz_mod.MAX_KEY]
    layout = "drum-map" if drum_map else "chromatic"
    out = sfz_mod.write_sfz(metas, name=name, layout=layout)
    typer.secho(f"Wrote {out} ({len(metas)} region(s), {layout}).", fg=typer.colors.GREEN)
    typer.echo("Load it in sforzando (VST3) on an instrument track in Cakewalk Next, "
               "or use the built-in XSampler / Pad Controller.")


@app.command()
def browse() -> None:
    """Rebuild the categorized browse/ folder tree (human-readable, for Finder/Explorer/Cakewalk)."""
    from . import browse as browse_mod
    from .index import SqliteVecStore

    rep = browse_mod.browse(SqliteVecStore())
    typer.echo(f"browse/ rebuilt: linked={rep['linked']} copied={rep['copied']} missing={rep['missing']}")
    typer.secho(f"Favorite this folder in Cakewalk's Media Browser: {config.forage_home() / 'browse'}",
                fg=typer.colors.GREEN)


@app.command()
def ui() -> None:
    """Launch the Forage desktop browser (requires PySide6: pip install 'forage[gui]')."""
    try:
        from .gui import launch
        rc = launch()  # blocks until the window closes; ImportError here = PySide6 missing
    except ImportError:
        typer.secho(
            "The desktop UI needs PySide6, which isn't installed.\n"
            "  pip install 'forage[gui]'      (or:  pip install PySide6)",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)
    raise typer.Exit(rc)


if __name__ == "__main__":  # pragma: no cover
    app()
