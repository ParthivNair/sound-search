"""OAuth2 client tests — no network (requests.post is monkeypatched)."""

from __future__ import annotations

import json
import time

import pytest


def _resp(payload, status=200):
    body = json.dumps(payload)  # precompute: a `json` method below would shadow the module

    class R:
        status_code = status
        text = body

        def json(self):
            return payload

    return R()


def test_authorize_url_and_missing_creds():
    from forage.sources.freesound import FreesoundAuthError, FreesoundClient

    c = FreesoundClient(cfg={"freesound_client_id": "abc"})
    url = c.authorize_url()
    assert "client_id=abc" in url and "response_type=code" in url

    bare = FreesoundClient(cfg={})
    with pytest.raises(FreesoundAuthError):
        bare.authorize_url()
    with pytest.raises(FreesoundAuthError):
        bare.search("anything")  # no token


def test_exchange_and_persist(monkeypatch, tmp_path):
    import forage.config as cfg
    from forage.sources import freesound

    monkeypatch.setattr(cfg, "oauth_path", lambda: tmp_path / "oauth.json")
    monkeypatch.setattr(freesound.requests, "post",
                        lambda *a, **k: _resp({"access_token": "AT", "refresh_token": "RT",
                                               "expires_in": 86400, "scope": "read write"}))
    c = freesound.FreesoundClient(cfg={"freesound_client_id": "id", "freesound_client_secret": "sec"})
    c.exchange_code("code123")
    assert (tmp_path / "oauth.json").exists()
    # a fresh client reloads the cached session
    c2 = freesound.FreesoundClient(cfg={"freesound_client_id": "id", "freesound_client_secret": "sec"})
    assert c2.has_oauth()
    assert c2.oauth_status()["authorized"] is True


def test_access_token_auto_refresh(monkeypatch, tmp_path):
    import forage.config as cfg
    from forage.sources import freesound

    monkeypatch.setattr(cfg, "oauth_path", lambda: tmp_path / "oauth.json")
    (tmp_path / "oauth.json").write_text(json.dumps({
        "access_token": "old", "refresh_token": "RT", "expires_at": time.time() - 10, "scope": "read",
    }), encoding="utf-8")

    calls = {"n": 0}

    def fake_post(*a, **k):
        calls["n"] += 1
        return _resp({"access_token": "NEW", "refresh_token": "RT2", "expires_in": 86400, "scope": "read"})

    monkeypatch.setattr(freesound.requests, "post", fake_post)
    c = freesound.FreesoundClient(cfg={"freesound_client_id": "id", "freesound_client_secret": "sec"})
    assert c._access_token() == "NEW"  # expired -> refreshed once
    assert calls["n"] == 1
