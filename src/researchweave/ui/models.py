"""Virtualized, accessible Qt table model for bounded research data previews."""

from __future__ import annotations

from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt


class ResearchTableModel(QAbstractTableModel):
    """Never allocates a QWidget/item for individual data cells."""

    def __init__(
        self, columns: list[str] | None = None, rows: list[list[str]] | None = None
    ) -> None:
        super().__init__()
        self.columns = list(columns or [])
        self.rows = list(rows or [])

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.rows)

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> object:
        if not index.isValid():
            return None
        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.ToolTipRole,
            Qt.ItemDataRole.AccessibleTextRole,
        ):
            return str(self.rows[index.row()][index.column()])
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = self.rows[index.row()][index.column()]
            try:
                float(value)
            except ValueError:
                return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> object:
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.AccessibleTextRole):
            return (
                self.columns[section]
                if orientation == Qt.Orientation.Horizontal
                else str(section + 1)
            )
        return None

    def set_records(self, columns: list[str], rows: list[list[str]]) -> None:
        self.beginResetModel()
        self.columns = list(columns)
        self.rows = list(rows)
        self.endResetModel()
