from __future__ import annotations
from typing import Optional, List
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QFontMetrics, QPainter
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QFrame,
    QLabel
)

# Professional Dark Theme Stylesheet
TAB_STYLE = """
_ProjectTab {
    background-color: #2d2d2d;
    border-radius: 5px;
    border: 1px solid #3d3d3d;
}
_ProjectTab[active="true"] {
    background-color: #3d3d3d;
    border: 1px solid #007acc;
}
_ProjectTab:hover {
    border: 1px solid #555555;
}

/* The name button */
#select_btn {
    text-align: left;
    padding: 8px;
    border: none;
    background: transparent;
    color: #cccccc;
    font-size: 13px;
    font-weight: 500;
}
_ProjectTab[active="true"] #select_btn {
    color: #ffffff;
    font-weight: bold;
}

/* Action buttons (Save/Close) */
QPushButton.action_btn {
    border: none;
    background: transparent;
    color: #888888;
    font-size: 14px;
    border-radius: 3px;
}
QPushButton.action_btn:hover {
    background-color: #444444;
    color: #ffffff;
}
#close_btn:hover {
    background-color: #c42b1c;
    color: white;
}

QPushButton#new_btn {
    background-color: #007acc;
    color: white;
    border: none;
    border-radius: 4px;
    font-weight: bold;
    padding: 8px;
    margin-bottom: 5px;
}
QPushButton#new_btn:hover {
    background-color: #0098ff;
}

QScrollArea {
    border: none;
    background: transparent;
}
"""

class ElidedButton(QPushButton):
    """A button that automatically elides text (adds ...) if the text is too long."""
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._full_text = text

    def setText(self, text):
        self._full_text = text
        super().setText(text)
        self.update()

    def paintEvent(self, event):
        # We calculate the elided text right before drawing
        painter = QPainter(self)
        metrics = QFontMetrics(self.font())
        
        # Calculate available width (total width - padding/icon space)
        icon_width = self.iconSize().width() + 10 if not self.icon().isNull() else 0
        available_width = self.width() - icon_width - 20 # 20 for padding
        
        elided = metrics.elidedText(self._full_text, Qt.TextElideMode.ElideRight, available_width)
        
        # Temporarily swap text to draw, then swap back (or just use drawText)
        # However, for QPushButton, it's easier to set the internal text
        if elided != self.text():
            super().setText(elided)
        
        super().paintEvent(event)

class _ProjectTab(QFrame):
    """Internal widget representing a single project row."""
    activated = pyqtSignal(int)
    closed = pyqtSignal(int)
    saved = pyqtSignal(int)

    def __init__(self, index: int, label: str, active: bool,
                 thumbnail: Optional[QPixmap] = None, parent=None):
        super().__init__(parent)
        self.index = index
        self.setObjectName("_ProjectTab")
        self.setProperty("active", active)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(2)

        # Elided Name Button
        self.select_btn = ElidedButton(label)
        self.select_btn.setObjectName("select_btn")
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # This allows the button to shrink as small as needed
        self.select_btn.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        
        if thumbnail and not thumbnail.isNull():
            self.select_btn.setIcon(QIcon(thumbnail))
            self.select_btn.setIconSize(QSize(24, 24))
        
        # Save Button
        self.save_btn = QPushButton("💾")
        self.save_btn.setProperty("class", "action_btn")
        self.save_btn.setFixedSize(28, 28)
        self.save_btn.setToolTip("Save Project")

        # Close/Delete Button
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("close_btn")
        self.close_btn.setProperty("class", "action_btn") 
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close Project")

        layout.addWidget(self.select_btn, stretch=1) # Name takes all available space
        layout.addWidget(self.save_btn)
        layout.addWidget(self.close_btn)

        self.select_btn.clicked.connect(lambda: self.activated.emit(self.index))
        self.save_btn.clicked.connect(lambda: self.saved.emit(self.index))
        self.close_btn.clicked.connect(lambda: self.closed.emit(self.index))

    def set_active(self, is_active: bool):
        if self.property("active") == is_active:
            return
        self.setProperty("active", is_active)
        self.style().unpolish(self)
        self.style().polish(self)


class ProjectTabs(QWidget):
    project_activated = pyqtSignal(int)
    project_closed = pyqtSignal(int)
    project_saved = pyqtSignal(int)
    new_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(TAB_STYLE)
        self._tabs: List[_ProjectTab] = []

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(2)

        self.new_btn = QPushButton("+ New Project")
        self.new_btn.setObjectName("new_btn")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_requested.emit)
        
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 5, 0)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.addStretch(1) 
        
        self.scroll.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.new_btn)
        self.main_layout.addWidget(self.scroll)

    def set_projects(self, labels: list[str], active_index: int,
                     thumbnails: Optional[list[QPixmap]] = None) -> None:
        # Clear existing
        for tab in self._tabs:
            tab.setParent(None)
            tab.deleteLater()
        self._tabs.clear()

        # Rebuild
        for i, label in enumerate(labels):
            thumb = thumbnails[i] if thumbnails and i < len(thumbnails) else None
            tab = _ProjectTab(i, label, i == active_index, thumbnail=thumb)
            
            tab.activated.connect(self.project_activated.emit)
            tab.closed.connect(self.project_closed.emit)
            tab.saved.connect(self.project_saved.emit)
            
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, tab)
            self._tabs.append(tab)

    def set_active_index(self, active_index: int):
        for i, tab in enumerate(self._tabs):
            tab.set_active(i == active_index)


# --- Demo logic ---
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    
    window = QWidget()
    window.setWindowTitle("Fixed Sidebar Demo")
    window.resize(250, 400) # Narrow width to test shrinking
    window.setStyleSheet("background-color: #1e1e1e;")

    layout = QVBoxLayout(window)
    tabs_widget = ProjectTabs()
    layout.addWidget(tabs_widget)

    # State
    projects = ["Logo Design", "A Very Long Project Name That Might Break UI", "Web UI", "Video"]
    current_idx = 0

    def refresh():
        tabs_widget.set_projects(projects, current_idx)

    def on_activate(idx):
        global current_idx
        current_idx = idx
        tabs_widget.set_active_index(idx)

    def on_close(idx):
        global current_idx
        if len(projects) > 1:
            projects.pop(idx)
            current_idx = min(current_idx, len(projects) - 1)
            refresh()

    def on_new():
        projects.append(f"New Project {len(projects)+1}")
        refresh()

    tabs_widget.project_activated.connect(on_activate)
    tabs_widget.project_closed.connect(on_close)
    tabs_widget.new_requested.connect(on_new)

    refresh()
    window.show()
    sys.exit(app.exec())