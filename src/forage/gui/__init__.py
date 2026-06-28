"""Forage desktop UI (PySide6). Optional — installed via `pip install 'forage[gui]'`.

`launch()` is the only symbol the CLI imports; it pulls in PySide6 lazily so a
missing-Qt install surfaces as a clean ImportError the CLI turns into an install hint.
"""

from __future__ import annotations


def launch() -> int:
    from .app import run  # imports PySide6; ImportError bubbles to the CLI guard
    return run()
