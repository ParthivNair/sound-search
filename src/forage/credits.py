"""Per-project credits / obligations manifest.

`forage credits [PATH]...` scopes the library to the sounds actually used in a
project — matching each audio file under PATH against the library by content hash,
falling back to the `freesound-<id>` filename stem for transcoded/renamed copies —
and renders a `credits.md` listing each sound's creator, link, license, and what
the producer must do, flagging NonCommercial / NoDerivatives sounds with a release
warning. With no PATH it covers the whole library.

The render functions are pure (return a markdown string); the CLI owns writing it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import licensing
from .grow import DECODABLE_EXTS
from .index import SqliteVecStore, VectorStore
from .library import sha256_file

_SUFFIX_RE = re.compile(r"^(.*?)[ _]\(?\d+\)?$")  # strip a trailing " (1)" / "_2" copy marker


@dataclass
class Matched:
    file: Path
    meta: dict
    how: str  # "hash" | "stem"


@dataclass
class ScopeResult:
    metas: list[dict] = field(default_factory=list)
    matched: list[Matched] = field(default_factory=list)
    unmatched_files: list[Path] = field(default_factory=list)
    whole_library: bool = False


def _stem_candidates(stem: str):
    """The filename stem, plus a copy with a trailing ' (n)'/'_n' marker stripped,
    so a Cakewalk copy 'freesound-123 (1)' still resolves to 'freesound-123'."""
    yield stem
    m = _SUFFIX_RE.match(stem)
    if m and m.group(1) and m.group(1) != stem:
        yield m.group(1)


def _iter_audio(paths):
    """Yield audio files from a list of file/dir paths (dirs are walked recursively;
    Cakewalk's Audio/ subfolder is covered). Non-audio (.cwp, .peak, ...) is skipped."""
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in DECODABLE_EXTS:
                    yield f
        elif p.is_file() and p.suffix.lower() in DECODABLE_EXTS:
            yield p


def scope_library(paths, store: VectorStore | None = None) -> ScopeResult:
    """Resolve which library sounds are in scope. No paths => whole library."""
    store = store or SqliteVecStore()
    rows = store.list_all()
    if not paths:
        return ScopeResult(metas=rows, whole_library=True)

    by_hash = {m["file_hash"]: m for m in rows}
    by_stem = {Path(m["filename"]).stem: m for m in rows}

    matched: list[Matched] = []
    unmatched: list[Path] = []
    seen_files: set = set()
    for f in _iter_audio(paths):
        rp = f.resolve()
        if rp in seen_files:
            continue
        seen_files.add(rp)
        meta = by_hash.get(sha256_file(f))
        how = "hash"
        if meta is None:
            for cand in _stem_candidates(f.stem):
                if cand in by_stem:
                    meta, how = by_stem[cand], "stem"
                    break
        if meta is None:
            unmatched.append(f)
        else:
            matched.append(Matched(file=f, meta=meta, how=how))

    metas: list[dict] = []
    seen_ids: set = set()
    for mt in matched:
        fid = mt.meta["forage_id"]
        if fid not in seen_ids:
            seen_ids.add(fid)
            metas.append(mt.meta)
    return ScopeResult(metas=metas, matched=matched, unmatched_files=unmatched)


def default_out_path(paths) -> Path:
    """`credits.md` beside a single project dir, else in the current directory."""
    if paths and len(paths) == 1 and Path(paths[0]).is_dir():
        return Path(paths[0]) / "credits.md"
    return Path("credits.md")


def scope_label(paths, result: ScopeResult) -> str:
    if result.whole_library:
        return "whole library"
    if paths and len(paths) == 1:
        return str(Path(paths[0]))
    return f"{len(paths)} path(s)"


def restricted_metas(metas) -> list[dict]:
    """Sounds that constrain a release: NonCommercial or NoDerivatives."""
    return [m for m in metas if m.get("non_commercial") or m.get("no_derivatives")]


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|")


def render_markdown(result: ScopeResult, scope_label: str) -> str:
    """Render the obligations manifest as markdown (pure — no file IO)."""
    metas = result.metas
    out: list[str] = [f"# Forage credits — {scope_label}", ""]

    counts = f"{len(metas)} sound(s) in scope"
    if not result.whole_library:
        counts += f" · {len(result.matched)} file(s) matched · {len(result.unmatched_files)} unmatched"
    unknown = sum(1 for m in metas if (m.get("license_name") or "Unknown") == "Unknown")
    if unknown:
        counts += f" · {unknown} unknown-license"
    out += [f"Generated {_today()} · {counts}", ""]

    restricted = restricted_metas(metas)
    if restricted:
        out.append("> ⚠ **Release warning** — this scope contains restricted sounds:")
        for m in restricted:
            kinds = []
            if m.get("non_commercial"):
                kinds.append("Non-commercial only")
            if m.get("no_derivatives"):
                kinds.append("No derivatives")
            out.append(f"> - **{m.get('title') or m['forage_id']}** ({m['forage_id']}): {', '.join(kinds)}.")
        out.append("")

    if metas:
        out += ["| Title | Creator | License | Must do |", "|---|---|---|---|"]
        for m in metas:
            who = m.get("attribution_username") or "creator unknown"
            link = m.get("attribution_url")
            creator = f"{who} ({link})" if link else who
            lic = m.get("license_name") or "Unknown"
            lic_url = m.get("license_url")
            lic_cell = f"{lic} ({lic_url})" if lic_url else lic
            must = "<br>".join(licensing.obligations(m))
            title = m.get("title") or m["forage_id"]
            out.append(f"| {_cell(title)} | {_cell(creator)} | {_cell(lic_cell)} | {_cell(must)} |")
        out.append("")
    else:
        out += ["_No sounds in scope._", ""]

    if result.unmatched_files:
        out.append("## Not from Forage — credit unknown")
        out += [f"- {f}" for f in result.unmatched_files]
        out.append("")

    # Consolidated one-line credits blurb (attribution-required sounds, deduped).
    blurb, seen = [], set()
    for m in metas:
        if not m.get("requires_attribution"):
            continue
        key = (m.get("attribution_username"), m.get("attribution_url"))
        if key in seen:
            continue
        seen.add(key)
        blurb.append(licensing.attribution_line(m))
    if blurb:
        out += ["## Credits blurb (paste into your release notes)", "",
                "Contains sounds — " + "; ".join(blurb) + ".", ""]

    out += ["---",
            "Generated by Forage. You are responsible for honoring these terms in anything you release.",
            ""]
    return "\n".join(out)
