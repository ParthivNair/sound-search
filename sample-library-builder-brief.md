# Personal Sample-Library Builder — Project Brief

*Working name: **Forage** (placeholder — rename freely)*

> This brief is self-contained. It assumes no prior context. Read "The core insight" and "What it is NOT" first — they're what keep the idea from collapsing into yet another sample browser.

## Concept (one line)

A **local-first** tool that **builds and grows a personal sample library** by harvesting legitimately-free sounds from the open web, auto-organizing them with **natural-language semantic search**, and feeding them into a DAW — so the producer stops manually finding, downloading, auditioning, and tagging sounds one at a time.

## The core insight (this is the whole point)

This is **not** a sample browser and **not** a cloud catalog.

- Organizing sounds you already own is a solved problem (e.g. Sononym, Algonaut Atlas — local ML similarity browsers).
- Renting access to someone else's hosted catalog is a solved problem (e.g. Loopcloud, Splice — cloud, subscription, huge libraries).

The unclaimed space is **assembling a personal, taste-targeted library out of what's freely available online, and growing it on demand.** The library is the *output*, not the input. The download → audition → tag → organize grind a producer otherwise does by hand **is** the software.

Keep two loops conceptually separate in the architecture:

1. **Grow the library** — discover + fetch new material from external free sources. This is where new sounds *enter*.
2. **Search the library** — natural-language and similarity search over what's been collected. This runs *locally* over the library being built.

This separation also resolves the obvious scaling worry: you never index "all of Freesound." You only embed what you actually fetch into your own library. Discovery uses the source's own search; semantic search runs over your local collection.

## What it is NOT (explicit non-goals — protect scope)

- **Not** a hosted catalog. No proprietary sound storage in the cloud, no server.
- **Not** competing on size. Curation beats volume. The value is *your* palette, not a million strangers' loops.
- **Not** an open-web scraper that vacuums up `"[producer] sample pack free download"` results. Sourcing is restricted to vetted-free / CC material (see Sourcing Policy). This is the integrity of the entire project — skip it and the tool becomes automated piracy with a nice UI, plus it has no defensibility since anyone can scrape.
- **Not** a VST3/AU plugin for v1. A Loopcloud-style in-DAW plugin with drag-to-timeline is the single hardest, most fragile piece — OS-level drag-out from a plugin window is host-specific and brittle, and it's what Loopcloud spent years getting right. v1 integrates via **folder + drag**. Revisit a plugin only after the core loop ships and proves useful.

## How it works (pipeline)

1. **Sources** — a registry of legitimately-free origins:
   - **Freesound** — CC-licensed, has a clean public API with per-sound license metadata.
   - A **curated allowlist** (v2) of producers'/labels' *own* free releases and free-pack sites with explicit licensing.
2. **Discover + fetch** — query sources (Freesound's API for their side; the curated registry for the rest), download candidates, and **retain license + attribution metadata with every file.**
3. **Embed + organize** — embed each fetched sound locally with **CLAP** (audio → vector), store in a local vector index, auto-tag/categorize (one-shot vs loop, brightness, etc.). This layer is commodity — assemble existing libraries, don't reinvent.
4. **Search the library** — natural-language query (e.g. *"warm dusty rhodes chord, short tail"*) → CLAP text embedding → nearest sounds from *your* library. Plus audio → audio "find similar." When nothing in the library matches a query, that's the signal to go fetch (loop 1).
5. **Use in DAW** — organized files sit on disk; drag into Cakewalk from the file manager / Cakewalk's browser. No plugin required.

## Sourcing policy (the legal spine)

- **v1 source:** Freesound (CC) only.
- **v2 sources:** a hand-curated registry of artists/sites that release authorized free material in the target styles.
- Every sound stores its **license + attribution**; surface this so the user can honor terms (some CC licenses require credit).
- Producer-specific free packs get added to the registry **manually / vetted** — never auto-discovered. Programmatically deciding "is this free pack actually licensed?" across the open web is unsolved, and it's exactly the line between a clean tool and a liability.
- Commercial packs (Splice/store content) pulled from file hosts, forums, or "leak" links are **out, full stop.**

## Tech building blocks (all commodity — assemble, don't invent)

- **CLAP** — LAION `laion_clap` (pip-installable, in HuggingFace Transformers, music-specific checkpoints available, runs on CPU) for joint audio + text embeddings. Reference: the open-source `llm-clap` already does "embed a folder of wavs, then search them by text" — close to the core retrieval primitive.
- **Freesound API** — free API key; text/tag search; per-sound license metadata; downloads.
- **Vector index** — start simple: SQLite + a vector extension (e.g. sqlite-vec), or FAISS/NumPy at small scale. No cloud DB.
- **Stack** — Python is the path of least resistance for the ML + API glue. Thin UI: **CLI first**, then a small local web or desktop UI.
- **Local-first** — everything on the user's machine.

## Cakewalk Next integration

- **v1 (easy, robust, do this):** the tool maintains the organized library folder; the user drags audio files from the file manager (or Cakewalk's browser) into the project. DAW-agnostic and works today. (Cakewalk Next imports audio and loads third-party VSTs.)
- **Later (hard, optional):** a VST3/AU bridge with in-plugin search and drag-to-timeline. Treat as a separate, much larger effort — not part of the core idea.

## Known design tradeoff (intentional, not a bug)

Seeding the library from "producers I love + adjacent free material" **deepens the sound you're already chasing.** It gives you your palette on tap; it will *not* surprise you with a direction you didn't know you wanted. That's the design intent — a personal palette engine — and it's worth stating so it stays a deliberate choice rather than an accidental limitation.

## Suggested v1 (ruthlessly small — ship this, then extend)

Prove the **full loop** end-to-end with the smallest possible slice. One source, no registry, no UI polish, no plugin.

- **Source:** Freesound only.
- **Grow:** keyword/natural-language query → Freesound API search → fetch top candidates → embed locally with CLAP → add to a local library folder + index, with license metadata.
- **Search (the differentiator — include it in v1):** query the *local* library semantically with CLAP (text → audio) and by similarity (audio → audio).
- **Use:** drag from the library folder into Cakewalk.

If that loop works and *feels good in a real session*, then add: the curated producer-pack registry, a real UI, automatic gap-querying, richer tagging, dedup, and (much later) a plugin. Resist building any of that before the v1 loop is finished and used.

## Open decisions for the dev session

- Vector store at expected library scale (sqlite-vec vs FAISS).
- CLAP checkpoint choice (general vs music-specific) — test retrieval quality on the actual kind of material before committing.
- v1 UI surface (CLI vs minimal local web app).
- Library on-disk layout + metadata schema (how license/attribution/tags travel with each file).
- (v2) representation of the curated source registry — likely a simple YAML/JSON list of vetted URLs + license per entry.
