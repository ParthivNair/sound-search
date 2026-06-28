"""Categorized, human-readable mirror of the library for the OS / DAW file browser.

Regenerates ``<FORAGE_HOME>/browse/<Category>/<friendly>_<forage_id>.<ext>`` as
hardlinks (cheap, no extra disk; same volume) with a copy fallback, so Explorer and
Cakewalk's Media Browser become navigable by *kind* instead of by opaque freesound id.
Idempotent: the tree is wiped and rebuilt each run, so renames / deletions / re-runs
of `forage categorize` are reflected.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from . import config
from .index import SqliteVecStore
from .library import sanitize


def browse(store=None, progress=lambda s: None) -> dict:
    """(Re)build the browse/ tree. Returns {linked, copied, missing}."""
    store = store or SqliteVecStore()
    root = config.forage_home() / "browse"
    if root.exists():
        shutil.rmtree(root, ignore_errors=True)
    counts = {"linked": 0, "copied": 0, "missing": 0}
    for m in store.list_all():
        src = config.samples_dir() / m["filename"]
        if not src.exists():
            counts["missing"] += 1
            continue
        cat = m.get("category") or "uncategorized"
        friendly = sanitize(m.get("title") or m["forage_id"])
        dest = root / cat / f"{friendly}_{m['forage_id']}{Path(m['filename']).suffix}"
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(src, dest)            # hardlink: instant, shares bytes (same volume)
            counts["linked"] += 1
        except OSError:                   # cross-volume / permission / FS without hardlinks
            shutil.copy2(src, dest)
            counts["copied"] += 1
    progress(f"browse: linked={counts['linked']} copied={counts['copied']} missing={counts['missing']}")
    return counts
