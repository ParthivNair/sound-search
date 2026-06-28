"""Qt table model wrapping a list of result rows (meta + optional score)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

from .models_logic import COLUMNS, build_row


class SampleTableModel(QAbstractTableModel):
    def __init__(self):
        super().__init__()
        self._rows: list[tuple[dict, float | None]] = []

    def set_items(self, metas, scores=None):
        self.beginResetModel()
        if scores is None:
            self._rows = [(m, None) for m in metas]
        else:
            self._rows = list(zip(metas, scores))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        meta, score = self._rows[index.row()]
        return build_row(meta, score)[index.column()]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def meta_at(self, row):
        return self._rows[row][0] if 0 <= row < len(self._rows) else None

    def metas_for_rows(self, rows):
        return [self._rows[r][0] for r in rows if 0 <= r < len(self._rows)]
