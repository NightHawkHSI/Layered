import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
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
ImageDraw = _sh.ImageDraw
_SelectionToolBase = _sh._SelectionToolBase
_Qt_DashLine = _sh._Qt_DashLine
_Qt_NoBrush = _sh._Qt_NoBrush


class MarqueeTool(_SelectionToolBase):
    """Drag a rectangular selection."""
    name = "Marquee"

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._begin_move_if_inside(layer, x, y):
            self._origin = None
            self._cur = None
            return
        self._origin = (x, y)
        self._cur = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._move_mode:
            self._continue_move(x, y)
            return
        if getattr(self, "_origin", None) is None:
            return
        self._cur = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._end_move():
            super().release(layer, x, y)
            return
        if getattr(self, "_origin", None) is None:
            return
        ox, oy = self._origin
        x0, x1 = sorted((ox, x)); y0, y1 = sorted((oy, y))
        if x1 - x0 < 2 or y1 - y0 < 2:
            if not (self.ctx.shift_held or self.ctx.alt_held):
                if self.ctx.set_selection is not None:
                    self.ctx.set_selection(None)
        else:
            canvas_w, canvas_h = self._canvas_size(layer)
            new_mask = Image.new("L", (canvas_w, canvas_h), 0)
            ImageDraw.Draw(new_mask).rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
            combined = self._combine_with_current(new_mask, layer)
            self._commit_mask(combined)
        self._origin = None
        self._cur = None
        super().release(layer, x, y)

    def paint_overlay(self, painter, canvas) -> None:
        if getattr(self, "_origin", None) is None or getattr(self, "_cur", None) is None:
            return
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        ox, oy = self._origin
        cx, cy = self._cur
        sx0, sy0 = canvas.canvas_to_screen(ox, oy)
        sx1, sy1 = canvas.canvas_to_screen(cx, cy)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        pen = QPen(QColor(255, 255, 255, 220), 1, _Qt_DashLine())
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(_Qt_NoBrush())
        painter.drawRect(rect)


TOOL_CLASS = MarqueeTool
