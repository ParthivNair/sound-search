"""The GUI's Qt-free seams — filtering, row formatting, drag paths, reveal command.
These import no PySide6, so they run in the normal headless suite."""

from __future__ import annotations

from forage.gui.dnd import paths_for_metas
from forage.gui.filters import combine_predicates
from forage.gui.models_logic import build_row, category_counts
from forage.gui.reveal import reveal_command


def test_combine_predicates_scope_license_category():
    metas = [
        {"is_oneshot": True, "category": "kick", "license_name": "CC0"},
        {"is_oneshot": False, "category": "pad", "license_name": "CC-BY", "requires_attribution": True},
    ]
    assert [combine_predicates("oneshot")(m) for m in metas] == [True, False]
    assert [combine_predicates("loop")(m) for m in metas] == [False, True]
    assert [combine_predicates("all", "free")(m) for m in metas] == [True, False]  # 2nd needs attribution
    assert [combine_predicates("all", None, "pad")(m) for m in metas] == [False, True]


def test_build_row():
    m = {"title": "Kick 1", "category": "kick", "license_name": "CC0", "duration_ms": 1200}
    row = build_row(m, score=0.873)
    assert row[0] == "Kick 1" and row[1] == "kick" and row[3] == "1.2s" and row[4] == "+0.873"
    assert build_row(m)[4] == ""                       # no score in browse mode
    assert build_row({"forage_id": "x"})[1] == "uncategorized"


def test_category_counts():
    counts = category_counts([{"category": "kick"}, {"category": "kick"}, {"category": None}])
    assert counts[0] == ("All", 3)
    assert ("kick", 2) in counts and ("uncategorized", 1) in counts


def test_paths_for_metas_dedup(tmp_path):
    metas = [{"filename": "freesound-1.wav"}, {"filename": "freesound-1.wav"}, {"filename": "freesound-2.wav"}]
    paths = paths_for_metas(metas, tmp_path)
    assert len(paths) == 2 and all(p.parent == tmp_path for p in paths)


def test_reveal_command():
    cmd = reveal_command(r"C:\x\y.wav")
    assert cmd[0] == "explorer" and cmd[1].startswith("/select,") and cmd[1].endswith("y.wav")
