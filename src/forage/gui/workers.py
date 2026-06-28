"""The store/CLAP worker. Owns the SqliteVecStore connection on ONE thread (sqlite
connections and the CLAP/torch singleton are not safe to touch across threads), and
serves every DB/embedding request issued by the GUI thread via signals.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot


class StoreWorker(QObject):
    listed = Signal(list)        # list[dict] from list_all()
    counted = Signal(int)
    searched = Signal(list, str)  # list[Hit], query label
    clapLoading = Signal()
    clapReady = Signal()
    growProgress = Signal(str)
    growDone = Signal(int, int)   # kept, skipped
    categorized = Signal(dict)
    failed = Signal(str)

    def __init__(self):
        super().__init__()
        self._store = None

    @Slot()
    def start(self):
        try:
            from ..index import SqliteVecStore
            self._store = SqliteVecStore()           # connection bound to THIS thread
            self.counted.emit(self._store.count())
            self.listed.emit(self._store.list_all())
        except Exception as e:  # surface DB/setup errors instead of dying silently
            self.failed.emit(str(e))

    @staticmethod
    def _lf(spec):
        from ..predicates import license_filter
        return license_filter(spec or None)

    @Slot(str, int, str)
    def do_search(self, query, top_k, license_spec):
        try:
            from .. import embed
            if embed._model is None:
                self.clapLoading.emit()
            vec = embed.embed_text(query)            # heavy on first call; on THIS thread
            self.clapReady.emit()
            self.searched.emit(self._store.search(vec, top_k, license_filter=self._lf(license_spec)), query)
        except Exception as e:
            self.failed.emit(str(e))

    @Slot(str, int, str)
    def do_similar(self, forage_id, top_k, license_spec):
        try:
            hits = self._store.similar(forage_id, top_k, license_filter=self._lf(license_spec))
            self.searched.emit(hits, f"similar:{forage_id}")
        except Exception as e:
            self.failed.emit(str(e))

    @Slot(str, int, str)
    def do_grow(self, query, count, license_spec):
        try:
            from .. import grow as grow_mod
            kept, skipped = grow_mod.grow(query, count, store=self._store,
                                          license_filter=self._lf(license_spec),
                                          progress=self.growProgress.emit)
            self.growDone.emit(kept, skipped)
            self.listed.emit(self._store.list_all())
        except Exception as e:
            self.failed.emit(str(e))

    @Slot(bool, float)
    def do_categorize(self, recompute, threshold):
        try:
            from .. import categorize as cat_mod
            from .. import embed
            counts = cat_mod.categorize(self._store, embed.embed_text, recompute=recompute,
                                        threshold=threshold, progress=self.growProgress.emit)
            self.categorized.emit(counts)
            self.listed.emit(self._store.list_all())
        except Exception as e:
            self.failed.emit(str(e))
