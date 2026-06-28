"""Client-side row filtering (Qt-free, unit-testable).

The GUI caches the full `list_all()` and filters it here so browsing is instant and
never touches CLAP or the DB.
"""

from __future__ import annotations

from ..predicates import license_filter


def combine_predicates(scope: str = "all", license_spec=None, category=None):
    """Build one predicate over a meta dict combining scope (all/oneshot/loop),
    a license spec, and a category name (None = any)."""
    lf = license_filter(license_spec)

    def pred(m: dict) -> bool:
        if scope == "oneshot" and not m.get("is_oneshot"):
            return False
        if scope == "loop" and m.get("is_oneshot"):
            return False
        if category and (m.get("category") or "uncategorized") != category:
            return False
        if lf and not lf(m):
            return False
        return True

    return pred
