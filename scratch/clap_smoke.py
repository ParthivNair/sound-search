"""Phase 0 CLAP smoke test (throwaway).

Goal: prove on THIS Windows/Anaconda CPU machine that CLAP installs, loads its
checkpoint, and turns audio + text into a shared-space embedding -- and settle
the embedding dimension empirically (research disagreed: 512 vs 1024).

It synthesizes a few test signals so it needs no downloads beyond the CLAP
checkpoint itself. You may instead pass real WAV paths:

    python scratch/clap_smoke.py                 # synthetic signals
    python scratch/clap_smoke.py a.wav b.wav ...  # your own clips

Success criteria printed at the end:
  * a finite embedding with a stable shape (the dimension we lock for the index)
  * per-clip embedding latency in ms (CPU feasibility for later phases)
  * a text x audio cosine matrix (sanity: percussive query should lean toward the
    noise burst over the pure tone -- indicative only on synthetic audio)
"""

from __future__ import annotations

import sys
import time

import numpy as np

SR = 48_000  # CLAP is fixed at 48 kHz mono
DUR = 3.0
TARGET_PEAK = 10 ** (-3.0 / 20.0)  # normalize to -3 dBFS to avoid int16 clipping


def _normalize(x: np.ndarray) -> np.ndarray:
    x = x.astype(np.float32)
    peak = float(np.max(np.abs(x))) or 1.0
    return (x / peak) * TARGET_PEAK


def synth_signals() -> dict[str, np.ndarray]:
    t = np.linspace(0, DUR, int(SR * DUR), endpoint=False, dtype=np.float32)
    # Percussive: white-noise burst with a fast exponential decay (drum-ish).
    rng = np.random.default_rng(0)
    env = np.exp(-t * 12.0)
    noise_burst = rng.standard_normal(t.shape).astype(np.float32) * env
    # Tonal: steady 220 Hz sine.
    sine = np.sin(2 * np.pi * 220.0 * t)
    # Sweep: 200 -> 2000 Hz chirp.
    chirp = np.sin(2 * np.pi * (200.0 + (1800.0 / DUR) * t) * t)
    return {
        "noise_burst (percussive)": _normalize(noise_burst),
        "sine_220hz (tonal)": _normalize(sine),
        "chirp_200_2000hz": _normalize(chirp),
    }


def load_real(paths: list[str]) -> dict[str, np.ndarray]:
    import librosa  # imported lazily so synthetic mode needs no extra deps

    out: dict[str, np.ndarray] = {}
    for p in paths:
        y, _ = librosa.load(p, sr=SR, mono=True)  # resample to 48k mono via librosa (NOT torchaudio)
        out[p] = _normalize(np.asarray(y, dtype=np.float32))
    return out


def main() -> int:
    paths = sys.argv[1:]
    signals = load_real(paths) if paths else synth_signals()
    labels = list(signals.keys())
    batch = np.stack([signals[k] for k in labels]).astype(np.float32)  # (N, samples)

    print("Loading CLAP (enable_fusion=False). First run downloads ~1.5 GB checkpoint...")
    t0 = time.perf_counter()
    import laion_clap

    model = laion_clap.CLAP_Module(enable_fusion=False)
    model.load_ckpt()  # downloads/loads the default non-fusion 630k checkpoint
    print(f"  model ready in {time.perf_counter() - t0:.1f}s")

    t0 = time.perf_counter()
    audio_emb = model.get_audio_embedding_from_data(x=batch, use_tensor=False)
    audio_dt = time.perf_counter() - t0
    audio_emb = np.asarray(audio_emb, dtype=np.float32)

    queries = [
        "drums",
        "a percussion hit",
        "a pure sine wave tone",
        "vinyl crackle",
    ]
    text_emb = np.asarray(model.get_text_embedding(queries, use_tensor=False), dtype=np.float32)

    def l2(x: np.ndarray) -> np.ndarray:
        return x / (np.linalg.norm(x, axis=1, keepdims=True) + 1e-9)

    cos = l2(text_emb) @ l2(audio_emb).T  # (n_queries, n_audio)

    print("\n=== RESULTS ===")
    print(f"audio embedding shape : {audio_emb.shape}  dtype={audio_emb.dtype}")
    print(f"text  embedding shape : {text_emb.shape}")
    print(f"EMBEDDING_DIM (locked from here) : {audio_emb.shape[1]}")
    print(f"finite                : {np.isfinite(audio_emb).all()}")
    print(f"per-clip embed latency: {audio_dt / len(labels) * 1000:.0f} ms/clip "
          f"({len(labels)} clips in {audio_dt:.2f}s, CPU)")

    print("\ncosine(text query x audio clip):")
    header = "  " + "".join(f"{i:>12}" for i in range(len(labels)))
    print(header)
    for qi, q in enumerate(queries):
        row = "".join(f"{cos[qi, ai]:>12.3f}" for ai in range(len(labels)))
        print(f"{row}   <- {q!r}")
    print("\nclip legend:")
    for i, k in enumerate(labels):
        print(f"  [{i}] {k}")
    print("\nNote: synthetic audio is out-of-distribution for CLAP, so cross-modal")
    print("ranking here is indicative only. Real-material quality is judged in Phase 1.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
