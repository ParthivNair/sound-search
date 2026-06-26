"""CLAP embedding wrapper (lazy singleton).

Loads the pinned non-fusion checkpoint once per process and exposes audio/text
embedding in the shared 512-d space. Vectors are L2-normalized so cosine
similarity (and L2-KNN over normalized vectors) is valid across modalities.
"""

from __future__ import annotations

import os

import numpy as np

from . import config

# Quiet transformers' load report before laion_clap imports it.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

_model = None


def get_model():
    """Load CLAP once (the general 630k checkpoint = config.CLAP_CHECKPOINT).

    laion_clap prints its full per-layer weight list to stdout on load; we
    capture that into a throwaway buffer so the CLI stays clean.
    """
    global _model
    if _model is None:
        import contextlib
        import io

        import laion_clap

        with contextlib.redirect_stdout(io.StringIO()):
            m = laion_clap.CLAP_Module(enable_fusion=False)
            m.load_ckpt()  # default download is 630k-audioset-best.pt (the pinned checkpoint)
        _model = m
    return _model


def _l2(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-9)


def embed_audio_batch(waves: list[np.ndarray]) -> np.ndarray:
    """Embed a list of 48 kHz mono float32 waveforms -> (N, 512) normalized."""
    model = get_model()
    out = []
    for i in range(0, len(waves), 8):
        batch = waves[i : i + 8]
        maxlen = max(len(w) for w in batch)
        arr = np.zeros((len(batch), maxlen), dtype=np.float32)
        for j, w in enumerate(batch):
            arr[j, : len(w)] = w
        e = model.get_audio_embedding_from_data(x=arr, use_tensor=False)
        out.append(np.asarray(e, dtype=np.float32))
    return _l2(np.concatenate(out, axis=0))


def embed_audio(wave: np.ndarray) -> np.ndarray:
    return embed_audio_batch([wave])[0]


def embed_text(text: str) -> np.ndarray:
    model = get_model()
    e = np.asarray(model.get_text_embedding([text], use_tensor=False), dtype=np.float32)
    return _l2(e)[0]
