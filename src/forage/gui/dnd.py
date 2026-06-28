"""Drag-and-drop path helpers (Qt-free, unit-testable).

The QUrl/QMimeData wrapping lives in the view; this just turns selected metas into a
de-duplicated list of absolute audio paths.
"""

from __future__ import annotations

from pathlib import Path


def paths_for_metas(metas, samples_dir) -> list[Path]:
    seen: set = set()
    out: list[Path] = []
    for m in metas:
        p = Path(samples_dir) / m["filename"]
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
