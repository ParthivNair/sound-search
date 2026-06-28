"""Pure metadata predicates + badge formatting shared by the CLI and the GUI.

Kept free of Typer (and Qt) so either front-end can import them without pulling in
the other's framework.
"""

from __future__ import annotations


def flags(meta: dict) -> str:
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


def license_filter(spec: str | None):
    """Predicate over a meta dict from a `--license` spec (cc0 / by / free / substring)."""
    if not spec:
        return None
    s = spec.lower()
    if s == "free":  # no obligations: safe to use anywhere
        return lambda m: not (m.get("requires_attribution") or m.get("non_commercial") or m.get("no_derivatives"))
    return lambda m: s in (m.get("license_name") or "").lower()


def tags_filter(specs):
    """Case-insensitive substring match; OR across the given tags."""
    if not specs:
        return None
    needles = [s.lower() for s in specs]
    return lambda m: any(n in t.lower() for t in (m.get("tags") or []) for n in needles)
