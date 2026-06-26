# Forage

A **local-first** tool that *builds and grows a personal sample library* by
harvesting legitimately-free CC sounds from Freesound, organizing them with
**natural-language semantic search** (via [CLAP](https://github.com/LAION-AI/CLAP)
audio↔text embeddings), and feeding them into a DAW (Cakewalk Next) by
**folder + drag**.

Two loops, kept separate by design:

1. **Grow** — discover + fetch new CC material from Freesound (where sounds *enter*).
2. **Search** — natural-language and similarity search over *your* local library.

You only ever embed what you actually fetch — never "all of Freesound." Every
sound keeps its **license + attribution**, and obligations are surfaced when you
assemble a project so you can credit correctly.

See `sample-library-builder-brief.md` for the full concept and the approved build
plan for the phased roadmap.

## Status

Early development. Building toward v1 in phases, each individually testable:

- **Phase 0** — environment + CLAP smoke test *(in progress)*
- **Phase 1** — prove retrieval quality on real audio (GO/RETHINK gate)
- **Phase 2** — persistent library + `sqlite-vec` index + `forage search`
- **Phase 3** — the compliant `forage grow` loop
- **Phase 4** — per-project credits/obligations + robustness

## Quick start

Requires **Python ≥3.11** — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
Windows/Anaconda environment recipe (do **not** use the system Python 3.8).

```bat
conda activate forage
pip install -e .
forage config show
python scratch\clap_smoke.py
```

## Licensing

Forage fetches Creative Commons material and **retains each sound's license and
attribution**. You are responsible for honoring those terms (e.g. crediting
CC-BY sounds) in anything you release; `forage credits` produces a manifest to
help. Forage is local-first and never redistributes the audio it fetches.
