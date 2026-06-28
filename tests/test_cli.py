"""CLI-level tests: the `--tags` filter helper and the search gap-hint."""

from __future__ import annotations

import forage.embed as embed_mod
import forage.index as index_mod
from forage.cli import _license_filter, _tags_filter, app
from forage.index import Hit


# -- tag filtering ----------------------------------------------------------

def test_tags_filter_substring_and_or():
    rows = [{"tags": ["Kick", "drum"]}, {"tags": ["snare"]}, {"tags": []}]
    tf = _tags_filter(["kick"])
    assert [tf(m) for m in rows] == [True, False, False]          # case-insensitive substring
    tf2 = _tags_filter(["sna", "drum"])
    assert [tf2(m) for m in rows] == [True, True, False]          # OR across tags
    assert _tags_filter(None) is None and _tags_filter([]) is None


def test_license_and_tags_compose():
    rows = [
        {"license_name": "CC0", "requires_attribution": False, "non_commercial": False,
         "no_derivatives": False, "tags": ["kick"]},
        {"license_name": "CC-BY", "requires_attribution": True, "non_commercial": False,
         "no_derivatives": False, "tags": ["kick"]},
    ]
    lf, tf = _license_filter("free"), _tags_filter(["kick"])
    out = [m for m in rows if lf(m) and tf(m)]
    assert len(out) == 1 and out[0]["license_name"] == "CC0"


# -- search gap-hint --------------------------------------------------------

class _GapStore:
    """Minimal stand-in returning a single hit at a chosen score."""

    def __init__(self, score):
        self._score = score

    def count(self):
        return 1

    def search(self, vec, limit, license_filter=None):
        meta = {"filename": "freesound-1.wav", "title": "thing", "license_name": "CC0",
                "attribution_username": "bob"}
        return [Hit("freesound-1", self._score, meta)]


def _run_search(monkeypatch, score):
    from typer.testing import CliRunner

    monkeypatch.setattr(embed_mod, "embed_text", lambda q: None)
    monkeypatch.setattr(index_mod, "SqliteVecStore", lambda *a, **k: _GapStore(score))
    return CliRunner().invoke(app, ["search", "obscure thing"])


def test_gap_hint_shown_for_weak_top_score(monkeypatch):
    result = _run_search(monkeypatch, 0.10)  # below SEARCH_GAP_THRESHOLD (0.35)
    assert result.exit_code == 0
    assert "hint:" in result.output and "forage grow" in result.output


def test_no_gap_hint_for_strong_top_score(monkeypatch):
    result = _run_search(monkeypatch, 0.90)  # well above threshold
    assert result.exit_code == 0
    assert "hint:" not in result.output


# -- export-sfz / browse CLI smoke ------------------------------------------

def test_export_sfz_and_browse_cli(tmp_path, monkeypatch):
    import numpy as np
    import soundfile as sf
    from typer.testing import CliRunner

    import forage.config as cfg
    from forage import audio
    from forage.cli import app
    from forage.index import SqliteVecStore

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    cfg.samples_dir().mkdir(parents=True, exist_ok=True)
    t = np.linspace(0, 0.2, int(audio.SR * 0.2), endpoint=False)
    sf.write(str(cfg.samples_dir() / "freesound-1.wav"),
             (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), audio.SR)

    store = SqliteVecStore(db_path=cfg.db_path())  # default dim 512, matches CLI store
    store.add(dict(
        forage_id="freesound-1", source="freesound", source_id="1", file_hash="h1",
        filename="freesound-1.wav", title="kick", license_name="CC0", license_url=None,
        attribution_username=None, attribution_url=None, requires_attribution=False,
        non_commercial=False, share_alike=False, no_derivatives=False, tags=[],
        duration_ms=300, checkpoint_id="630k-audioset-best.pt", embedding_dim=512,
        added_at="now", category="kick", is_oneshot=True,
    ), np.ones(512, dtype=np.float32))
    store.close()

    r = CliRunner().invoke(app, ["export-sfz"])
    assert r.exit_code == 0 and "region" in r.output
    assert (cfg.forage_home() / "instruments" / "forage-kit.sfz").exists()

    r2 = CliRunner().invoke(app, ["browse"])
    assert r2.exit_code == 0
    assert (cfg.forage_home() / "browse" / "kick").is_dir()
