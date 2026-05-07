"""Bridge wrapper: MagicWand tool with its own popout settings UI."""

import importlib.util
import sys
from pathlib import Path
from typing import Optional, Callable

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from app.ui.slider_field import SliderField

def _load_builtin_wand():
    """Safely imports the legacy MagicWandTool from the relative path."""
    module_key = "_layered_builtin_tools"
    if module_key not in sys.modules:
        # Resolve path to _builtin_tools.py (3 levels up)
        src = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
        if not src.exists():
            raise ImportError(f"Could not find legacy tool source at {src}")
            
        spec = importlib.util.spec_from_file_location(module_key, src)
        if spec and spec.loader:
            mod = importlib.util.module_from_spec(spec)
            sys.modules[module_key] = mod
            spec.loader.exec_module(mod)
    
    return sys.modules[module_key].MagicWandTool

_BaseMagicWand = _load_builtin_wand()


class MagicWandTool(_BaseMagicWand):
    def build_ui(self, parent: QWidget, ctx: object) -> QToolButton:
        """
        Constructs a QToolButton with a dropdown menu containing 
        the tolerance configuration.
        """
        # 1. Main Button Setup
        btn = QToolButton(parent)
        btn.setText("Tolerance")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(110)
        btn.setToolTip("Magic Wand Settings")

        # 2. Menu and Slider Content
        menu = QMenu(btn)
        container = QWidget(menu)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        label = QLabel("Tolerance")
        # Ensure label doesn't shrink
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        current_val = int(getattr(ctx, "fill_tolerance", 32))
        slider = SliderField(0, 255, current_val, slider_width=180)
        
        layout.addWidget(label)
        layout.addWidget(slider)

        # 3. Debounce Logic
        # We use a single-shot timer to prevent lag during slider dragging
        debounce = QTimer(container)
        debounce.setSingleShot(True)
        debounce.setInterval(120)

        def _safe_reapply():
            """Executes reapply logic, ignoring errors if the tool state is invalid."""
            try:
                if hasattr(self, "reapply"):
                    self.reapply()
            except Exception as e:
                print(f"MagicWand reapply failed: {e}")

        debounce.timeout.connect(_safe_reapply)

        def _handle_change(value: int) -> None:
            """Updates context and triggers the debounce timer."""
            ctx.fill_tolerance = int(value)
            
            # Fire optional callback if defined in context
            on_change_cb = getattr(ctx, "on_tolerance_changed", None)
            if callable(on_change_cb):
                on_change_cb()
            
            debounce.start()

        slider.valueChanged.connect(_handle_change)

        # 4. Integrate into Menu
        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        btn.setMenu(menu)

        return btn


TOOL_CLASS = MagicWandTool