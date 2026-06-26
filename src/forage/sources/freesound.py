"""Freesound API v2 client.

Two auth modes, by design:
  * SEARCH + previews use the token ("API key") — simple, never expires.
  * Downloading ORIGINAL files requires OAuth2 (Bearer). The token alone returns
    401 on the download endpoint, so grow needs a one-time `forage auth login`.

Uses `requests` (certifi CA bundle) — the stdlib ssl store on this Anaconda is
stale and rejects Freesound's Let's Encrypt chain.
"""

from __future__ import annotations

import json
import time
from urllib.parse import urlencode

import requests

from .. import config

API = "https://freesound.org/apiv2"
AUTHORIZE_URL = f"{API}/oauth2/authorize/"
TOKEN_URL = f"{API}/oauth2/access_token/"
RATE_SECONDS = 1.2  # polite: well under 60 req/min
SEARCH_FIELDS = "id,name,license,username,url,tags,previews,duration,samplerate,type"


class FreesoundAuthError(RuntimeError):
    pass


class FreesoundClient:
    def __init__(self, cfg: dict | None = None):
        cfg = config.load_config() if cfg is None else cfg
        self.token = (cfg.get("freesound_token") or "").strip()
        self.client_id = (cfg.get("freesound_client_id") or "").strip()
        self.client_secret = (cfg.get("freesound_client_secret") or "").strip()
        self._oauth = self._load_oauth()

    # ---- search (token auth) -------------------------------------------
    def search(self, query: str, page_size: int = 15, max_duration: float | None = None,
               extra_filter: str | None = None) -> list[dict]:
        if not self.token:
            raise FreesoundAuthError("No freesound_token in config.json (needed for search).")
        filters = []
        if max_duration:
            filters.append(f"duration:[0 TO {max_duration}]")
        if extra_filter:
            filters.append(extra_filter)
        params = {"query": query, "fields": SEARCH_FIELDS, "page_size": page_size, "sort": "score"}
        if filters:
            params["filter"] = " ".join(filters)
        return self._get(f"{API}/search/text/", params=params, token_auth=True).json().get("results", [])

    # ---- OAuth2 --------------------------------------------------------
    def authorize_url(self, state: str = "forage") -> str:
        if not self.client_id:
            raise FreesoundAuthError("No freesound_client_id in config.json.")
        return f"{AUTHORIZE_URL}?{urlencode({'client_id': self.client_id, 'response_type': 'code', 'state': state})}"

    def exchange_code(self, code: str) -> None:
        if not (self.client_id and self.client_secret):
            raise FreesoundAuthError("Need freesound_client_id and freesound_client_secret in config.json.")
        r = requests.post(TOKEN_URL, timeout=30, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": "authorization_code", "code": code.strip(),
        })
        if r.status_code != 200:
            raise FreesoundAuthError(f"Token exchange failed: HTTP {r.status_code} {r.text[:200]}")
        self._save_oauth(r.json())

    def _refresh(self) -> None:
        if not self._oauth.get("refresh_token"):
            raise FreesoundAuthError("No OAuth session. Run `forage auth login`.")
        r = requests.post(TOKEN_URL, timeout=30, data={
            "client_id": self.client_id, "client_secret": self.client_secret,
            "grant_type": "refresh_token", "refresh_token": self._oauth["refresh_token"],
        })
        if r.status_code != 200:
            raise FreesoundAuthError(f"Refresh failed: HTTP {r.status_code} {r.text[:200]}. Run `forage auth login`.")
        self._save_oauth(r.json())

    def has_oauth(self) -> bool:
        return bool(self._oauth.get("refresh_token"))

    def oauth_status(self) -> dict:
        if not self._oauth:
            return {"authorized": False}
        return {
            "authorized": True,
            "scope": self._oauth.get("scope"),
            "expires_in_s": int(self._oauth.get("expires_at", 0) - time.time()),
        }

    def _access_token(self) -> str:
        if not self._oauth:
            raise FreesoundAuthError("Not authorized for downloads. Run `forage auth login`.")
        if time.time() >= self._oauth.get("expires_at", 0) - 60:  # refresh slightly early
            self._refresh()
        return self._oauth["access_token"]

    def download_original(self, sound_id, dest_path) -> None:
        """Download the ORIGINAL file (OAuth2 Bearer) streaming to dest_path."""
        token = self._access_token()
        r = self._get(f"{API}/sounds/{sound_id}/download/", bearer=token, stream=True)
        with open(dest_path, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                if chunk:
                    fh.write(chunk)

    # ---- helpers -------------------------------------------------------
    def _get(self, url, params=None, token_auth=False, bearer=None, stream=False) -> requests.Response:
        headers = {}
        if bearer:
            headers["Authorization"] = f"Bearer {bearer}"
        elif token_auth:
            headers["Authorization"] = f"Token {self.token}"
        last = None
        for attempt in range(3):
            try:
                r = requests.get(url, params=params, headers=headers, timeout=60, stream=stream)
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r
            if r.status_code in (401, 403):
                raise FreesoundAuthError(f"HTTP {r.status_code} for {url}: {r.text[:160]}")
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", "5")))
                continue
            last = f"HTTP {r.status_code}: {r.text[:160]}"
            time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"GET failed after retries: {url} ({last})")

    def _load_oauth(self) -> dict:
        p = config.oauth_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_oauth(self, tok: dict) -> None:
        if not tok.get("access_token"):
            raise FreesoundAuthError(f"Token response missing access_token: {str(tok)[:160]}")
        rec = {
            "access_token": tok["access_token"],
            "refresh_token": tok.get("refresh_token") or self._oauth.get("refresh_token"),
            "expires_at": time.time() + int(tok.get("expires_in", 86400)),
            "scope": tok.get("scope"),
        }
        p = config.oauth_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        self._oauth = rec
