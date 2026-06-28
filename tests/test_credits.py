"""Tests for `forage credits` — scoping (hash/stem), obligation prose, and the
rendered manifest. Embedding is monkeypatched; the sqlite-vec store runs for real."""

from __future__ import annotations

import shutil

import numpy as np
import soundfile as sf

from forage import audio, credits, licensing
from forage.index import SqliteVecStore
from forage.library import sha256_file


def _wav(path, freq=440.0, seconds=0.3):
    t = np.linspace(0, seconds, int(audio.SR * seconds), endpoint=False)
    sf.write(str(path), (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32), audio.SR)


def _meta(fid, file_hash, filename, **over):
    sid = fid.split("-")[-1]
    base = dict(
        forage_id=fid, source="freesound", source_id=sid, file_hash=file_hash,
        filename=filename, title=fid, license_name="CC0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        attribution_username="bob", attribution_url=f"https://freesound.org/s/{sid}/",
        requires_attribution=False, non_commercial=False, share_alike=False,
        no_derivatives=False, tags=["t"], duration_ms=300,
        checkpoint_id="630k-audioset-best.pt", embedding_dim=512, added_at="now",
    )
    base.update(over)
    return base


def _build_lib(tmp_path, monkeypatch):
    """A 2-sound library on disk: freesound-1 (CC0), freesound-2 (CC-BY-NC)."""
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    import forage.config as cfg

    cfg.samples_dir().mkdir(parents=True, exist_ok=True)
    store = SqliteVecStore(db_path=cfg.db_path(), dim=512)
    rng = np.random.default_rng(0)

    f1 = cfg.samples_dir() / "freesound-1.wav"
    _wav(f1, 440)
    store.add(_meta("freesound-1", sha256_file(f1), "freesound-1.wav"),
              rng.standard_normal(512).astype(np.float32))

    f2 = cfg.samples_dir() / "freesound-2.wav"
    _wav(f2, 660)
    store.add(_meta("freesound-2", sha256_file(f2), "freesound-2.wav",
                    license_name="CC-BY-NC", license_url="http://creativecommons.org/licenses/by-nc/3.0/",
                    requires_attribution=True, non_commercial=True),
              rng.standard_normal(512).astype(np.float32))
    return store, cfg


# -- obligation prose -------------------------------------------------------

def test_obligations_prose_per_license():
    assert "No obligation" in licensing.obligations({"license_name": "CC0"})[0]
    assert any("unknown" in s.lower() for s in licensing.obligations({"license_name": "Unknown"}))

    by = {"license_name": "CC-BY", "requires_attribution": True,
          "attribution_username": "bob", "attribution_url": "u"}
    assert any("attribution required" in s for s in licensing.obligations(by))

    nc = {"license_name": "CC-BY-NC", "requires_attribution": True, "non_commercial": True,
          "attribution_username": "bob"}
    assert any("Non-commercial" in s for s in licensing.obligations(nc))

    nd = {"license_name": "CC-BY-ND", "requires_attribution": True, "no_derivatives": True,
          "attribution_username": "bob"}
    assert any("No derivatives" in s for s in licensing.obligations(nd))

    sa = {"license_name": "CC-BY-SA", "requires_attribution": True, "share_alike": True,
          "attribution_username": "bob"}
    assert any("Share-alike" in s for s in licensing.obligations(sa))


def test_attribution_line_fallbacks():
    assert licensing.attribution_line({}) == "Credit creator unknown ((no link))"
    line = licensing.attribution_line({"attribution_username": "amy", "license_url": "L"})
    assert line == "Credit amy (L)"


# -- scoping ----------------------------------------------------------------

def test_scope_by_hash(tmp_path, monkeypatch):
    store, cfg = _build_lib(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy2(cfg.samples_dir() / "freesound-1.wav", proj / "kick_take.wav")  # same bytes, renamed
    result = credits.scope_library([str(proj)], store=store)
    assert len(result.matched) == 1 and result.matched[0].how == "hash"
    assert [m["forage_id"] for m in result.metas] == ["freesound-1"]
    assert result.unmatched_files == []


def test_scope_by_stem(tmp_path, monkeypatch):
    store, cfg = _build_lib(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    _wav(proj / "freesound-2.wav", freq=123)          # different bytes -> hash misses, stem hits
    _wav(proj / "freesound-1 (1).wav", freq=321)      # copy marker -> strips to freesound-1
    result = credits.scope_library([str(proj)], store=store)
    hows = {m.meta["forage_id"]: m.how for m in result.matched}
    assert hows == {"freesound-2": "stem", "freesound-1": "stem"}
    assert sorted(m["forage_id"] for m in result.metas) == ["freesound-1", "freesound-2"]


def test_scope_unmatched(tmp_path, monkeypatch):
    store, _ = _build_lib(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    _wav(proj / "some_guitar.wav", freq=200)
    result = credits.scope_library([str(proj)], store=store)
    assert result.metas == []
    assert [p.name for p in result.unmatched_files] == ["some_guitar.wav"]
    md = credits.render_markdown(result, "proj")
    assert "Not from Forage" in md and "some_guitar.wav" in md


def test_whole_library_scope(tmp_path, monkeypatch):
    store, _ = _build_lib(tmp_path, monkeypatch)
    result = credits.scope_library(None, store=store)
    assert result.whole_library is True
    assert sorted(m["forage_id"] for m in result.metas) == ["freesound-1", "freesound-2"]


def test_empty_scope(tmp_path, monkeypatch):
    store, _ = _build_lib(tmp_path, monkeypatch)
    proj = tmp_path / "empty"
    proj.mkdir()
    result = credits.scope_library([str(proj)], store=store)
    assert result.metas == []
    md = credits.render_markdown(result, "empty")
    assert "_No sounds in scope._" in md  # still a valid manifest


# -- rendering --------------------------------------------------------------

def test_nc_nd_warning_emitted(tmp_path, monkeypatch):
    store, _ = _build_lib(tmp_path, monkeypatch)
    result = credits.scope_library(None, store=store)  # includes the CC-BY-NC sound
    md = credits.render_markdown(result, "whole library")
    assert "Release warning" in md and "Non-commercial only" in md


def test_no_warning_for_cc0_only(tmp_path, monkeypatch):
    store, cfg = _build_lib(tmp_path, monkeypatch)
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy2(cfg.samples_dir() / "freesound-1.wav", proj / "freesound-1.wav")  # CC0 only
    result = credits.scope_library([str(proj)], store=store)
    md = credits.render_markdown(result, "proj")
    assert "Release warning" not in md


def test_markdown_structure_and_blurb(tmp_path, monkeypatch):
    store, _ = _build_lib(tmp_path, monkeypatch)
    result = credits.scope_library(None, store=store)
    md = credits.render_markdown(result, "whole library")
    assert md.startswith("# Forage credits — whole library")
    assert "| Title | Creator | License | Must do |" in md
    assert "Generated by Forage. You are responsible" in md
    # only the CC-BY-NC sound requires attribution -> it alone appears in the blurb
    assert "Credits blurb" in md
    blurb_line = next(ln for ln in md.splitlines() if ln.startswith("Contains sounds —"))
    assert "bob" in blurb_line
