import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
from typing import Optional, Tuple
import numpy as np

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from app.ui.slider_field import SliderField

_SHARED_KEY = "_layered_brushes_shared"
if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)
_sh = _sys.modules[_SHARED_KEY]

Layer = _sh.Layer
Image = _sh.Image
ToolContext = _sh.ToolContext
_SelectionToolBase = _sh._SelectionToolBase


class MagicWandTool(_SelectionToolBase):
    """Click to select contiguous pixels within tolerance."""
    name = "Magic Wand"
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._seed: Optional[Tuple[int, "Layer", int, int, bool]] = None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._begin_move_if_inside(layer, x, y):
            return
        ox, oy = layer.offset
        lx, ly = x - ox, y - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return
        self._sample_and_commit(layer, lx, ly, additive_mode=(self.ctx.shift_held or self.ctx.alt_held))

    def _sample_and_commit(self, layer: Layer, lx: int, ly: int,
                           additive_mode: bool, ctrl_mode: Optional[bool] = None) -> None:
        ox, oy = layer.offset
        arr = np.asarray(layer.image.convert("RGBA"), dtype=np.int16)
        target = arr[ly, lx].astype(np.int16)
        tol = max(0, int(self.ctx.fill_tolerance))
        if target[3] == 0:
            match = arr[..., 3] == 0
        else:
            diff = np.abs(arr[..., :3] - target[:3]).max(axis=-1)
            match = (diff <= tol) & (arr[..., 3] > 0)
        h, w = match.shape
        use_ctrl = self.ctx.ctrl_held if ctrl_mode is None else ctrl_mode
        if use_ctrl:
            visited = match
        else:
            visited = np.zeros_like(match)
            stack = [(lx, ly)]
            while stack:
                px, py = stack.pop()
                if px < 0 or py < 0 or px >= w or py >= h:
                    continue
                if visited[py, px] or not match[py, px]:
                    continue
                visited[py, px] = True
                stack.extend(((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)))
        canvas_w, canvas_h = self._canvas_size(layer)
        canvas_mask = Image.new("L", (canvas_w, canvas_h), 0)
        layer_mask = Image.fromarray((visited * 255).astype(np.uint8), mode="L")
        canvas_mask.paste(layer_mask, (ox, oy))
        if additive_mode:
            combined = self._combine_with_current(canvas_mask, layer)
        else:
            combined = canvas_mask
        self._commit_mask(combined)
        self._seed = (id(layer), layer, lx, ly, use_ctrl)
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None:
            try:
                ca("Magic Wand")
            except Exception:
                pass

    def reapply(self) -> None:
        if self._seed is None:
            return
        _, layer, lx, ly, ctrl_mode = self._seed
        if layer.image is None:
            self._seed = None
            return
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            self._seed = None
            return
        self._sample_and_commit(layer, lx, ly, additive_mode=False, ctrl_mode=ctrl_mode)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._move_mode:
            self._continue_move(x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._end_move()
        super().release(layer, x, y)

    def build_ui(self, parent: QWidget, ctx: object) -> QToolButton:
        btn = QToolButton(parent)
        btn.setText("Tolerance")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(110)
        btn.setToolTip("Magic Wand Settings")

        menu = QMenu(btn)
        container = QWidget(menu)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        label = QLabel("Tolerance")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        current_val = int(getattr(ctx, "fill_tolerance", 32))
        slider = SliderField(0, 255, current_val, slider_width=180)

        layout.addWidget(label)
        layout.addWidget(slider)

        debounce = QTimer(container)
        debounce.setSingleShot(True)
        debounce.setInterval(120)

        def _safe_reapply():
            try:
                if hasattr(self, "reapply"):
                    self.reapply()
            except Exception as e:
                print(f"MagicWand reapply failed: {e}")

        debounce.timeout.connect(_safe_reapply)

        def _handle_change(value: int) -> None:
            ctx.fill_tolerance = int(value)
            on_change_cb = getattr(ctx, "on_tolerance_changed", None)
            if callable(on_change_cb):
                on_change_cb()
            debounce.start()

        slider.valueChanged.connect(_handle_change)

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        btn.setMenu(menu)

        return btn


TOOL_CLASS = MagicWandTool
