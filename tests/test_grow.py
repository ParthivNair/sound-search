"""Grow orchestration tests with a fake client — no network, no CLAP."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from forage import audio, embed, grow


class FakeClient:
    """Stands in for FreesoundClient: canned search results + writes real wavs."""

    def __init__(self, results):
        self.results = results

    def has_oauth(self):
        return True

    def search(self, query, page_size=15, max_duration=None, extra_filter=None):
        return self.results

    def download_original(self, sound_id, dest_path):
        # distinct content per id so file hashes differ
        freq = 100 + (int(sound_id) % 800)
        t = np.linspace(0, 0.3, int(audio.SR * 0.3), endpoint=False)
        sf.write(str(dest_path), (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32), audio.SR)


def _result(sid, license_url, name="snd"):
    return {"id": sid, "name": name, "license": license_url, "username": "bob",
            "url": f"https://freesound.org/s/{sid}/", "tags": ["t"], "type": "wav"}


RESULTS = [
    _result(1, "http://creativecommons.org/publicdomain/zero/1.0/", "CC0 kick"),
    _result(2, "http://creativecommons.org/licenses/by-nc/3.0/", "BY-NC snare"),
]


def _patch_embed(monkeypatch):
    monkeypatch.setattr(embed, "embed_audio",
                        lambda w: np.random.default_rng(len(w)).standard_normal(512).astype(np.float32))


def test_grow_keeps_and_dedups(tmp_path, monkeypatch):
    import forage.config as cfg
    from forage.index import SqliteVecStore

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    _patch_embed(monkeypatch)
    store = SqliteVecStore(db_path=tmp_path / "lib" / "library.db")

    kept, skipped = grow.grow("kick", count=5, store=store, client=FakeClient(RESULTS))
    assert kept == 2 and skipped == 0
    assert store.count() == 2

    # the BY-NC sound carries its obligation flags through to the sidecar
    import json
    meta = json.loads((cfg.metadata_dir() / "freesound-2.json").read_text(encoding="utf-8"))
    assert meta["license_name"] == "CC-BY-NC" and meta["non_commercial"] is True
    assert (cfg.samples_dir() / "freesound-2.wav").exists()

    # re-grow is resumable: both already present -> kept 0
    kept2, skipped2 = grow.grow("kick", count=5, store=store, client=FakeClient(RESULTS))
    assert kept2 == 0 and skipped2 == 2


def test_grow_license_filter(tmp_path, monkeypatch):
    from forage.index import SqliteVecStore

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    _patch_embed(monkeypatch)
    store = SqliteVecStore(db_path=tmp_path / "lib" / "library.db")

    kept, _ = grow.grow("kick", count=5, store=store, client=FakeClient(RESULTS),
                        license_filter=lambda m: m["license_name"] == "CC0")
    assert kept == 1
    assert store.list_all()[0]["license_name"] == "CC0"
