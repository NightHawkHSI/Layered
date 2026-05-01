"""Bottom project switcher: tabs with close + save buttons per project."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class _ProjectTab(QWidget):
    activated = pyqtSignal(int)
    closed = pyqtSignal(int)
    saved = pyqtSignal(int)

    def __init__(self, index: int, label: str, active: bool,
                 thumbnail: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.index = index
        self.select_btn = QPushButton(label)
        self.select_btn.setCheckable(True)
        self.select_btn.setChecked(active)
        self.select_btn.setMinimumWidth(60)
        self.select_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.select_btn.setStyleSheet("text-align: left; padding: 4px 8px;")
        if thumbnail is not None and not thumbnail.isNull():
            self.select_btn.setIcon(QIcon(thumbnail))
            self.select_btn.setIconSize(QSize(28, 28))
        self.select_btn.clicked.connect(lambda: self.activated.emit(self.index))

        self.save_btn = QPushButton("💾")
        self.save_btn.setFixedWidth(28)
        self.save_btn.setToolTip("Save composite")
        self.save_btn.clicked.connect(lambda: self.saved.emit(self.index))

        self.close_btn = QPushButton("✕")
        self.close_btn.setFixedWidth(24)
        self.close_btn.setToolTip("Close project")
        self.close_btn.clicked.connect(lambda: self.closed.emit(self.index))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)
        layout.addWidget(self.select_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.close_btn)


class ProjectTabs(QWidget):
    project_activated = pyqtSignal(int)
    project_closed = pyqtSignal(int)
    project_saved = pyqtSignal(int)
    new_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self._row_widget = QWidget()
        self._row = QVBoxLayout(self._row_widget)
        self._row.setContentsMargins(4, 4, 4, 4)
        self._row.setSpacing(4)
        self._row.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setWidget(self._row_widget)

        self.new_btn = QPushButton("+ New")
        self.new_btn.clicked.connect(self.new_requested.emit)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        outer.addWidget(self.new_btn)
        outer.addWidget(self.scroll, 1)

    def set_projects(self, labels: list[str], active_index: int,
                     thumbnails: Optional[list[QPixmap]] = None) -> None:
        # Wipe row
        while self._row.count():
            item = self._row.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        for i, label in enumerate(labels):
            thumb = thumbnails[i] if thumbnails and i < len(thumbnails) else None
            tab = _ProjectTab(i, label, i == active_index, thumbnail=thumb)
            tab.activated.connect(self.project_activated.emit)
            tab.closed.connect(self.project_closed.emit)
            tab.saved.connect(self.project_saved.emit)
            self._row.addWidget(tab)
        self._row.addStretch(1)
