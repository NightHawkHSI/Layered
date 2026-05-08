"""
Bottom project switcher: tabs with close + save buttons per project.
Features: 
- Smooth scrolling
- Dynamic QSS styling (Dark Mode)
- Optimized 'active' state switching without UI rebuilding
- Thumbnail support
"""
from __future__ import annotations

from typing import Optional, List
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QFrame,
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
_ProjectTab[active="true"]:hover {
    border: 1px solid #0098ff;
}

QPushButton#select_btn {
    text-align: left;
    padding: 8px;
    border: none;
    background: transparent;
    color: #cccccc;
    font-size: 13px;
    font-weight: 500;
}
_ProjectTab[active="true"] QPushButton#select_btn {
    color: #ffffff;
    font-weight: bold;
}

QPushButton#action_btn {
    border: none;
    background: transparent;
    color: #888888;
    font-size: 14px;
    border-radius: 3px;
}
QPushButton#action_btn:hover {
    background-color: #444444;
    color: #ffffff;
}
QPushButton#close_btn:hover {
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
}
QPushButton#new_btn:hover {
    background-color: #0098ff;
}
QPushButton#new_btn:pressed {
    background-color: #005a9e;
}

QScrollArea {
    border: none;
    background: transparent;
}
"""

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
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        # Main selection button (Label + Thumbnail)
        self.select_btn = QPushButton(label)
        self.select_btn.setObjectName("select_btn")
        self.select_btn.setCheckable(True)
        self.select_btn.setChecked(active)
        self.select_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.select_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        if thumbnail and not thumbnail.isNull():
            self.select_btn.setIcon(QIcon(thumbnail))
            self.select_btn.setIconSize(QSize(24, 24))
        
        # Save Button
        self.save_btn = QPushButton("💾")
        self.save_btn.setObjectName("action_btn")
        self.save_btn.setFixedSize(28, 28)
        self.save_btn.setToolTip("Save Project")

        # Close Button
        self.close_btn = QPushButton("✕")
        self.close_btn.setObjectName("close_btn") # Specialized hover color
        self.close_btn.setProperty("class", "action_btn") 
        # Note: we use both objectName and class for CSS flexibility
        self.close_btn.setFixedSize(28, 28)
        self.close_btn.setToolTip("Close Project")
        # Apply the general action_btn style manually since we changed ObjectName
        self.close_btn.setStyleSheet("QPushButton { border: none; background: transparent; color: #888888; border-radius: 3px; }")

        layout.addWidget(self.select_btn)
        layout.addWidget(self.save_btn)
        layout.addWidget(self.close_btn)

        # Wire signals (using captured index to ensure correctness)
        self.select_btn.clicked.connect(lambda: self.activated.emit(self.index))
        self.save_btn.clicked.connect(lambda: self.saved.emit(self.index))
        self.close_btn.clicked.connect(lambda: self.closed.emit(self.index))

    def set_active(self, is_active: bool):
        """Updates the visual state without rebuilding the widget."""
        if self.property("active") == is_active:
            return
        self.setProperty("active", is_active)
        self.select_btn.setChecked(is_active)
        # Refresh stylesheet properties
        self.style().unpolish(self)
        self.style().polish(self)


class ProjectTabs(QWidget):
    """The main sidebar/bottom bar project switcher."""
    project_activated = pyqtSignal(int)
    project_closed = pyqtSignal(int)
    project_saved = pyqtSignal(int)
    new_requested = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setStyleSheet(TAB_STYLE)
        self._tabs: List[_ProjectTab] = []

        # Outer Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(8)

        # "New Project" Button
        self.new_btn = QPushButton("+ New Project")
        self.new_btn.setObjectName("new_btn")
        self.new_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.new_btn.clicked.connect(self.new_requested.emit)
        
        # Scroll Area Setup
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 2, 0)
        self.scroll_layout.setSpacing(4)
        self.scroll_layout.addStretch(1) # Keeps items at the top
        
        self.scroll.setWidget(self.scroll_content)

        self.main_layout.addWidget(self.new_btn)
        self.main_layout.addWidget(self.scroll)

    def set_projects(self, labels: list[str], active_index: int,
                     thumbnails: Optional[list[QPixmap]] = None) -> None:
        """
        Clears and rebuilds the project list. 
        Use this when projects are added or removed.
        """
        # Clean up existing widgets
        while self.scroll_layout.count() > 1: # Keep the stretch
            item = self.scroll_layout.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()
        self._tabs = []

        # Build new tabs
        for i, label in enumerate(labels):
            thumb = thumbnails[i] if thumbnails and i < len(thumbnails) else None
            tab = _ProjectTab(i, label, i == active_index, thumbnail=thumb)
            
            tab.activated.connect(self.project_activated.emit)
            tab.closed.connect(self.project_closed.emit)
            tab.saved.connect(self.project_saved.emit)
            
            # Insert before the stretch at the bottom
            self.scroll_layout.insertWidget(self.scroll_layout.count() - 1, tab)
            self._tabs.append(tab)

    def set_active_index(self, active_index: int):
        """
        Efficiently updates which tab is highlighted.
        Does not rebuild the list, so it's safe to call frequently.
        """
        for i, tab in enumerate(self._tabs):
            tab.set_active(i == active_index)


# --- Example Usage / Demo ---
if __name__ == "__main__":
    import sys

    app = QApplication(sys.argv)
    
    # Create main window container
    window = QWidget()
    window.setWindowTitle("Project Switcher Demo")
    window.resize(300, 500)
    window.setStyleSheet("background-color: #1e1e1e;") # Dark background for the app

    layout = QVBoxLayout(window)
    
    # Initialize the component
    tabs_widget = ProjectTabs()
    layout.addWidget(tabs_widget)

    # Mock Data
    project_list = ["Logo Design", "Website UI", "Video Edit", "Mobile App"]
    
    def on_project_activated(idx):
        print(f"Switching to: {project_list[idx]}")
        tabs_widget.set_active_index(idx)

    def on_new():
        name = f"Project {len(project_list) + 1}"
        project_list.append(name)
        tabs_widget.set_projects(project_list, len(project_list)-1)
        print(f"Created: {name}")

    # Initial Population
    tabs_widget.set_projects(project_list, 0)

    # Connect signals
    tabs_widget.project_activated.connect(on_project_activated)
    tabs_widget.new_requested.connect(on_new)
    tabs_widget.project_closed.connect(lambda i: print(f"Closing {i}"))
    tabs_widget.project_saved.connect(lambda i: print(f"Saving {i}"))

    window.show()
    sys.exit(app.exec())