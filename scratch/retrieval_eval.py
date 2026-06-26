"""Phase 1 retrieval-quality eval (throwaway, interactive) — the GO/RETHINK gate.

Embeds every clip in scratch/clips/ under BOTH candidate checkpoints (general
630k vs music_audioset) and lets you judge text->audio and audio->audio
retrieval BY EAR, side by side, so we can:
  (1) decide GO (retrieval is good enough to build on) or RETHINK, and
  (2) lock which checkpoint to pin in config for every later phase.

Also includes a hybrid CLAP+tag re-rank — the pre-designed RETHINK fallback —
so a weak pure-CLAP result triggers a planned pivot, not a scramble.

Run inside the `forage` conda env after fetch_eval_clips.py:
    python scratch/retrieval_eval.py

REPL commands:
    <free text>        text->audio: top-5 per checkpoint
    h <free text>      hybrid CLAP+tag re-rank (general checkpoint)
    sim <id>           audio->audio neighbors of a library clip (per checkpoint)
    play <id>          open that clip in the default player (to audition)
    queries            run every line of eval_queries.txt through text->audio
    q                  quit
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import json
import numpy as np

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
QUERIES_FILE = HERE / "eval_queries.txt"
SR = 48_000
TARGET_PEAK = 10 ** (-3.0 / 20.0)
TOPK = 5

# Candidate checkpoints. 'general' replicates the Phase 0 smoke config exactly.
CHECKPOINTS = [
    {"key": "general", "amodel": "HTSAT-tiny", "ckpt": None},
    {"key": "music", "amodel": "HTSAT-base", "repo": "lukewys/laion_clap",
     "file": "music_audioset_epoch_15_esc_90.14.pt"},
]


def load_clips() -> tuple[list[dict], np.ndarray]:
    import librosa

    metas, waves = [], []
    for jf in sorted(CLIPS.glob("*.json")):
        meta = json.loads(jf.read_text(encoding="utf-8"))
        audio = CLIPS / f"{meta['freesound_id']}.mp3"
        if not audio.exists():
            continue
        try:
            y, _ = librosa.load(str(audio), sr=SR, mono=True)
        except Exception as e:
            print(f"  skip {audio.name}: {e}")
            continue
        peak = float(np.max(np.abs(y))) or 1.0
        metas.append(meta)
        waves.append((y / peak * TARGET_PEAK).astype(np.float32))
    if not metas:
        sys.exit(f"No clips in {CLIPS}. Run fetch_eval_clips.py first.")
    return metas, waves  # waves is a ragged list


def l2(x: np.ndarray) -> np.ndarray:
    return x / (np.linalg.norm(x, axis=-1, keepdims=True) + 1e-9)


def embed_all(model, waves: list[np.ndarray]) -> np.ndarray:
    embs = []
    for i in range(0, len(waves), 8):
        batch = waves[i:i + 8]
        maxlen = max(len(w) for w in batch)
        arr = np.zeros((len(batch), maxlen), dtype=np.float32)
        for j, w in enumerate(batch):
            arr[j, : len(w)] = w
        e = model.get_audio_embedding_from_data(x=arr, use_tensor=False)
        embs.append(np.asarray(e, dtype=np.float32))
    return l2(np.concatenate(embs, axis=0))


def load_model(spec: dict):
    import laion_clap

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel=spec["amodel"])
    if "file" in spec:  # download a specific checkpoint (e.g. the music model) from HF
        from huggingface_hub import hf_hub_download

        path = hf_hub_download(spec["repo"], spec["file"])
        model.load_ckpt(path)
    else:  # default download matching the config (general 630k)
        model.load_ckpt()
    return model


def flags_str(m: dict) -> str:
    parts = [m.get("license_name", "?")]
    if m.get("requires_attribution"):
        parts.append("ATTRIB")
    if m.get("non_commercial"):
        parts.append("NC")
    if m.get("share_alike"):
        parts.append("SA")
    if m.get("no_derivatives"):
        parts.append("ND")
    return ",".join(parts)


def show(metas, scores, k=TOPK):
    order = np.argsort(-scores)[:k]
    for rank, idx in enumerate(order, 1):
        m = metas[idx]
        print(f"   {rank}. {scores[idx]:+.3f}  [{m['freesound_id']}] {m.get('title','')[:44]:44}"
              f"  ({flags_str(m)})  by {m.get('attribution_username','?')}")


def main() -> int:
    metas, waves = load_clips()
    print(f"Loaded {len(metas)} eval clips. Embedding under each checkpoint...")
    models, audio_embs = {}, {}
    for spec in CHECKPOINTS:
        try:
            t0 = time.perf_counter()
            m = load_model(spec)
            audio_embs[spec["key"]] = embed_all(m, waves)
            models[spec["key"]] = m
            print(f"  [{spec['key']}] embedded in {time.perf_counter()-t0:.1f}s")
        except Exception as e:
            print(f"  [{spec['key']}] UNAVAILABLE ({type(e).__name__}: {e}); skipping.")
    if not models:
        sys.exit("No checkpoints could be loaded.")

    id_to_idx = {str(m["freesound_id"]): i for i, m in enumerate(metas)}

    def text_search(q: str):
        for key, model in models.items():
            te = l2(np.asarray(model.get_text_embedding([q], use_tensor=False), dtype=np.float32))
            scores = (audio_embs[key] @ te.T).ravel()
            print(f" -- {key} --")
            show(metas, scores)

    def hybrid(q: str):
        key = "general" if "general" in models else next(iter(models))
        model = models[key]
        te = l2(np.asarray(model.get_text_embedding([q], use_tensor=False), dtype=np.float32))
        clap = (audio_embs[key] @ te.T).ravel()
        qtokens = set(q.lower().split())
        tagscore = np.array([
            len(qtokens & {t.lower() for t in (m.get("tags") or [])}) for m in metas
        ], dtype=np.float32)
        tagscore = tagscore / (tagscore.max() or 1.0)
        blended = 0.7 * clap + 0.3 * tagscore
        print(f" -- hybrid (0.7*CLAP[{key}] + 0.3*tag) --")
        show(metas, blended)

    def similar(sid: str):
        if sid not in id_to_idx:
            print(f"  unknown id {sid}")
            return
        i = id_to_idx[sid]
        for key in models:
            scores = (audio_embs[key] @ audio_embs[key][i]).ravel()
            scores[i] = -1e9  # exclude self
            print(f" -- {key} (neighbors of {sid}) --")
            show(metas, scores)

    def all_queries() -> list[str]:
        return [l.strip() for l in QUERIES_FILE.read_text(encoding="utf-8").splitlines()
                if l.strip() and not l.startswith("#")]

    # Non-interactive batch report: `python scratch/retrieval_eval.py report`
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        import contextlib

        out = open(HERE / "eval_report.txt", "w", encoding="utf-8")

        class _Tee:
            def write(self, s):
                sys.__stdout__.write(s)
                out.write(s)

            def flush(self):
                sys.__stdout__.flush()
                out.flush()

        with contextlib.redirect_stdout(_Tee()):
            print(f"Checkpoints loaded: {', '.join(models)}")
            print(f"Eval clips: {len(metas)}\n")
            for q in all_queries():
                print(f"\n=== {q!r} ===")
                text_search(q)
        out.close()
        print(f"\nReport written to {HERE / 'eval_report.txt'}")
        return 0

    print("\nReady. Type a query, 'h <query>', 'sim <id>', 'play <id>', 'queries', or 'q'.")
    while True:
        try:
            line = input("\neval> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line == "q":
            break
        if line == "queries":
            for q in [l.strip() for l in QUERIES_FILE.read_text(encoding="utf-8").splitlines()
                      if l.strip() and not l.startswith("#")]:
                print(f"\n=== {q!r} ===")
                text_search(q)
            continue
        if line.startswith("play "):
            sid = line[5:].strip()
            f = CLIPS / f"{sid}.mp3"
            if f.exists() and hasattr(os, "startfile"):
                os.startfile(str(f))  # type: ignore[attr-defined]
            else:
                print(f"  {f} {'not found' if not f.exists() else 'cannot auto-play'}")
            continue
        if line.startswith("sim "):
            similar(line[4:].strip())
            continue
        if line.startswith("h "):
            hybrid(line[2:].strip())
            continue
        text_search(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
