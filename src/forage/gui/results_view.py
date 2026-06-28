"""Results table with native drag-OUT: dropping selected rows onto a Cakewalk track
deposits the actual WAV file(s) via a standard Windows CF_HDROP (QMimeData URLs).

We start the drag manually from mouseMoveEvent rather than relying on QTableView's
built-in heuristic (which only starts a drag when the press lands on an *already
selected* row — so a first press-and-drag just extends the selection and never
arms a file drag). Here, press selects the row(s) and any drag past the threshold
extracts them.
"""

from __future__ import annotations

from PySide6.QtCore import QMimeData, Qt, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QAbstractItemView, QApplication, QTableView

from .dnd import paths_for_metas


class SampleTableView(QTableView):
    def __init__(self, samples_dir):
        super().__init__()
        self._samples_dir = samples_dir
        self._press_pos = None
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)

    def selected_rows(self) -> list[int]:
        return sorted({i.row() for i in self.selectionModel().selectedRows()})

    def selected_paths(self):
        return paths_for_metas(self.model().metas_for_rows(self.selected_rows()), self._samples_dir)

    # -- manual drag-out -------------------------------------------------
    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint() if event.button() == Qt.LeftButton else None
        super().mousePressEvent(event)  # normal selection on press

    def mouseMoveEvent(self, event):
        if (self._press_pos is not None
                and (event.buttons() & Qt.LeftButton)
                and self.selected_rows()
                and (event.position().toPoint() - self._press_pos).manhattanLength()
                    >= QApplication.startDragDistance()):
            self._press_pos = None
            self.startDrag(Qt.CopyAction)   # blocks until the drop completes
            return                          # swallow: don't let the view extend selection
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        super().mouseReleaseEvent(event)

    def startDrag(self, supported_actions):
        paths = self.selected_paths()
        if not paths:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])  # -> CF_HDROP on Windows
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.CopyAction)  # COPY: never moves the library file
