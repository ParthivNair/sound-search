# Forage — at a glance

## What it is

**Forage** is a local-first tool that *builds and grows a personal sample library* out of
legitimately-free sounds on the open web, auto-organizes them with **natural-language semantic
search**, and feeds them into a DAW. The twist: the library is the **output**, not the input —
instead of browsing sounds you already own (Sononym) or renting a cloud catalog (Splice/Loopcloud),
Forage automates the *download → audition → tag → organize* grind a producer does by hand, assembling
a taste-targeted palette on demand. You type *"warm dusty rhodes chord, short tail"*; if nothing in
your library matches, that's the signal to go fetch more.

## How it works

- **Two deliberately separate loops** (the core architectural decision)
  - **Grow** — where new sounds *enter* the system
    - Queries an external free source (v1: **Freesound**, CC-licensed) using *its* search, so you
      never index "all of Freesound" — only what you actually pull
    - **Split auth model**: API token for search/previews; **OAuth2 (Bearer)** required to download
      originals
    - Downloads full-quality originals, captures **license + attribution + obligation flags**
      (attribution / non-commercial / share-alike / no-derivatives) per file
    - Idempotent + resumable: dedups by source-id and content hash, rate-limited, atomic temp→final
      writes
  - **Search** — runs *locally* over what's been collected
    - **CLAP** embeds audio and text into one shared 512-dim vector space (so text and audio are
      directly comparable)
    - Supports **text → audio** ("find me X") and **audio → audio** ("find similar to this")
    - Nearest-neighbor lookup via **sqlite-vec** (L2-normalized vectors ⇒ L2-KNN == cosine)
- **Data model: source-of-truth + derived index**
  - Per-file **JSON sidecar** is canonical (license, attribution, tags, obligations)
  - The SQLite/sqlite-vec database is a *rebuildable* index — blow it away and `reindex` from sidecars
  - Obligations travel with every sound and surface **at use time** (inline in search results, and a
    per-project credits manifest)
- **Stack & posture**
  - Python + Typer CLI; `laion_clap` (CPU), `sqlite-vec`, `requests`; **everything on-device, no server**
- **DAW integration**
  - v1 is just **folder + drag** — the organized library is a normal folder you drag into Cakewalk
    Next; *no plugin* (the brittle, host-specific part is deliberately deferred)
- **Why it's defensible (the design intent)**
  - **Curation over volume** — your palette, not a million strangers' loops
  - **Legal integrity as the spine** — CC/vetted-free only, never an open-web scraper; that's the line
    between a clean tool and automated piracy

## One-line framing for an architect

It's essentially an **ETL pipeline with a semantic index** — *extract* (Freesound API), *transform*
(decode → CLAP embed → license-normalize), *load* (sidecar + vector index) — where the query layer is a
**cross-modal embedding space** rather than SQL predicates, and the whole thing is single-tenant and
offline by design.
