import importlib.util as _iu
import sys as _sys
from collections import deque
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

# ---------------------------------------------------------------------------
# Shared module bootstrap
# ---------------------------------------------------------------------------
_SHARED_KEY = "_layered_brushes_shared"
if _SHARED_KEY not in _sys.modules:
    _src  = _P(__file__).resolve().parents[2] / "_shared.py"
    _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
    _mod  = _iu.module_from_spec(_spec)
    _sys.modules[_SHARED_KEY] = _mod
    _spec.loader.exec_module(_mod)
_sh = _sys.modules[_SHARED_KEY]

Layer              = _sh.Layer
Image              = _sh.Image
ToolContext        = _sh.ToolContext
_SelectionToolBase = _sh._SelectionToolBase

# Prefer the shared helper if it exists (new _shared.py); fall back to a
# local definition so the tool loads cleanly against older shared modules.
_right_button_held = getattr(_sh, "_right_button_held", None)
if _right_button_held is None:
    def _right_button_held() -> bool:
        try:
            from PyQt6.QtWidgets import QApplication
            from PyQt6.QtCore import Qt
            return bool(QApplication.mouseButtons() & Qt.MouseButton.RightButton)
        except Exception:
            return False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DEFAULT_TOLERANCE: int = 32
_MIN_TOLERANCE:     int = 0
_MAX_TOLERANCE:     int = 255
_DEBOUNCE_MS:       int = 120

# Type alias — (layer, lx, ly, use_ctrl)
_Seed = Tuple["Layer", int, int, bool]


