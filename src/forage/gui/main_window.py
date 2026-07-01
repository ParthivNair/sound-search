"""The Forage main window: category sidebar + search/results + detail/transport.

The window holds the cached `list_all()` and does all category/scope/license filtering
client-side (instant, no CLAP). Text search / similar / grow / categorize are delegated
to the StoreWorker via signals.
"""

from __future__ import annotations

import subprocess

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QProgressBar, QPushButton, QRadioButton,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from .. import config
from .filters import combine_predicates
from .models_logic import category_counts
from .player import AuditionPlayer
from .results_model import SampleTableModel
from .results_view import SampleTableView
from .reveal import reveal_command, reveal_label

LICENSES = [("Any license", None), ("CC0", "cc0"), ("CC-BY", "by"), ("No-obligation", "free")]
SCOPES = [("All", "all"), ("One-shots", "oneshot"), ("Loops", "loop")]


class MainWindow(QMainWindow):
    searchRequested = Signal(str, int, str)
    similarRequested = Signal(str, int, str)
    growRequested = Signal(str, int, str)
    categorizeRequested = Signal(bool, float)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Forage")
        self.resize(1040, 660)
        self._all: list[dict] = []
        self._src_metas: list[dict] = []
        self._src_scores = None
        self._kit: list[dict] = []
        self._samples_dir = config.samples_dir()
        self._player = AuditionPlayer()
        self._build_ui()

    # -- construction ----------------------------------------------------
    def _build_ui(self):
        split = QSplitter(Qt.Horizontal)
        split.addWidget(self._build_sidebar())
        right = QSplitter(Qt.Vertical)
        right.addWidget(self._build_results())
        right.addWidget(self._build_detail())
        right.setStretchFactor(0, 4)
        right.setStretchFactor(1, 1)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)
        self.statusBar().showMessage("Starting…")

    def _hline(self):
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        return f

    def _build_sidebar(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.addWidget(QLabel("<b>Scope</b>"))
        self._scope_group = QButtonGroup(self)
        for i, (label, key) in enumerate(SCOPES):
            rb = QRadioButton(label)
            rb.setProperty("scope", key)
            rb.setChecked(i == 0)
            self._scope_group.addButton(rb)
            v.addWidget(rb)
        self._scope_group.buttonClicked.connect(lambda *_: self._apply_filters())
        v.addWidget(self._hline())
        v.addWidget(QLabel("<b>License</b>"))
        self._license = QComboBox()
        for label, spec in LICENSES:
            self._license.addItem(label, spec)
        self._license.currentIndexChanged.connect(lambda *_: self._apply_filters())
        v.addWidget(self._license)
        v.addWidget(self._hline())
        v.addWidget(QLabel("<b>Categories</b>"))
        self._cats = QListWidget()
        self._cats.itemClicked.connect(lambda *_: self._apply_filters())
        v.addWidget(self._cats, 1)
        w.setMinimumWidth(200)
        return w

    def _build_results(self):
        w = QWidget()
        v = QVBoxLayout(w)
        row = QHBoxLayout()
        self._query = QLineEdit()
        self._query.setPlaceholderText("warm dusty rhodes chord, short tail")
        self._query.returnPressed.connect(self._do_search)
        sbtn = QPushButton("Search")
        sbtn.clicked.connect(self._do_search)
        cbtn = QPushButton("Clear")
        cbtn.clicked.connect(self._clear_search)
        row.addWidget(self._query)
        row.addWidget(sbtn)
        row.addWidget(cbtn)
        v.addLayout(row)
        self._table = SampleTableView(self._samples_dir)
        self._model = SampleTableModel()
        self._table.setModel(self._model)
        self._table.clicked.connect(self._on_row_clicked)
        v.addWidget(self._table, 1)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.hide()
        v.addWidget(self._progress)
        return w

    def _build_detail(self):
        w = QWidget()
        v = QVBoxLayout(w)
        self._title = QLabel("—")
        self._title.setWordWrap(True)
        v.addWidget(self._title)
        row = QHBoxLayout()
        for label, slot in [("▶ Play", self._play_selected), ("■ Stop", self._player.stop),
                            ("Similar", self._do_similar), (reveal_label(), self._reveal),
                            ("Add to kit", self._add_to_kit), ("Export kit .sfz", self._export_kit)]:
            b = QPushButton(label)
            b.clicked.connect(slot)
            row.addWidget(b)
        v.addLayout(row)
        g = QHBoxLayout()
        self._grow_q = QLineEdit()
        self._grow_q.setPlaceholderText("grow more, e.g. vinyl crackle")
        self._grow_n = QSpinBox()
        self._grow_n.setRange(1, 50)
        self._grow_n.setValue(5)
        gbtn = QPushButton("Grow…")
        gbtn.clicked.connect(self._do_grow)
        catb = QPushButton("Categorize…")
        catb.clicked.connect(self._do_categorize)
        g.addWidget(self._grow_q)
        g.addWidget(self._grow_n)
        g.addWidget(gbtn)
        g.addWidget(catb)
        v.addLayout(g)
        return w

    # -- current selection helpers --------------------------------------
    def _license_spec(self):
        return self._license.currentData()

    def _scope(self):
        btn = self._scope_group.checkedButton()
        return btn.property("scope") if btn else "all"

    def _selected_category(self):
        it = self._cats.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _current_meta(self):
        idx = self._table.currentIndex()
        return self._model.meta_at(idx.row()) if idx.isValid() else None

    def _selected_metas(self):
        return self._model.metas_for_rows(self._table.selected_rows())

    # -- filtering / display --------------------------------------------
    def _set_source(self, metas, scores=None):
        self._src_metas = metas
        self._src_scores = scores
        self._apply_filters()

    def _apply_filters(self):
        pred = combine_predicates(self._scope(), self._license_spec(), self._selected_category())
        if self._src_scores is None:
            kept = [m for m in self._src_metas if pred(m)]
            self._model.set_items(kept)
            self.statusBar().showMessage(f"{len(kept)} of {len(self._all)} shown")
        else:
            kept = [(m, s) for m, s in zip(self._src_metas, self._src_scores) if pred(m)]
            self._model.set_items([m for m, _ in kept], [s for _, s in kept])
            self.statusBar().showMessage(f"{len(kept)} result(s)")
        self._table.resizeColumnsToContents()

    def _refresh_categories(self):
        self._cats.blockSignals(True)
        self._cats.clear()
        for label, count in category_counts(self._all):
            it = QListWidgetItem(f"{label} ({count})")
            it.setData(Qt.UserRole, None if label == "All" else label)
            self._cats.addItem(it)
        self._cats.setCurrentRow(0)
        self._cats.blockSignals(False)

    # -- user actions ----------------------------------------------------
    def _on_row_clicked(self, index):
        meta = self._model.meta_at(index.row())
        if meta:
            self._title.setText(f"{meta.get('title') or meta['forage_id']}  —  "
                                f"{meta.get('category') or 'uncategorized'}")
            self._player.play(self._samples_dir / meta["filename"])

    def _play_selected(self):
        m = self._current_meta()
        if m:
            self._player.play(self._samples_dir / m["filename"])

    def _do_search(self):
        q = self._query.text().strip()
        if not q:
            return
        self._progress.show()
        self.statusBar().showMessage("Searching…")
        self.searchRequested.emit(q, 50, self._license_spec() or "")

    def _clear_search(self):
        self._query.clear()
        self._set_source(self._all, None)

    def _do_similar(self):
        m = self._current_meta()
        if m:
            self._progress.show()
            self.statusBar().showMessage("Finding similar…")
            self.similarRequested.emit(m["forage_id"], 50, self._license_spec() or "")

    def _reveal(self):
        m = self._current_meta()
        if m:
            subprocess.run(reveal_command(self._samples_dir / m["filename"]))

    def _add_to_kit(self):
        for m in self._selected_metas():
            if m not in self._kit:
                self._kit.append(m)
        self.statusBar().showMessage(f"Kit: {len(self._kit)} sound(s)")

    def _export_kit(self):
        from .. import sfz as sfz_mod
        kit = self._kit or self._selected_metas()
        if not kit:
            QMessageBox.information(self, "Forage", "Select sounds or add them to the kit first.")
            return
        out = sfz_mod.write_sfz(kit, name="forage-kit", layout="drum-map")
        self._kit = []
        QMessageBox.information(self, "Forage",
                                f"Wrote {out}\n\nLoad it in sforzando (VST3) on an instrument track, "
                                "or use Cakewalk's XSampler / Pad Controller.")

    def _do_grow(self):
        q = self._grow_q.text().strip()
        if not q:
            return
        self._progress.show()
        self.statusBar().showMessage("Growing…")
        self.growRequested.emit(q, self._grow_n.value(), self._license_spec() or "")

    def _do_categorize(self):
        self._progress.show()
        self.statusBar().showMessage("Categorizing…")
        self.categorizeRequested.emit(False, config.CATEGORIZE_THRESHOLD)

    # -- worker callbacks ------------------------------------------------
    def on_listed(self, metas):
        self._all = metas
        self._refresh_categories()
        self._set_source(metas, None)

    def on_counted(self, n):
        self.statusBar().showMessage(f"{n} sounds")

    def on_searched(self, hits, query):
        self._progress.hide()
        self._set_source([h.meta for h in hits], [h.score for h in hits])

    def on_clap_loading(self):
        self.statusBar().showMessage("Loading CLAP model (first search, ~15s)…")

    def on_clap_ready(self):
        pass

    def on_grow_progress(self, s):
        self.statusBar().showMessage(s)

    def on_grow_done(self, kept, skipped):
        self._progress.hide()
        self.statusBar().showMessage(f"Grew {kept}, skipped {skipped}")

    def on_categorized(self, counts):
        self._progress.hide()
        self.statusBar().showMessage(f"Categorized {sum(counts.values())} sound(s)")

    def on_failed(self, msg):
        self._progress.hide()
        self.statusBar().showMessage("Error")
        QMessageBox.warning(self, "Forage", msg)
