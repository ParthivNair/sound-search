"""The GUI's Qt-free seams — filtering, row formatting, drag paths, reveal command.
These import no PySide6, so they run in the normal headless suite."""

from __future__ import annotations

import sys

import pytest

from forage.gui import reveal as reveal_mod
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


# -- reveal platform dispatch --------------------------------------------
# Host-independent by construction:
#   * The win32 input r"C:\x\y.wav" is os.path.normpath-stable on BOTH POSIX and
#     Windows (backslashes preserved, no separator translation), so the expected
#     argv is byte-identical regardless of which OS runs the test.
#   * The darwin path is passed through str() only (no normpath), so a POSIX-style
#     path is exact everywhere.
# The `platform` seam is injected explicitly so every case runs on any host.

@pytest.mark.parametrize(
    "platform, path, expected",
    [
        ("win32", r"C:\x\y.wav", ["explorer", "/select,C:\\x\\y.wav"]),
        ("darwin", "/a/b/c.wav", ["open", "-R", "/a/b/c.wav"]),
    ],
)
def test_reveal_command_dispatch(platform, path, expected):
    assert reveal_command(path, platform=platform) == expected


def test_reveal_command_win32_byte_identical():
    # Must stay at least as strong as the original assertions: exact argv equality
    # for the current Windows behavior, with `/select,` glued to the normalized path.
    assert reveal_command(r"C:\x\y.wav", platform="win32") == [
        "explorer",
        "/select,C:\\x\\y.wav",
    ]


@pytest.mark.parametrize("platform", ["linux", "cygwin", "freebsd7", "aix", ""])
def test_reveal_command_unsupported_platform_raises(platform):
    with pytest.raises(NotImplementedError):
        reveal_command(r"C:\x\y.wav", platform=platform)


def test_reveal_command_defaults_to_sys_platform(monkeypatch):
    # With no explicit platform, the module must read sys.platform at CALL time
    # (i.e. `platform = platform if platform is not None else sys.platform` in the
    # body — NOT captured as a def-time default), so patching sys.platform here
    # must change the dispatch. reveal.py must `import sys` for this to resolve.
    monkeypatch.setattr(sys, "platform", "darwin")
    assert reveal_command("/a/b/c.wav") == ["open", "-R", "/a/b/c.wav"]
    monkeypatch.setattr(sys, "platform", "win32")
    assert reveal_command(r"C:\x\y.wav") == ["explorer", "/select,C:\\x\\y.wav"]


@pytest.mark.parametrize(
    "platform, expected",
    [("win32", "Reveal in Explorer"), ("darwin", "Reveal in Finder")],
)
def test_reveal_label_dispatch(platform, expected):
    assert reveal_mod.reveal_label(platform=platform) == expected


def test_reveal_label_defaults_to_sys_platform(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert reveal_mod.reveal_label() == "Reveal in Finder"
    monkeypatch.setattr(sys, "platform", "win32")
    assert reveal_mod.reveal_label() == "Reveal in Explorer"