class MagicWandTool(_SelectionToolBase):
    """Click to select contiguous pixels within a colour tolerance.

    Modifier keys
    -------------
    Shift / Alt  Additive selection (union with existing mask).
    Ctrl         Select *all* matching pixels globally — no flood fill.
    Right-click  Move the existing selection without re-sampling.
    """

    name      = "Magic Wand"
    tool_id   = "magic_wand"
    commit_on = None

    def __init__(self, ctx: ToolContext) -> None:
        super().__init__(ctx)
        self._seed: Optional[_Seed] = None

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------

    def press(self, layer: Layer, x: int, y: int) -> None:
        # Right-click: move the existing selection only — never re-sample.
        # We check Qt's global mouse state because the dispatcher routes
        # all buttons through the same press() signature.
        if _right_button_held():
            self._begin_move_if_inside(layer, x, y)
            return

        if self._begin_move_if_inside(layer, x, y):
            return

        lx, ly = self._to_layer_coords(layer, x, y)
        if not self._in_bounds(layer, lx, ly):
            return
        additive = self.ctx.shift_held or self.ctx.alt_held
        self._sample_and_commit(layer, lx, ly, additive_mode=additive)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._move_mode:
            self._continue_move(x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._end_move()
        super().release(layer, x, y)

    # ------------------------------------------------------------------
    # Core selection logic
    # ------------------------------------------------------------------

    def reapply(self) -> None:
        """Re-run the last selection with the current tolerance / modifiers."""
        if self._seed is None:
            return
        layer, lx, ly, ctrl_mode = self._seed
        if layer.image is None or not self._in_bounds(layer, lx, ly):
            self._seed = None
            return
        additive = self.ctx.shift_held or self.ctx.alt_held
        self._sample_and_commit(
            layer, lx, ly, additive_mode=additive, ctrl_mode=ctrl_mode
        )

    def _sample_and_commit(
        self,
        layer: Layer,
        lx: int,
        ly: int,
        *,
        additive_mode: bool,
        ctrl_mode: Optional[bool] = None,
    ) -> None:
        use_ctrl   = self.ctx.ctrl_held if ctrl_mode is None else ctrl_mode
        arr        = np.asarray(layer.image.convert("RGBA"), dtype=np.uint8)

        match_mask = self._build_match_mask(arr, lx, ly)
        visited    = match_mask if use_ctrl else self._flood_fill(match_mask, lx, ly)

        canvas_mask = self._to_canvas_mask(visited, layer)
        if additive_mode:
            canvas_mask = self._combine_with_current(canvas_mask, layer)

        self._commit_mask(canvas_mask)
        self._seed = (layer, lx, ly, use_ctrl)
        self._notify_commit("Magic Wand")

    # ------------------------------------------------------------------
    # Mask building
    # ------------------------------------------------------------------

    def _build_match_mask(self, arr: np.ndarray, lx: int, ly: int) -> np.ndarray:
        """Bool array: pixels that match the seed colour within tolerance."""
        target = arr[ly, lx]
        tol    = max(_MIN_TOLERANCE, int(self.ctx.fill_tolerance))

        if target[3] == 0:
            return arr[..., 3] == 0

        diff = np.abs(arr[..., :3].astype(np.int16) - target[:3].astype(np.int16))
        return (diff.max(axis=-1) <= tol) & (arr[..., 3] > 0)

    @staticmethod
    def _flood_fill(match: np.ndarray, sx: int, sy: int) -> np.ndarray:
        """4-connected flood fill starting at (sx, sy).

        Uses scipy connected-components when available (much faster on
        large images); falls back to a pure-Python deque stack otherwise.
        """
        try:
            from scipy.ndimage import label as _label  # type: ignore
            labeled, _ = _label(match)
            seed_label = labeled[sy, sx]
            if seed_label == 0:
                return np.zeros_like(match)
            return labeled == seed_label
        except ImportError:
            pass

        h, w    = match.shape
        visited = np.zeros_like(match)
        if not match[sy, sx]:
            return visited

        stack: deque[Tuple[int, int]] = deque([(sx, sy)])
        while stack:
            px, py = stack.pop()
            if px < 0 or py < 0 or px >= w or py >= h:
                continue
            if visited[py, px] or not match[py, px]:
                continue
            visited[py, px] = True
            stack.extend(((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)))
        return visited

    def _to_canvas_mask(self, visited: np.ndarray, layer: Layer) -> Image.Image:
        ox, oy             = layer.offset
        canvas_w, canvas_h = self._canvas_size(layer)
        canvas_mask        = Image.new("L", (canvas_w, canvas_h), 0)
        layer_mask         = Image.fromarray((visited * 255).astype(np.uint8), mode="L")
        canvas_mask.paste(layer_mask, (ox, oy))
        return canvas_mask

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _to_layer_coords(layer: Layer, x: int, y: int) -> Tuple[int, int]:
        ox, oy = layer.offset
        return x - ox, y - oy

    @staticmethod
    def _in_bounds(layer: Layer, lx: int, ly: int) -> bool:
        return 0 <= lx < layer.image.width and 0 <= ly < layer.image.height

    def _notify_commit(self, action_name: str) -> None:
        ca = getattr(self.ctx, "commit_action", None)
        if callable(ca):
            ca(action_name)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def build_ui(self, parent: QWidget, ctx: object) -> QToolButton:
        btn = QToolButton(parent)
        btn.setText("Tolerance")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(110)
        btn.setToolTip(
            "Magic Wand — adjust selection tolerance\n"
            "Right-click drag to move selection without re-sampling"
        )

        menu      = QMenu(btn)
        container = QWidget(menu)
        layout    = QHBoxLayout(container)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        label = QLabel("Tolerance")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        current_val = int(getattr(ctx, "fill_tolerance", _DEFAULT_TOLERANCE))
        slider = SliderField(_MIN_TOLERANCE, _MAX_TOLERANCE, current_val, slider_width=180)

        layout.addWidget(label)
        layout.addWidget(slider)

        debounce = QTimer(container)
        debounce.setSingleShot(True)
        debounce.setInterval(_DEBOUNCE_MS)

        def _safe_reapply() -> None:
            try:
                self.reapply()
            except Exception as exc:
                print(f"[MagicWand] reapply failed: {exc}")

        debounce.timeout.connect(_safe_reapply)

        def _on_slider_change(value: int) -> None:
            ctx.fill_tolerance = value
            on_change = getattr(ctx, "on_tolerance_changed", None)
            if callable(on_change):
                on_change()
            debounce.start()

        slider.valueChanged.connect(_on_slider_change)

        action = QWidgetAction(menu)
        action.setDefaultWidget(container)
        menu.addAction(action)
        btn.setMenu(menu)

        return btn


TOOL_CLASS = MagicWandTool