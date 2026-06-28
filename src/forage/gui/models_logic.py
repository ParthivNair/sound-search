"""Row formatting + category counts for the results model (Qt-free, unit-testable)."""

from __future__ import annotations

from collections import Counter

from ..predicates import flags

COLUMNS = ("Title", "Category", "License", "Dur", "Score")


def _dur(ms) -> str:
    return f"{ms / 1000:.1f}s" if ms else ""


def build_row(meta: dict, score=None) -> tuple:
    """The display tuple for one result row, column-aligned with COLUMNS."""
    return (
        meta.get("title") or meta.get("forage_id") or "",
        meta.get("category") or "uncategorized",
        flags(meta),
        _dur(meta.get("duration_ms")),
        f"{score:+.3f}" if score is not None else "",
    )


def category_counts(metas) -> list[tuple[str, int]]:
    """[(label, count)] for the sidebar: 'All' first, then categories alphabetically."""
    c = Counter((m.get("category") or "uncategorized") for m in metas)
    return [("All", len(metas))] + [(name, c[name]) for name in sorted(c)]
