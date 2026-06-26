"""On-disk library: per-file sidecars (source of truth), content-hash dedup, and
import of audio into the library + index.

Layout under FORAGE_HOME:
    samples/<forage_id>.<ext>     audio (flat, Cakewalk-draggable)
    metadata/<forage_id>.json     canonical sidecar (license + obligations + tags)
    library.db                    sqlite-vec index (derived, rebuildable)
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import audio, config, embed
from .index import SqliteVecStore

AUDIO_EXTS = {".wav", ".flac", ".aif", ".aiff", ".mp3", ".ogg"}


def sha256_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize(name: str) -> str:
    bad = '<>:"/\\|?*'
    return "".join("_" if c in bad else c for c in name).strip() or "untitled"


def _read_eval_sidecar(audio_path: Path) -> dict | None:
    """Phase 1 eval clips carry a sibling <id>.json with Freesound metadata."""
    j = audio_path.with_suffix(".json")
    if j.exists():
        try:
            return json.loads(j.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def build_meta(path: Path, file_hash: str) -> dict:
    base = {
        "file_hash": file_hash,
        "checkpoint_id": config.CLAP_CHECKPOINT,
        "embedding_dim": config.EMBEDDING_DIM,
        "added_at": _now(),
        "tags": [],
    }
    ev = _read_eval_sidecar(path)
    if ev and ev.get("freesound_id"):
        sid = str(ev["freesound_id"])
        base.update(
            forage_id=f"freesound-{sid}",
            source="freesound",
            source_id=sid,
            title=ev.get("title") or path.stem,
            tags=ev.get("tags", []),
            license_name=ev.get("license_name", "Unknown"),
            license_url=ev.get("license_url"),
            attribution_username=ev.get("attribution_username"),
            attribution_url=ev.get("attribution_url"),
            requires_attribution=bool(ev.get("requires_attribution")),
            non_commercial=bool(ev.get("non_commercial")),
            share_alike=bool(ev.get("share_alike")),
            no_derivatives=bool(ev.get("no_derivatives")),
        )
        return base
    # Generic local audio: no source license metadata available.
    base.update(
        forage_id=f"local-{file_hash[:12]}",
        source="local",
        source_id=None,
        title=sanitize(path.stem),
        license_name="Unknown",
        license_url=None,
        attribution_username=None,
        attribution_url=None,
        requires_attribution=False,
        non_commercial=False,
        share_alike=False,
        no_derivatives=False,
    )
    return base


def write_sidecar(meta: dict) -> None:
    config.metadata_dir().mkdir(parents=True, exist_ok=True)
    (config.metadata_dir() / f"{meta['forage_id']}.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )


def import_folder(folder, store: SqliteVecStore | None = None, progress=lambda s: None):
    """Import every audio file under `folder` into the library + index.
    Dedups by content hash. Returns (added, skipped)."""
    folder = Path(folder)
    store = store or SqliteVecStore()
    files = [p for p in sorted(folder.rglob("*")) if p.suffix.lower() in AUDIO_EXTS]
    added = skipped = 0
    for p in files:
        try:
            file_hash = sha256_file(p)
            if store.has_hash(file_hash):
                skipped += 1
                continue
            meta = build_meta(p, file_hash)
            wave = audio.load_audio(p)
            meta["duration_ms"] = audio.duration_ms(wave)
            vec = embed.embed_audio(wave)

            dest = config.samples_dir() / f"{meta['forage_id']}{p.suffix.lower()}"
            meta["filename"] = dest.name

            # Index insert FIRST (and idempotent); only on success do we copy the
            # audio and write the sidecar, so a duplicate or failure never orphans
            # a file in samples/.
            if not store.add(meta, vec):
                skipped += 1
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
            write_sidecar(meta)
            added += 1
            progress(f"  + {meta['forage_id']:24} [{meta['license_name']}] {meta['title'][:40]}")
        except Exception as e:  # one unreadable/bad file must not abort the batch
            skipped += 1
            progress(f"  ! {p.name}: {e}")
    return added, skipped
