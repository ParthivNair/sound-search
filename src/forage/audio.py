"""Audio loading for embedding: 48 kHz mono, peak-normalized to -3 dBFS.

Uses librosa/soundfile (never torchaudio.resample, which needs a fragile ffmpeg
backend on Windows). CLAP is fixed at 48 kHz mono.
"""

from __future__ import annotations

import numpy as np

SR = 48_000
TARGET_PEAK = 10 ** (-3.0 / 20.0)  # normalize to -3 dBFS to avoid int16 clipping


def load_audio(path) -> np.ndarray:
    """Load any supported file as float32 mono at 48 kHz, normalized to -3 dBFS."""
    import librosa

    y, _ = librosa.load(str(path), sr=SR, mono=True)
    y = np.asarray(y, dtype=np.float32)
    peak = float(np.max(np.abs(y))) or 1.0
    return (y / peak) * TARGET_PEAK


def duration_ms(wave: np.ndarray) -> int:
    return int(round(len(wave) / SR * 1000))
