"""Auto-categorization via CLAP zero-shot.

We embed a curated taxonomy of category prompts once with `embed_text`, then for each
sound compare its already-stored embedding (no re-embed) to every prompt by cosine,
assigning the nearest category. A cheap exact-token keyword match on tags/title wins
when present (it's high-precision); otherwise CLAP decides, falling back to
"uncategorized" when even the best match is weak. Each sound also gets `is_oneshot`
from its duration.

Results are written to both the DB (in place) and the canonical sidecar, so a later
`forage reindex` carries them through.
"""

from __future__ import annotations

from collections import Counter

import numpy as np

from . import config, library

# (category, CLAP prompt). Natural phrases work best with the general 630k checkpoint.
TAXONOMY = [
    ("kick",        "a kick drum, deep punchy bass drum hit"),
    ("snare",       "a snare drum hit"),
    ("clap",        "a hand clap percussion hit"),
    ("closed-hat",  "a closed hi-hat drum, short tick"),
    ("open-hat",    "an open hi-hat cymbal, sizzling"),
    ("tom",         "a tom drum hit"),
    ("cymbal",      "a crash or ride cymbal"),
    ("percussion",  "a percussion hit, shaker, conga or tambourine"),
    ("bass",        "a deep bass instrument note"),
    ("synth-keys",  "a synthesizer keyboard, piano or electric piano chord"),
    ("pad",         "a soft sustained synth pad or ambient texture"),
    ("lead",        "a bright synth lead or melodic pluck"),
    ("guitar",      "an electric or acoustic guitar"),
    ("vocal",       "a human voice singing or speaking"),
    ("fx-riser",    "a rising sweep or uplifter sound effect"),
    ("fx-impact",   "a cinematic impact, boom or hit"),
    ("fx-noise",    "a white noise sweep or static texture"),
    ("fx-ambience", "a background ambience or field recording"),
]
CATEGORY_NAMES = [c for c, _ in TAXONOMY]

# Exact-token (lowercased) override: a confident name beats a fuzzy embedding match.
KEYWORD_MAP = {
    "kick": "kick", "bd": "kick", "bassdrum": "kick",
    "snare": "snare", "sd": "snare", "rimshot": "snare", "rim": "snare",
    "clap": "clap", "snap": "clap",
    "hihat": "closed-hat", "hat": "closed-hat", "hh": "closed-hat", "closedhat": "closed-hat",
    "openhat": "open-hat", "ohh": "open-hat",
    "tom": "tom",
    "crash": "cymbal", "ride": "cymbal", "cymbal": "cymbal",
    "perc": "percussion", "shaker": "percussion", "conga": "percussion",
    "bongo": "percussion", "tambourine": "percussion",
    "bass": "bass", "808": "bass", "sub": "bass",
    "pad": "pad",
    "lead": "lead", "pluck": "lead",
    "guitar": "guitar",
    "vocal": "vocal", "vox": "vocal", "voice": "vocal",
    "riser": "fx-riser", "uplifter": "fx-riser", "sweep": "fx-riser",
    "impact": "fx-impact", "boom": "fx-impact", "hit": "fx-impact",
    "noise": "fx-noise", "static": "fx-noise",
    "ambience": "fx-ambience", "ambient": "fx-ambience", "field": "fx-ambience",
}


def _tokens(text: str) -> list[str]:
    out, cur = [], []
    for ch in (text or "").lower():
        if ch.isalnum():
            cur.append(ch)
        elif cur:
            out.append("".join(cur)); cur = []
    if cur:
        out.append("".join(cur))
    return out


# "bass"/"synth-keys" are broad low-end/tonal buckets that loose Freesound tags
# over-trigger; a specific hit (kick/snare/hat/...) anywhere should win over them.
_GENERIC = {"bass", "synth-keys"}


def keyword_category(meta: dict) -> str | None:
    """Exact-token match over title + tags. A specific category beats a generic
    (bass/synth-keys) one, so 'Electronic Kick Drum' tagged 'bass' resolves to kick."""
    hits = []
    for tok in _tokens(meta.get("title") or ""):
        if tok in KEYWORD_MAP:
            hits.append(KEYWORD_MAP[tok])
    for tag in (meta.get("tags") or []):
        for tok in _tokens(tag):
            if tok in KEYWORD_MAP:
                hits.append(KEYWORD_MAP[tok])
    if not hits:
        return None
    for h in hits:
        if h not in _GENERIC:
            return h
    return hits[0]


def build_label_vectors(embed_text_fn) -> tuple[list[str], np.ndarray]:
    """Embed every taxonomy prompt -> (names, M x D L2-normalized matrix)."""
    vecs = [np.asarray(embed_text_fn(prompt), dtype=np.float32).ravel() for _, prompt in TAXONOMY]
    mat = np.vstack(vecs)
    mat = mat / (np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9)
    return CATEGORY_NAMES, mat


def classify_one(vec, label_mat, names, meta, threshold) -> tuple[str, float]:
    """Keyword override > CLAP argmax > 'uncategorized' (when below threshold)."""
    kw = keyword_category(meta)
    if kw:
        return kw, 1.0
    q = np.asarray(vec, dtype=np.float32).ravel()
    q = q / (np.linalg.norm(q) + 1e-9)
    sims = label_mat @ q
    j = int(sims.argmax())
    return (names[j], float(sims[j])) if sims[j] >= threshold else ("uncategorized", float(sims[j]))


def categorize(store, embed_text_fn, recompute=False, threshold=0.0, progress=lambda s: None) -> dict:
    """Assign category + is_oneshot to every sound. Returns a {category: count} dict."""
    rows = store.list_all()
    todo = [m for m in rows if recompute or not m.get("category")]
    progress(f"Categorizing {len(todo)} of {len(rows)} sound(s)...")
    progress("Loading CLAP to embed category prompts (first run is slow)...")
    names, label_mat = build_label_vectors(embed_text_fn)

    counts: Counter = Counter()
    for i, m in enumerate(todo, 1):
        fid = m["forage_id"]
        vec = store.get_vector(fid)
        if vec is None:
            continue
        category, _score = classify_one(vec, label_mat, names, m, threshold)
        dur = m.get("duration_ms")
        is_oneshot = dur is not None and dur < config.ONESHOT_MS

        store.set_fields(fid, category=category, is_oneshot=is_oneshot)
        # Keep the canonical sidecar in sync (prefer the on-disk sidecar; fall back to
        # the DB meta if it's unreadable) so a later reindex carries the fields through.
        side, _problems = library.load_sidecar(config.metadata_dir() / f"{fid}.json")
        side = side if isinstance(side, dict) else dict(m)
        side["category"] = category
        side["is_oneshot"] = is_oneshot
        library.write_sidecar(side)

        counts[category] += 1
        if i % 25 == 0 or i == len(todo):
            progress(f"  {i}/{len(todo)}")
    return dict(counts)
