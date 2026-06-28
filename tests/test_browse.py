"""Browse folder tree: builds per-category, idempotent, hardlink-or-copy fallback."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from forage import audio, browse, config
from forage.index import SqliteVecStore


def _wav(path, freq=440.0):
    t = np.linspace(0, 0.2, int(audio.SR * 0.2), endpoint=False)
    sf.write(str(path), (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32), audio.SR)


def _meta(fid, category, title=None):
    return dict(
        forage_id=fid, source="test", source_id=None, file_hash=fid, filename=f"{fid}.wav",
        title=title or fid, license_name="CC0", license_url=None, attribution_username=None,
        attribution_url=None, requires_attribution=False, non_commercial=False,
        share_alike=False, no_derivatives=False, tags=[], duration_ms=200,
        checkpoint_id="630k-audioset-best.pt", embedding_dim=8, added_at="now",
        category=category, is_oneshot=True,
    )


def _store_with(tmp_path, items):
    config.samples_dir().mkdir(parents=True, exist_ok=True)
    store = SqliteVecStore(db_path=config.db_path(), dim=8)
    rng = np.random.default_rng(0)
    for fid, cat in items:
        _wav(config.samples_dir() / f"{fid}.wav")
        store.add(_meta(fid, cat), rng.standard_normal(8).astype(np.float32))
    return store


def test_builds_tree_and_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    store = _store_with(tmp_path, [("freesound-1", "kick"), ("freesound-2", "snare")])
    rep = browse.browse(store)
    root = config.forage_home() / "browse"
    assert (root / "kick").is_dir() and (root / "snare").is_dir()
    assert rep["linked"] + rep["copied"] == 2 and rep["missing"] == 0
    assert len(list((root / "kick").glob("*.wav"))) == 1

    rep2 = browse.browse(store)  # wipe + rebuild
    assert rep2["linked"] + rep2["copied"] == 2
    store.close()


def test_uncategorized_bucket_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    store = _store_with(tmp_path, [("freesound-1", None)])
    # add a row whose audio file does not exist -> counted missing
    store.add(_meta("freesound-9", "kick"), np.ones(8, dtype=np.float32) * 0.2)
    rep = browse.browse(store)
    assert (config.forage_home() / "browse" / "uncategorized").is_dir()
    assert rep["missing"] == 1
    store.close()


def test_copy_fallback_when_hardlink_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    store = _store_with(tmp_path, [("freesound-1", "kick")])

    def _boom(*a, **k):
        raise OSError("no hardlinks here")

    monkeypatch.setattr(browse.os, "link", _boom)
    rep = browse.browse(store)
    assert rep["copied"] == 1 and rep["linked"] == 0
    store.close()
