"""Import / dedup / sidecar tests. Embedding is monkeypatched so no CLAP/torch
is loaded; audio decode (librosa) and the sqlite-vec store run for real."""

from __future__ import annotations

import numpy as np
import soundfile as sf

from forage import audio, embed, library


def _write_wav(path, seconds=0.4, freq=440.0):
    t = np.linspace(0, seconds, int(audio.SR * seconds), endpoint=False)
    y = (0.2 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    sf.write(str(path), y, audio.SR)


def test_import_dedup_and_sidecars(tmp_path, monkeypatch):
    import forage.config as cfg

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    monkeypatch.setattr(
        embed, "embed_audio",
        lambda w: np.random.default_rng(0).standard_normal(cfg.EMBEDDING_DIM).astype(np.float32),
    )

    src = tmp_path / "src"
    src.mkdir()
    _write_wav(src / "a.wav", freq=440)
    _write_wav(src / "b.wav", freq=880)

    added, skipped = library.import_folder(src)
    assert (added, skipped) == (2, 0)

    assert len(list(cfg.metadata_dir().glob("*.json"))) == 2
    assert len(list(cfg.samples_dir().glob("*.wav"))) == 2

    # re-import of identical bytes dedups (idempotent grow/import)
    added2, skipped2 = library.import_folder(src)
    assert (added2, skipped2) == (0, 2)


def test_eval_sidecar_carries_license(tmp_path, monkeypatch):
    """A clip with a sibling Freesound eval-sidecar inherits its license + obligations."""
    import json

    import forage.config as cfg

    monkeypatch.setenv("FORAGE_HOME", str(tmp_path / "lib"))
    monkeypatch.setattr(
        embed, "embed_audio",
        lambda w: np.random.default_rng(1).standard_normal(cfg.EMBEDDING_DIM).astype(np.float32),
    )

    src = tmp_path / "src"
    src.mkdir()
    _write_wav(src / "999.wav")
    (src / "999.json").write_text(json.dumps({
        "freesound_id": 999, "title": "Test BY-NC", "tags": ["foo"],
        "license_name": "CC-BY-NC", "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "attribution_username": "alice", "requires_attribution": True, "non_commercial": True,
    }), encoding="utf-8")

    added, _ = library.import_folder(src)
    assert added == 1
    meta = json.loads((cfg.metadata_dir() / "freesound-999.json").read_text(encoding="utf-8"))
    assert meta["forage_id"] == "freesound-999"
    assert meta["source"] == "freesound"
    assert meta["license_name"] == "CC-BY-NC"
    assert meta["requires_attribution"] is True
    assert meta["non_commercial"] is True
