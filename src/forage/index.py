"""Vector index for Forage.

`VectorStore` is the abstraction (so FAISS/NumPy stay a cheap swap); `SqliteVecStore`
is the v1 implementation backed by sqlite-vec — vectors + metadata in one ACID file.

Vectors are L2-normalized before storage, so KNN by L2 distance is equivalent to
KNN by cosine similarity; we report cosine (1 - L2^2/2) for readability.

The raw float32 vector is also stored as a BLOB in the `sounds` table so a sound's
own vector can be fetched cheaply (for audio->audio `similar`) and the index stays
rebuildable.
"""

from __future__ import annotations

import json
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import config

# Metadata columns stored alongside each vector (also the sidecar field set).
_BOOL_FIELDS = ("requires_attribution", "non_commercial", "share_alike", "no_derivatives")
_COLUMNS = (
    "forage_id", "source", "source_id", "file_hash", "filename", "title",
    "license_name", "license_url", "attribution_username", "attribution_url",
    *_BOOL_FIELDS, "tags", "duration_ms", "checkpoint_id", "embedding_dim", "added_at",
    "category", "is_oneshot",
)
# Persisted as INTEGER (sqlite has no bool). `is_oneshot` may be NULL until a sound
# has been categorized, so casting must tolerate None.
_INT_FIELDS = (*_BOOL_FIELDS, "is_oneshot")


@dataclass
class Hit:
    forage_id: str
    score: float  # cosine similarity (higher = more similar)
    meta: dict


LicenseFilter = Callable[[dict], bool]


class VectorStore(ABC):
    @abstractmethod
    def add(self, meta: dict, vector: np.ndarray) -> bool: ...
    @abstractmethod
    def search(self, query_vec: np.ndarray, top_k: int, license_filter: LicenseFilter | None = None) -> list[Hit]: ...
    @abstractmethod
    def similar(self, forage_id: str, top_k: int, license_filter: LicenseFilter | None = None) -> list[Hit]: ...
    @abstractmethod
    def get_vector(self, forage_id: str) -> np.ndarray | None: ...
    @abstractmethod
    def has_hash(self, file_hash: str) -> bool: ...
    @abstractmethod
    def list_all(self) -> list[dict]: ...
    @abstractmethod
    def count(self) -> int: ...


