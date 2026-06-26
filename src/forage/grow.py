"""The GROW loop: discover -> fetch ORIGINAL -> embed -> index, kept separate
from SEARCH. Dedups by Freesound id and by content hash, rate-limits, and is
resumable (already-grown sounds are skipped).
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from . import audio, config, embed, licensing
from .index import SqliteVecStore
from .library import sha256_file, write_sidecar
from .sources.freesound import FreesoundClient

RATE_SECONDS = 1.2
MAX_DURATION = 10.0  # keep clips short to avoid CLAP fusion mode
# Original formats soundfile/librosa can decode on this stack (skip m4a/wma early).
DECODABLE_EXTS = {".wav", ".flac", ".aiff", ".aif", ".ogg", ".mp3"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_unlink(p, progress) -> None:
    """Best-effort temp cleanup; a Windows file lock must not abort the loop."""
    try:
        p.unlink(missing_ok=True)
    except OSError:
        progress(f"  ! could not remove temp {p.name}")


def _meta_from_result(result: dict, file_hash: str, ext: str) -> dict:
    sid = str(result["id"])
    lic = licensing.parse_license(result.get("license"))
    return {
        "forage_id": f"freesound-{sid}",
        "source": "freesound",
        "source_id": sid,
        "file_hash": file_hash,
        "filename": f"freesound-{sid}{ext}",
        "title": result.get("name") or sid,
        "tags": result.get("tags", []),
        "attribution_username": result.get("username"),
        "attribution_url": result.get("url"),
        "duration_ms": None,
        "checkpoint_id": config.CLAP_CHECKPOINT,
        "embedding_dim": config.EMBEDDING_DIM,
        "added_at": _now(),
        **lic,
    }


def grow(query, count, store=None, client=None, license_filter=None, progress=lambda s: None):
    """Fetch up to `count` NEW originals matching `query`. Returns (kept, skipped)."""
    store = store or SqliteVecStore()
    client = client or FreesoundClient()
    if not client.has_oauth():
        from .sources.freesound import FreesoundAuthError

        raise FreesoundAuthError("Downloading originals needs OAuth2. Run `forage auth login` first.")

    # Over-fetch so dedup/license filtering still yields up to `count`.
    results = client.search(query, page_size=max(count * 3, count + 5), max_duration=MAX_DURATION)
    kept = skipped = 0
    for r in results:
        if kept >= count:
            break
        sid = str(r["id"])
        fid = f"freesound-{sid}"
        if store.get_vector(fid) is not None:  # resumable: already grown
            skipped += 1
            continue
        if license_filter and not license_filter(licensing.parse_license(r.get("license"))):
            skipped += 1
            continue

        ext = "." + (r.get("type") or "wav").lower()
        if ext not in DECODABLE_EXTS:  # skip undecodable originals before spending a download
            skipped += 1
            progress(f"  - {fid}: unsupported original format '{ext}', skipping")
            continue
        dest = config.samples_dir() / f"{fid}{ext}"
        # Keep the real extension on the temp file so soundfile/librosa can decode it.
        tmp = dest.with_name(f".tmp-{dest.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            client.download_original(sid, tmp)
            file_hash = sha256_file(tmp)
            if store.has_hash(file_hash):  # same bytes already present under another id
                _safe_unlink(tmp, progress)
                skipped += 1
                continue
            meta = _meta_from_result(r, file_hash, ext)
            wave = audio.load_audio(tmp)
            meta["duration_ms"] = audio.duration_ms(wave)
            vec = embed.embed_audio(wave)
            if not store.add(meta, vec):
                _safe_unlink(tmp, progress)
                skipped += 1
                continue
            tmp.replace(dest)  # atomic finalize only after the index row lands
            write_sidecar(meta)
            kept += 1
            progress(f"  + {fid:24} [{meta['license_name']}] {meta['title'][:40]}")
        except Exception as e:
            _safe_unlink(tmp, progress)
            skipped += 1
            progress(f"  ! {sid}: {e}")
        time.sleep(RATE_SECONDS)
    return kept, skipped


def doctor(store=None) -> dict:
    """Reconcile the library: report DB rows with missing audio, orphan sample
    files, and sidecars not in the index. Read-only (reports, does not delete)."""
    store = store or SqliteVecStore()
    rows = store.list_all()
    by_file = {m["filename"]: m for m in rows}
    samples = config.samples_dir()
    metadir = config.metadata_dir()

    missing_audio = [m["forage_id"] for m in rows
                     if not (samples / m["filename"]).exists()] if samples.exists() else []
    sample_files = {p.name for p in samples.glob("*")} if samples.exists() else set()
    orphan_files = sorted(sample_files - set(by_file.keys()))
    indexed_ids = {m["forage_id"] for m in rows}
    sidecar_ids = {p.stem for p in metadir.glob("*.json")} if metadir.exists() else set()
    sidecars_not_indexed = sorted(sidecar_ids - indexed_ids)

    return {
        "indexed": len(rows),
        "missing_audio": missing_audio,
        "orphan_files": orphan_files,
        "sidecars_not_indexed": sidecars_not_indexed,
    }
