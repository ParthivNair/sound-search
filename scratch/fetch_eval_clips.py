"""Phase 1 throwaway eval fetch.

Pulls a handful of real Freesound clips per seed term into scratch/clips/ so we
can judge CLAP retrieval quality on REAL material BEFORE building anything
persistent. Throwaway in every respect EXCEPT two non-negotiables (per the plan
+ the critique): it captures full license + attribution (obligation flags) for
every clip, and it rate-limits politely.

Auth: token-only (Freesound "API key"). It downloads PREVIEWS (hq mp3), which
token auth can access. Downloading ORIGINAL files requires Freesound OAuth2 and
is deferred to the real Phase 3 grow loop — previews are perfect for a retrieval
A/B and avoid the heavier auth + download quota.

Usage (inside the `forage` conda env):
    set FREESOUND_TOKEN=...        # or put it in config.json (see get_token)
    python scratch/fetch_eval_clips.py check        # verify the token with 1 search
    python scratch/fetch_eval_clips.py              # fetch the full eval set
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests  # uses certifi's current CA bundle (stdlib urllib uses Anaconda's stale store)

API = "https://freesound.org/apiv2"
HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
TERMS_FILE = HERE / "eval_fetch_terms.txt"
PER_TERM = int(os.environ.get("PER_TERM", "6"))
MAX_DURATION = 10.0
RATE_SECONDS = 1.2  # comfortably under Freesound's 60 req/min


def get_token() -> str:
    tok = os.environ.get("FREESOUND_TOKEN", "").strip()
    if tok:
        return tok
    # Fall back to config.json {"freesound_token": "..."} in either the library
    # root (FORAGE_HOME) or the repo root (where the user dropped it).
    home = os.environ.get("FORAGE_HOME") or str(Path.home() / "Documents" / "Forage")
    for cfg in (Path(home) / "config.json", HERE.parent / "config.json"):
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
                if data.get("freesound_token"):
                    return str(data["freesound_token"]).strip()
            except Exception:
                pass
    # Last resort: a plain scratch/.freesound_token file.
    local = HERE / ".freesound_token"
    if local.exists():
        return local.read_text(encoding="utf-8").strip()
    sys.exit(
        "No Freesound token found. Set FREESOUND_TOKEN, or add "
        '{"freesound_token": "..."} to %USERPROFILE%\\Documents\\Forage\\config.json, '
        "or write the token to scratch/.freesound_token"
    )


def parse_license(url: str | None) -> dict:
    """Map a Freesound license URL to a name + obligation flags. Order matters:
    most-specific variants are checked first."""
    u = (url or "").lower()
    f = {
        "license_url": url,
        "requires_attribution": False,
        "non_commercial": False,
        "share_alike": False,
        "no_derivatives": False,
    }
    if "publicdomain/zero" in u or "/cc0" in u:
        name = "CC0"
    elif "by-nc-sa" in u:
        name = "CC-BY-NC-SA"; f.update(requires_attribution=True, non_commercial=True, share_alike=True)
    elif "by-nc-nd" in u:
        name = "CC-BY-NC-ND"; f.update(requires_attribution=True, non_commercial=True, no_derivatives=True)
    elif "by-nc" in u:
        name = "CC-BY-NC"; f.update(requires_attribution=True, non_commercial=True)
    elif "by-sa" in u:
        name = "CC-BY-SA"; f.update(requires_attribution=True, share_alike=True)
    elif "by-nd" in u:
        name = "CC-BY-ND"; f.update(requires_attribution=True, no_derivatives=True)
    elif "/by/" in u or u.rstrip("/").endswith("/by"):
        name = "CC-BY"; f.update(requires_attribution=True)
    elif "sampling+" in u or "samplingplus" in u:
        name = "Sampling+"; f.update(requires_attribution=True)
    else:
        name = "Unknown"
    f["license_name"] = name
    return f


def _get(url: str, token: str, params: dict | None = None) -> requests.Response:
    last = None
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30,
                             headers={"Authorization": f"Token {token}"})
        except requests.RequestException as e:
            last = e
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 200:
            return r
        if r.status_code == 401:
            sys.exit("HTTP 401 — Freesound token is invalid or not yet active.")
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "5"))
            print(f"  rate-limited (429); waiting {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 404:
            r.raise_for_status()
        last = f"HTTP {r.status_code}"
        print(f"  {last} on {url} (attempt {attempt+1})")
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"failed after retries: {url} ({last})")


def search(term: str, token: str) -> list[dict]:
    params = {
        "query": term,
        "filter": f"duration:[0 TO {MAX_DURATION}]",
        "fields": "id,name,license,username,url,tags,previews,duration,samplerate",
        "page_size": PER_TERM,
        "sort": "score",
    }
    return _get(f"{API}/search/text/", token, params=params).json().get("results", [])


def fetch_clip(result: dict, term: str, token: str) -> dict | None:
    sid = result["id"]
    previews = result.get("previews") or {}
    preview_url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")
    if not preview_url:
        return None
    out_audio = CLIPS / f"{sid}.mp3"
    if not out_audio.exists():
        out_audio.write_bytes(_get(preview_url, token).content)
        time.sleep(RATE_SECONDS)
    lic = parse_license(result.get("license"))
    meta = {
        "freesound_id": sid,
        "seed_term": term,
        "title": result.get("name"),
        "tags": result.get("tags", []),
        "attribution_username": result.get("username"),
        "attribution_url": result.get("url"),
        "duration_ms": int(round(float(result.get("duration", 0)) * 1000)),
        "samplerate": result.get("samplerate"),
        "preview_url": preview_url,
        **lic,
    }
    (CLIPS / f"{sid}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def main() -> int:
    token = get_token()
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        res = search("kick drum", token)
        print(f"Token OK. 'kick drum' returned {len(res)} results.")
        if res:
            m = parse_license(res[0].get("license"))
            print(f"  e.g. id={res[0]['id']} '{res[0].get('name')}' "
                  f"license={m['license_name']} attr={m['requires_attribution']}")
        return 0

    CLIPS.mkdir(parents=True, exist_ok=True)
    terms = [
        ln.strip() for ln in TERMS_FILE.read_text(encoding="utf-8").splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    print(f"Fetching up to {PER_TERM} clips for each of {len(terms)} terms -> {CLIPS}")
    counts: dict[str, int] = {}
    total = 0
    for term in terms:
        try:
            results = search(term, token)
        except Exception as e:
            print(f"  [{term}] search failed: {e}")
            time.sleep(RATE_SECONDS)
            continue
        kept = 0
        for r in results:
            try:
                meta = fetch_clip(r, term, token)
            except Exception as e:
                print(f"    id={r.get('id')} fetch failed: {e}")
                continue
            if meta:
                kept += 1
                total += 1
                counts[meta["license_name"]] = counts.get(meta["license_name"], 0) + 1
        print(f"  [{term}] kept {kept}")
        time.sleep(RATE_SECONDS)

    print(f"\nDone. {total} clips in {CLIPS}")
    print("License breakdown:")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {name:14} {n}")
    print("\nNext: python scratch/retrieval_eval.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