class SqliteVecStore(VectorStore):
    def __init__(self, db_path=None, dim: int | None = None):
        import sqlite_vec

        self.dim = int(dim or config.EMBEDDING_DIM)
        self.path = Path(db_path or config.db_path())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path))
        self.db.row_factory = sqlite3.Row
        self.db.enable_load_extension(True)
        sqlite_vec.load(self.db)
        self.db.enable_load_extension(False)
        self._init_schema()
        self._check_checkpoint()

    # -- setup -----------------------------------------------------------
    def _init_schema(self) -> None:
        self.db.execute(
            """CREATE TABLE IF NOT EXISTS sounds(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                forage_id TEXT UNIQUE, source TEXT, source_id TEXT,
                file_hash TEXT UNIQUE, filename TEXT, title TEXT,
                license_name TEXT, license_url TEXT,
                attribution_username TEXT, attribution_url TEXT,
                requires_attribution INTEGER, non_commercial INTEGER,
                share_alike INTEGER, no_derivatives INTEGER,
                tags TEXT, duration_ms INTEGER,
                checkpoint_id TEXT, embedding_dim INTEGER, added_at TEXT,
                category TEXT, is_oneshot INTEGER,
                embedding BLOB)"""
        )
        self.db.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_sounds USING vec0(embedding float[{self.dim}])"
        )
        self.db.execute("CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT)")
        self._migrate()
        self.db.commit()

    def _migrate(self) -> None:
        """Idempotently add columns introduced after a DB was first created. Additive
        and metadata-only on sqlite, so an older library.db gains them on next open."""
        cols = {r["name"] for r in self.db.execute("PRAGMA table_info(sounds)").fetchall()}
        for name, decl in (("category", "TEXT"), ("is_oneshot", "INTEGER")):
            if name not in cols:
                self.db.execute(f"ALTER TABLE sounds ADD COLUMN {name} {decl}")

    def _check_checkpoint(self) -> None:
        """Refuse to mix vectors from different checkpoints (different vector space)."""
        row = self.db.execute("SELECT value FROM meta WHERE key='checkpoint_id'").fetchone()
        if row is None:
            self.db.execute("INSERT INTO meta(key, value) VALUES('checkpoint_id', ?)", (config.CLAP_CHECKPOINT,))
            self.db.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('embedding_dim', ?)", (str(self.dim),))
            self.db.commit()
        else:
            if row["value"] != config.CLAP_CHECKPOINT:
                raise RuntimeError(
                    f"Index was built with checkpoint '{row['value']}' but config pins "
                    f"'{config.CLAP_CHECKPOINT}'. Run `forage reindex` to rebuild."
                )
            dim_row = self.db.execute("SELECT value FROM meta WHERE key='embedding_dim'").fetchone()
            if dim_row and int(dim_row["value"]) != self.dim:
                raise RuntimeError(
                    f"Index embedding_dim={dim_row['value']} but {self.dim} requested. "
                    "Run `forage reindex` to rebuild."
                )

    # -- helpers ---------------------------------------------------------
    def _prep(self, vector: np.ndarray) -> np.ndarray:
        v = np.asarray(vector, dtype=np.float32).ravel()
        if v.shape[0] != self.dim:
            raise ValueError(f"vector dim {v.shape[0]} != index dim {self.dim}")
        return v / (np.linalg.norm(v) + 1e-9)

    @staticmethod
    def _row_to_meta(row: sqlite3.Row) -> dict:
        m = {k: row[k] for k in _COLUMNS}
        m["tags"] = json.loads(row["tags"]) if row["tags"] else []
        for b in _BOOL_FIELDS:
            m[b] = bool(row[b])
        m["is_oneshot"] = bool(row["is_oneshot"])  # NULL (not categorized) -> False
        return m

    def _meta_by_rowid(self, rowid: int) -> dict | None:
        row = self.db.execute("SELECT * FROM sounds WHERE id=?", (rowid,)).fetchone()
        return self._row_to_meta(row) if row else None

    # -- writes ----------------------------------------------------------
    def add(self, meta: dict, vector: np.ndarray) -> bool:
        """Insert a sound + vector. Returns False if its file_hash/forage_id is
        already present (idempotent re-runs)."""
        import sqlite_vec

        vec = self._prep(vector)
        values = [meta.get(c) for c in _COLUMNS]
        values = [
            json.dumps(v) if c == "tags"
            else (int(v) if (c in _INT_FIELDS and v is not None) else v)
            for c, v in zip(_COLUMNS, values)
        ]
        placeholders = ", ".join("?" for _ in _COLUMNS)
        try:
            cur = self.db.execute(
                f"INSERT OR IGNORE INTO sounds({', '.join(_COLUMNS)}, embedding) "
                f"VALUES({placeholders}, ?)",
                (*values, vec.tobytes()),
            )
            if cur.rowcount == 0:  # duplicate forage_id or file_hash
                self.db.rollback()
                return False
            self.db.execute(
                "INSERT INTO vec_sounds(rowid, embedding) VALUES(?, ?)",
                (cur.lastrowid, sqlite_vec.serialize_float32(vec.tolist())),
            )
            self.db.commit()
            return True
        except Exception:
            self.db.rollback()
            raise

    # -- reads -----------------------------------------------------------
    def search(self, query_vec, top_k, license_filter=None) -> list[Hit]:
        import sqlite_vec

        q = self._prep(query_vec)
        over = top_k * 5 if license_filter else top_k
        rows = self.db.execute(
            "SELECT rowid, distance FROM vec_sounds WHERE embedding MATCH ? "
            "ORDER BY distance LIMIT ?",
            (sqlite_vec.serialize_float32(q.tolist()), over),
        ).fetchall()
        hits: list[Hit] = []
        for r in rows:
            meta = self._meta_by_rowid(r["rowid"])
            if meta is None:
                continue
            if license_filter and not license_filter(meta):
                continue
            score = 1.0 - (float(r["distance"]) ** 2) / 2.0  # L2 -> cosine for unit vectors
            hits.append(Hit(meta["forage_id"], score, meta))
            if len(hits) >= top_k:
                break
        return hits

    def similar(self, forage_id, top_k, license_filter=None) -> list[Hit]:
        v = self.get_vector(forage_id)
        if v is None:
            return []
        hits = self.search(v, top_k + 1, license_filter)
        return [h for h in hits if h.forage_id != forage_id][:top_k]

    def get_vector(self, forage_id) -> np.ndarray | None:
        row = self.db.execute("SELECT embedding FROM sounds WHERE forage_id=?", (forage_id,)).fetchone()
        if row is None or row["embedding"] is None:
            return None
        return np.frombuffer(row["embedding"], dtype=np.float32)

    def has_hash(self, file_hash) -> bool:
        return self.db.execute("SELECT 1 FROM sounds WHERE file_hash=?", (file_hash,)).fetchone() is not None

    def set_fields(self, forage_id: str, **kv) -> bool:
        """In-place UPDATE of derived metadata (category / is_oneshot) without a
        re-embed. Column names are whitelisted (never interpolated from caller input)."""
        kv = {k: v for k, v in kv.items() if k in ("category", "is_oneshot")}
        if not kv:
            return False
        kv = {k: (int(v) if (k == "is_oneshot" and v is not None) else v) for k, v in kv.items()}
        sets = ", ".join(f"{k}=?" for k in kv)
        cur = self.db.execute(f"UPDATE sounds SET {sets} WHERE forage_id=?", (*kv.values(), forage_id))
        self.db.commit()
        return cur.rowcount > 0

    def list_all(self) -> list[dict]:
        rows = self.db.execute("SELECT * FROM sounds ORDER BY id").fetchall()
        return [self._row_to_meta(r) for r in rows]

    def count(self) -> int:
        return int(self.db.execute("SELECT COUNT(*) AS n FROM sounds").fetchone()["n"])

    def close(self) -> None:
        self.db.close()
