"""Reindex parity: rebuilding library.db from sidecars (re-embedding audio) must
reproduce the same rows and the same search ranking. Embedding is monkeypatched to
a deterministic, content-derived vector so distinct audio gets distinct, stable
vectors and re-embedding the same file is identical."""

from __future__ import annotations

import hashlib

import numpy as np
import soundfile as sf

from forage import audio, embed, grow, library
from forage.index import SqliteVecStore


def _wav(path, freq=440.0, seconds=0.3):
    t = np.linspace(0, seconds, int(audio.SR * seconds), endpoint=False)
    sf.write(str(path), (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32), audio.SR)


def _content_embed(w):
    seed = int.from_bytes(hashlib.sha256(np.ascontiguousarray(w).tobytes()).digest()[:8], "big")
    return np.random.default_rng(seed).standard_normal(512).astype(np.float32)


def test_reindex_parity(tmp_path, monkeypatch):
    import forage.config as cfg

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    monkeypatch.setattr(embed, "embed_audio", _content_embed)

    src = tmp_path / "src"
    src.mkdir()
    for i, freq in enumerate([300, 500, 700, 900], 1):
        _wav(src / f"s{i}.wav", freq)
    store = SqliteVecStore()
    added, _ = library.import_folder(src, store=store)
    assert added == 4

    before_ids = {m["forage_id"] for m in store.list_all()}
    probe = sorted(before_ids)[0]
    rank_before = [h.forage_id for h in store.search(store.get_vector(probe), top_k=4)]
    store.close()  # release the file lock before deleting the DB (Windows)

    # Nuke the derived index; sidecars + audio (the source of truth) remain.
    cfg.db_path().unlink()
    rep = grow.reindex(embed_fn=_content_embed)
    assert rep["rebuilt"] == 4
    assert rep["skipped_invalid"] == 0 and rep["missing_audio"] == 0

    store2 = SqliteVecStore()
    after_ids = {m["forage_id"] for m in store2.list_all()}
    assert after_ids == before_ids
    rank_after = [h.forage_id for h in store2.search(store2.get_vector(probe), top_k=4)]
    assert rank_after == rank_before  # identical ranking proves sidecars are durable truth
    store2.close()


def test_reindex_skips_missing_audio_and_invalid(tmp_path, monkeypatch):
    import json

    import forage.config as cfg

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    monkeypatch.setattr(embed, "embed_audio", _content_embed)

    src = tmp_path / "src"
    src.mkdir()
    _wav(src / "a.wav", 440)
    store0 = SqliteVecStore()
    library.import_folder(src, store=store0)
    store0.close()  # release the file lock before deleting the DB (Windows)
    cfg.db_path().unlink()

    # one orphan sidecar (audio missing) and one malformed sidecar
    cfg.metadata_dir().mkdir(parents=True, exist_ok=True)
    (cfg.metadata_dir() / "freesound-999.json").write_text(json.dumps({
        "forage_id": "freesound-999", "source": "freesound", "file_hash": "x",
        "filename": "freesound-999.wav", "title": "ghost", "license_name": "CC0",
        "requires_attribution": False, "non_commercial": False, "share_alike": False,
        "no_derivatives": False, "tags": [],
    }), encoding="utf-8")
    (cfg.metadata_dir() / "broken.json").write_text("{ not json", encoding="utf-8")

    rep = grow.reindex(embed_fn=_content_embed)
    assert rep["rebuilt"] == 1
    assert rep["missing_audio"] == 1
    assert rep["skipped_invalid"] == 1
    store2 = SqliteVecStore()
    assert store2.count() == 1
    store2.close()
