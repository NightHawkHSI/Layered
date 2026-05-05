"""Bridge wrapper: MagicWand tool with its own popout settings UI.

Inherits the legacy MagicWandTool implementation from _builtin_tools.py
and adds the build_ui() hook so the tool panel mounts a single button
whose dropdown menu hosts the tolerance slider. That keeps the main
toolbar a fixed size and stops it from reflowing when the wand is
selected.

The reapply call is debounced through a QTimer so dragging the slider
does not trigger a flood of full-image scans.
"""
import importlib.util
import sys
from pathlib import Path

from PyQt6.QtCore import QTimer
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

_KEY = "_layered_builtin_tools"
if _KEY not in sys.modules:
    src = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    spec = importlib.util.spec_from_file_location(_KEY, src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[_KEY] = mod
    spec.loader.exec_module(mod)

_BaseMagicWand = sys.modules[_KEY].MagicWandTool


class MagicWandTool(_BaseMagicWand):
    def build_ui(self, parent, ctx):
        btn = QToolButton(parent)
        btn.setText("Tolerance")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(110)

        menu = QMenu(btn)
        host = QWidget(menu)
        row = QHBoxLayout(host)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)
        row.addWidget(QLabel("Tolerance"))
        slider = SliderField(0, 255, int(getattr(ctx, "fill_tolerance", 32)),
                             slider_width=180)
        row.addWidget(slider)

        # Debounce reapply so dragging the slider doesn't run a full
        # flood-fill scan on every pixel of slider travel.
        debounce = QTimer(host)
        debounce.setSingleShot(True)
        debounce.setInterval(120)

        def _reapply():
            try:
                self.reapply()
            except Exception:
                pass

        debounce.timeout.connect(_reapply)

        def _on_change(v: int) -> None:
            ctx.fill_tolerance = int(v)
            cb = getattr(ctx, "on_tolerance_changed", None)
            if callable(cb):
                cb()
            debounce.start()

        slider.valueChanged.connect(_on_change)

        action = QWidgetAction(menu)
        action.setDefaultWidget(host)
        menu.addAction(action)
        btn.setMenu(menu)
        return btn


TOOL_CLASS = MagicWandTool
