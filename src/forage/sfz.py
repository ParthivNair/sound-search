"""Export one-shots as an SFZ instrument so a whole kit plays from one MIDI track.

The emitted `.sfz` is plain text that points at the canonical sample files by
absolute path (forward slashes — sforzando accepts them on Windows), one `<region>`
per sound, each a single-key one-shot. Load it in a free SFZ player (sforzando VST3)
on an instrument track in Cakewalk Next, or fall back to the bundled XSampler / Pad
Controller. No CLAP needed — this is pure metadata.
"""

from __future__ import annotations

from pathlib import Path

from . import config
from .library import sanitize

# Preferred General-MIDI percussion keys per category (extra keys absorb collisions).
DRUM_MAP = {
    "kick": [36, 35],
    "snare": [38, 40, 37],
    "clap": [39],
    "closed-hat": [42, 44],
    "open-hat": [46],
    "tom": [45, 47, 48, 41, 43, 50],
    "cymbal": [49, 51, 57, 59, 55, 52, 53],
    "percussion": [69, 70, 75, 76, 77, 56, 54, 67, 68],
}

MAX_KEY = 127


def _next_free(used: set[int], start: int) -> int | None:
    k = start
    while k in used:
        k += 1
    return k if k <= MAX_KEY else None


def assign_keys(metas: list[dict], layout: str = "chromatic", start_key: int = 36) -> list[tuple[dict, int]]:
    """Pair each meta with a MIDI key. drum-map uses GM keys by category (next free on
    collision); chromatic ascends from start_key. Sounds that can't get a key (>127)
    are dropped."""
    used: set[int] = set()
    pairs: list[tuple[dict, int]] = []
    if layout == "drum-map":
        for m in metas:
            key = None
            for cand in DRUM_MAP.get(m.get("category") or "", []):
                if cand not in used:
                    key = cand
                    break
            if key is None:
                key = _next_free(used, start_key)
            if key is None:
                break  # ran out of keys
            used.add(key)
            pairs.append((m, key))
    else:  # chromatic
        k = start_key
        for m in metas:
            if k > MAX_KEY:
                break
            pairs.append((m, k))
            used.add(k)
            k += 1
    return pairs


def build_sfz(metas: list[dict], layout: str = "chromatic", name: str = "forage-kit",
              samples_dir=None, start_key: int = 36) -> str:
    """Pure: render the SFZ text for already-selected metas."""
    sd = Path(samples_dir) if samples_dir is not None else config.samples_dir()
    pairs = sorted(assign_keys(metas, layout, start_key), key=lambda p: p[1])
    out = [f"// Forage SFZ export: {name}",
           f"// {len(pairs)} region(s), {layout} layout. Sample paths are absolute.", ""]
    for m, key in pairs:
        path = (sd / m["filename"]).resolve().as_posix()
        out += ["<region>",
                f"sample={path}",
                f"key={key}",
                f"pitch_keycenter={key}",
                "loop_mode=one_shot",
                ""]
    return "\n".join(out)


def write_sfz(metas: list[dict], name: str = "forage-kit", layout: str = "chromatic") -> Path:
    """Render and write `<FORAGE_HOME>/instruments/<name>.sfz`; returns the path."""
    out = config.forage_home() / "instruments" / f"{sanitize(name)}.sfz"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_sfz(metas, layout=layout, name=name), encoding="utf-8")
    return out
