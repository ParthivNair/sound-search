"""Headless construction smoke for the desktop app (skipped if PySide6 is absent).

Builds the QApplication + window offscreen and pushes a fake meta through the real
filter/model pipeline — verifying the Qt wiring without a display, DB, or audio.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


def test_app_builds_and_filters_offscreen(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    from forage.gui.app import build

    app, win, thread, worker = build([])  # constructed, thread NOT started (no DB/CLAP)
    try:
        win.show()
        app.processEvents()
        assert win._model.rowCount() == 0

        win.on_listed([
            {"filename": "freesound-1.wav", "category": "kick", "is_oneshot": True,
             "license_name": "CC0", "title": "Kick 1", "duration_ms": 200},
            {"filename": "freesound-2.wav", "category": "pad", "is_oneshot": False,
             "license_name": "CC-BY", "requires_attribution": True, "title": "Pad", "duration_ms": 4000},
        ])
        app.processEvents()
        assert win._model.rowCount() == 2          # both listed
        assert win._cats.count() == 3              # All + kick + pad

        # selecting the one-shots scope filters client-side, no worker needed
        for b in win._scope_group.buttons():
            if b.property("scope") == "oneshot":
                b.setChecked(True)
        win._apply_filters()
        assert win._model.rowCount() == 1
    finally:
        win.close()


def test_table_selection_to_drag_paths_offscreen(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    from forage.gui.app import build

    app, win, thread, worker = build([])
    try:
        win.on_listed([
            {"filename": "freesound-1.wav", "category": "kick", "is_oneshot": True,
             "license_name": "CC0", "title": "a", "duration_ms": 200},
            {"filename": "freesound-2.wav", "category": "snare", "is_oneshot": True,
             "license_name": "CC0", "title": "b", "duration_ms": 200},
        ])
        app.processEvents()
        win._table.selectAll()
        names = sorted(p.name for p in win._table.selected_paths())
        assert names == ["freesound-1.wav", "freesound-2.wav"]  # drag would carry both files
    finally:
        win.close()
