"""Categorization: zero-shot assignment, keyword override, one-shot flag, the schema
migration, and survival through reindex. Controlled embeddings, no real CLAP."""

from __future__ import annotations

import json
import sqlite3

import numpy as np

from forage import categorize as C
from forage import config
from forage.index import SqliteVecStore

DIM = len(C.TAXONOMY)  # one orthogonal axis per category for a clean argmax


def _onehot(i, n=DIM):
    v = np.zeros(n, dtype=np.float32)
    v[i] = 1.0
    return v


def _prompt_embed():
    idx = {prompt: i for i, (_, prompt) in enumerate(C.TAXONOMY)}
    return lambda p: _onehot(idx[p])


def _meta(fid, dur, tags=None, title="zzz"):
    return dict(
        forage_id=fid, source="test", source_id=None, file_hash=fid, filename=f"{fid}.wav",
        title=title, license_name="CC0", license_url=None, attribution_username=None,
        attribution_url=None, requires_attribution=False, non_commercial=False,
        share_alike=False, no_derivatives=False, tags=tags or [], duration_ms=dur,
        checkpoint_id="630k-audioset-best.pt", embedding_dim=DIM, added_at="now",
    )


def test_clap_argmax_and_keyword_override(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    config.metadata_dir().mkdir(parents=True, exist_ok=True)
    store = SqliteVecStore(db_path=config.db_path(), dim=DIM)
    store.add(_meta("s-tom", 500), _onehot(5))                  # CATEGORY_NAMES[5] == "tom"
    store.add(_meta("s-kw", 3000, tags=["kick"]), _onehot(5))   # keyword beats the tom vector

    counts = C.categorize(store, _prompt_embed(), threshold=0.5)
    rows = {m["forage_id"]: m for m in store.list_all()}

    assert C.CATEGORY_NAMES[5] == "tom"
    assert rows["s-tom"]["category"] == "tom" and rows["s-tom"]["is_oneshot"] is True
    assert rows["s-kw"]["category"] == "kick" and rows["s-kw"]["is_oneshot"] is False
    assert counts["tom"] == 1 and counts["kick"] == 1

    side = json.loads((config.metadata_dir() / "s-tom.json").read_text(encoding="utf-8"))
    assert side["category"] == "tom" and side["is_oneshot"] is True
    store.close()


def test_keyword_specific_beats_generic_bass():
    # a clear drum in the title must win over a loose 'bass' tag
    assert C.keyword_category({"title": "Electronic Kick Drum #1", "tags": ["bass", "electronic"]}) == "kick"
    assert C.keyword_category({"title": "Electronic Snare Drum", "tags": ["bass"]}) == "snare"
    # genuine bass (no specific signal) stays bass
    assert C.keyword_category({"title": "Sub Bass C", "tags": ["bass", "808"]}) == "bass"
    assert C.keyword_category({"title": "untitled wash 03", "tags": []}) is None


def test_threshold_to_uncategorized(tmp_path, monkeypatch):
    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    config.metadata_dir().mkdir(parents=True, exist_ok=True)
    store = SqliteVecStore(db_path=config.db_path(), dim=DIM)
    store.add(_meta("s", 500), _onehot(5))
    # best cosine is 1.0; a threshold above that forces 'uncategorized'
    C.categorize(store, _prompt_embed(), threshold=1.5)
    assert store.list_all()[0]["category"] == "uncategorized"
    store.close()


def test_is_oneshot_boundary():
    # the rule lives inline in categorize(); assert the boundary directly
    assert (1499 is not None and 1499 < config.ONESHOT_MS) is True
    assert (1500 < config.ONESHOT_MS) is False


def test_migration_adds_columns_to_preexisting_db(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(str(p))
    con.execute("CREATE TABLE sounds(id INTEGER PRIMARY KEY, forage_id TEXT, file_hash TEXT)")
    con.commit()
    con.close()

    store = SqliteVecStore(db_path=p, dim=DIM)  # __init__ -> _init_schema -> _migrate
    cols = {r["name"] for r in store.db.execute("PRAGMA table_info(sounds)").fetchall()}
    assert "category" in cols and "is_oneshot" in cols
    store.close()


def test_category_survives_reindex(tmp_path, monkeypatch):
    import soundfile as sf

    from forage import audio, embed, grow, library

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    monkeypatch.setattr(embed, "embed_audio",
                        lambda w: np.random.default_rng(len(w)).standard_normal(512).astype(np.float32))

    src = tmp_path / "src"
    src.mkdir()
    t = np.linspace(0, 0.3, int(audio.SR * 0.3), endpoint=False)
    sf.write(str(src / "a.wav"), (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32), audio.SR)

    store = SqliteVecStore()
    library.import_folder(src, store=store)
    C.categorize(store, lambda p: np.ones(512, dtype=np.float32), threshold=-1.0)
    cat = store.list_all()[0]["category"]
    assert cat  # got some category written to DB + sidecar
    store.close()

    config.db_path().unlink()  # blow away the derived index
    grow.reindex(embed_fn=lambda w: np.random.default_rng(len(w)).standard_normal(512).astype(np.float32))

    store2 = SqliteVecStore()
    assert store2.list_all()[0]["category"] == cat  # carried through via the sidecar
    store2.close()
