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
- **Phase 5** — desktop UI, auto-categorization, and Cakewalk instrument export

## Quick start

Requires **Python ≥3.11** — see [CONTRIBUTING.md](CONTRIBUTING.md) for the
Windows/Anaconda environment recipe (do **not** use the system Python 3.8).

```bat
conda activate forage
pip install -e .
forage config show
python scratch\clap_smoke.py
```

## Finding sounds (categories, UI, browse folders)

Freesound files are named `freesound-<id>.<ext>`, which is useless for browsing. Fix
that with a one-time categorize, then use whichever surface you like:

```bat
forage categorize                 :: tag every sound kick/snare/hat/bass/synth/vocal/fx + one-shot vs loop
forage list --tags kick           :: filter from the CLI
forage ui                         :: desktop app: search, audition, filter by category, drag onto a track
forage browse                     :: build a Documents\Forage\browse\<Category>\ tree (favorite it in Cakewalk's Media Browser)
```

`forage ui` needs the optional GUI dependency: `pip install -e ".[gui]"` (PySide6).
The app lets you audition, filter, and **drag a sample straight onto a Cakewalk
track**; if your host rejects the drop, use the **Reveal in Explorer** button and
drag from there.

## Instruments — play one-shots as MIDI notes

Rather than dropping a single hi-hat onto its own audio track, export a kit and play
it from **one instrument track**:

```bat
forage export-sfz --drum-map --name my-kit     :: drums mapped to General-MIDI keys
forage export-sfz --category kick --category snare
forage export-sfz                              :: all one-shots, chromatic from MIDI 36
```

This writes `Documents\Forage\instruments\<name>.sfz` (absolute paths to your WAVs).
To play it in **Cakewalk Next**:

- **Recommended** — install the free [sforzando](https://www.plogue.com/products/sforzando.html)
  (VST3) SFZ player, add it on an instrument track, and drag/load the `.sfz` onto it.
  Each sound triggers on its own MIDI note.
- **No install** — Cakewalk Next's built-in **XSampler** (one sound, set the root note)
  or **Pad Controller** (up to 16 sounds, one per pad) also play WAVs from MIDI; drag
  the WAVs in from `Documents\Forage\browse\…`.

## Licensing

Forage fetches Creative Commons material and **retains each sound's license and
attribution**. You are responsible for honoring those terms (e.g. crediting
CC-BY sounds) in anything you release; `forage credits` produces a manifest to
help. Forage is local-first and never redistributes the audio it fetches.
