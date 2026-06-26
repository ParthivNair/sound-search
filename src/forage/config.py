"""Resolved paths and pinned model config for Forage.

Importing this module asserts a supported Python version, because the system
default interpreter on the dev machine is 3.8.5 (EOL) and laion-clap/torch
require >=3.11. An accidental ``python script.py`` under 3.8 should fail loud.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # pragma: no cover - guard for wrong interpreter
    raise RuntimeError(
        f"Forage requires Python >=3.11 (got {sys.version.split()[0]}). "
        "Activate the dedicated environment first:  conda activate forage"
    )

# The CLAP checkpoint is PINNED here. Switching it invalidates every stored
# embedding (different checkpoint = different vector space), so changing this
# value requires a `forage reindex`. The general-vs-music choice is resolved
# empirically by the Phase 1 retrieval-quality eval before any persistent
# index is built; until then this is the general baseline.
CLAP_CHECKPOINT = "630k-audioset-best.pt"

# Measured by the Phase 0 smoke test on this machine (scratch/clap_smoke.py):
# laion_clap's joint audio/text space is 512-dim for the non-fusion 630k
# checkpoint. The index schema is created from this value. (~114 ms/clip on CPU.)
EMBEDDING_DIM: int = 512


def forage_home() -> Path:
    """Library root. User-visible by default so it can be added as a favorite
    folder in Cakewalk Next's browser (better drag ergonomics than %APPDATA%)."""
    override = os.environ.get("FORAGE_HOME")
    if override:
        return Path(override)
    return Path.home() / "Documents" / "Forage"


def samples_dir() -> Path:
    return forage_home() / "samples"


def metadata_dir() -> Path:
    return forage_home() / "metadata"


def db_path() -> Path:
    return forage_home() / "library.db"


def config_path() -> Path:
    return forage_home() / "config.json"


def oauth_path() -> Path:
    """Where the Freesound OAuth2 access/refresh tokens are cached (gitignored)."""
    return forage_home() / "oauth.json"


def _config_search_paths():
    # Canonical location first, then the repo root (dev convenience — where the
    # token was first dropped). Both are gitignored.
    yield config_path()
    yield Path(__file__).resolve().parents[2] / "config.json"


def load_config() -> dict:
    """Load config.json (freesound_token / freesound_client_id / _client_secret)."""
    for p in _config_search_paths():
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return {}
