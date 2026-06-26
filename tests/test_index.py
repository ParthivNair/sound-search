"""Fast unit tests for the vector index (no CLAP/torch — numpy + sqlite_vec only)."""

from __future__ import annotations

import numpy as np
import pytest

from forage.index import SqliteVecStore

DIM = 8


def _meta(i: int, license_name: str = "CC0", nc: bool = False, ra: bool = False) -> dict:
    fid = f"t-{i}"
    return dict(
        forage_id=fid, source="test", source_id=None, file_hash=f"hash{i}",
        filename=f"{fid}.wav", title=f"sound {i}", license_name=license_name, license_url=None,
        attribution_username="bob", attribution_url=None, requires_attribution=ra,
        non_commercial=nc, share_alike=False, no_derivatives=False, tags=["x"],
        duration_ms=100, checkpoint_id="630k-audioset-best.pt", embedding_dim=DIM, added_at="now",
    )


def test_roundtrip_and_dedup(tmp_path):
    s = SqliteVecStore(db_path=tmp_path / "t.db", dim=DIM)
    rng = np.random.default_rng(0)
    vecs = {i: rng.standard_normal(DIM).astype(np.float32) for i in range(10)}
    for i, v in vecs.items():
        assert s.add(_meta(i), v) is True
    assert s.count() == 10

    # dedup by file_hash: re-adding is a no-op
    assert s.add(_meta(0), vecs[0]) is False
    assert s.count() == 10

    # nearest-self is the top hit at cosine ~1.0
    hits = s.search(vecs[3], top_k=1)
    assert hits[0].forage_id == "t-3"
    assert hits[0].score > 0.99

    # audio->audio similar excludes the query itself
    sim = s.similar("t-3", top_k=3)
    assert sim and all(h.forage_id != "t-3" for h in sim)

    # stored vector round-trips and is normalized
    gv = s.get_vector("t-3")
    assert gv.shape == (DIM,)
    assert abs(float(np.linalg.norm(gv)) - 1.0) < 1e-4

    assert s.has_hash("hash5") and not s.has_hash("nope")


def test_license_filter(tmp_path):
    s = SqliteVecStore(db_path=tmp_path / "t.db", dim=DIM)
    rng = np.random.default_rng(1)
    s.add(_meta(0, "CC0"), rng.standard_normal(DIM).astype(np.float32))
    s.add(_meta(1, "Attribution", ra=True), rng.standard_normal(DIM).astype(np.float32))
    s.add(_meta(2, "Attribution-NonCommercial", nc=True, ra=True), rng.standard_normal(DIM).astype(np.float32))
    q = rng.standard_normal(DIM).astype(np.float32)
    cc0 = s.search(q, top_k=10, license_filter=lambda m: m["license_name"] == "CC0")
    assert len(cc0) == 1 and cc0[0].meta["license_name"] == "CC0"


def test_checkpoint_guard(tmp_path):
    import forage.config as cfg

    p = tmp_path / "t.db"
    SqliteVecStore(db_path=p, dim=DIM).close()  # records the current checkpoint
    old = cfg.CLAP_CHECKPOINT
    cfg.CLAP_CHECKPOINT = "different-checkpoint.pt"
    try:
        with pytest.raises(RuntimeError):
            SqliteVecStore(db_path=p, dim=DIM)
    finally:
        cfg.CLAP_CHECKPOINT = old
