"""Interactive canvas widget.

Renders the composited layer stack as a pixmap and forwards mouse events to
the active tool. The canvas auto-fits zoom on resize, accepts dropped images,
and only routes left-button presses to drawing tools (right-click is reserved
for future context menus).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from PIL.ImageQt import ImageQt
from PyQt6.QtCore import QLineF, QPoint, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from .layer import LayerStack
from .tools import Tool


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp", ".dds"}


class Canvas(QWidget):
    """Bitmap canvas with pluggable active tool."""

    layer_changed = pyqtSignal()
    action_committed = pyqtSignal(str)  # tool/action label, emitted at end of a discrete user action
    images_dropped = pyqtSignal(list)  # list[Path]

    def __init__(self, layer_stack: LayerStack, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(400, 300)
        self.setAcceptDrops(True)
        self.layer_stack = layer_stack
        self.tool: Optional[Tool] = None
        self.zoom: float = 1.0
        self._auto_fit = True
        self._pan = QPoint(0, 0)
        self._cached_pixmap: Optional[QPixmap] = None
        self._dirty = True
        self._panning = False
        self.selection_provider = None  # callable -> Optional[Selection]
        # Cache of canvas-space selection edge segments keyed by the
        # mask object id + size, so repaint doesn't re-scan the whole
        # mask every frame. Each entry is a list of (x0, y0, x1, y1)
        # in canvas pixel coords representing a single 1-px edge.
        self._sel_edge_cache: tuple[Optional[int], Optional[tuple[int, int]], list[tuple[int, int, int, int]]] = (None, None, [])
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    # --- public API ---

    def set_layer_stack(self, stack: LayerStack) -> None:
        self.layer_stack = stack
        self._auto_fit = True
        self._pan = QPoint(0, 0)
        self.refresh()

    def set_tool(self, tool: Optional[Tool]) -> None:
        self.tool = tool

    def refresh(self) -> None:
        self._dirty = True
        self.update()

    def fit_to_window(self) -> None:
        self._auto_fit = True
        self._compute_fit_zoom()
        self._pan = QPoint(0, 0)
        self.update()

    def width(self) -> int:  # type: ignore[override]
        return self.layer_stack.width

    def height(self) -> int:  # type: ignore[override]
        return self.layer_stack.height

    # --- rendering ---

    def _compute_fit_zoom(self) -> None:
        if self.layer_stack.width <= 0 or self.layer_stack.height <= 0:
            return
        margin = 32
        avail_w = max(super().width() - margin, 1)
        avail_h = max(super().height() - margin, 1)
        zx = avail_w / self.layer_stack.width
        zy = avail_h / self.layer_stack.height
        self.zoom = max(0.05, min(zx, zy))

    def _composite_pixmap(self) -> QPixmap:
        if not self._dirty and self._cached_pixmap is not None:
            return self._cached_pixmap
        composite = self.layer_stack.composite()
        qimg = ImageQt(composite).copy()
        self._cached_pixmap = QPixmap.fromImage(QImage(qimg))
        self._dirty = False
        return self._cached_pixmap

    def resizeEvent(self, e):  # noqa: N802
        if self._auto_fit:
            self._compute_fit_zoom()
        super().resizeEvent(e)

    def paintEvent(self, _event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(40, 40, 44))
        pixmap = self._composite_pixmap()

        scaled_w = int(self.layer_stack.width * self.zoom)
        scaled_h = int(self.layer_stack.height * self.zoom)
        x = (super().width() - scaled_w) // 2 + self._pan.x()
        y = (super().height() - scaled_h) // 2 + self._pan.y()
        target = QRectF(x, y, scaled_w, scaled_h)

        cb = 16
        painter.save()
        painter.setClipRect(target)
        for cy in range(int(target.top()), int(target.bottom()) + cb, cb):
            for cx in range(int(target.left()), int(target.right()) + cb, cb):
                color = QColor(60, 60, 60) if ((cx // cb + cy // cb) % 2) else QColor(80, 80, 80)
                painter.fillRect(cx, cy, cb, cb, color)
        painter.restore()

        painter.drawPixmap(target, pixmap, QRectF(pixmap.rect()))

        painter.setPen(QPen(QColor(0, 0, 0, 200), 1))
        painter.drawRect(target)

        # Selection outline — traces the actual mask boundary, so a
        # circular magic-wand selection paints a circle of marching
        # ants instead of the bbox rectangle.
        if self.selection_provider is not None:
            try:
                sel = self.selection_provider()
            except Exception:
                sel = None
            if sel is not None and getattr(sel, "mask", None) is not None:
                segs = self._selection_edges(sel.mask)
                if segs:
                    pen = QPen(QColor(255, 255, 255, 220), 1, Qt.PenStyle.DashLine)
                    pen.setCosmetic(True)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    lines: list[QLineF] = []
                    for x0c, y0c, x1c, y1c in segs:
                        sx0, sy0 = self.canvas_to_screen(x0c, y0c)
                        sx1, sy1 = self.canvas_to_screen(x1c, y1c)
                        lines.append(QLineF(sx0, sy0, sx1, sy1))
                    painter.drawLines(lines)

        if self.tool is not None and hasattr(self.tool, "paint_overlay"):
            try:
                self.tool.paint_overlay(painter, self)
            except Exception:
                pass

    # --- mouse → tool routing ---

    def _to_canvas_coords(self, pos) -> tuple[int, int]:
        scaled_w = int(self.layer_stack.width * self.zoom)
        scaled_h = int(self.layer_stack.height * self.zoom)
        x0 = (super().width() - scaled_w) // 2 + self._pan.x()
        y0 = (super().height() - scaled_h) // 2 + self._pan.y()
        cx = int((pos.x() - x0) / max(self.zoom, 1e-6))
        cy = int((pos.y() - y0) / max(self.zoom, 1e-6))
        return cx, cy

    def _selection_edges(self, mask) -> list[tuple[int, int, int, int]]:
        """Return canvas-space 1-px edge segments along the mask boundary.

        Vectorised border trace: a pixel contributes a top edge when its
        cell above is unset (or off-image), a bottom edge when the cell
        below is unset, and likewise for left/right. The segments are
        cached per (mask id, size) so panning / zooming doesn't re-scan
        the whole mask each repaint.
        """
        cache_id, cache_size, cache_segs = self._sel_edge_cache
        if cache_id == id(mask) and cache_size == mask.size:
            return cache_segs
        try:
            arr = np.asarray(mask.convert("L") if mask.mode != "L" else mask, dtype=np.uint8) > 0
        except Exception:
            return []
        if not arr.any():
            self._sel_edge_cache = (id(mask), mask.size, [])
            return []
        h, w = arr.shape
        segs: list[tuple[int, int, int, int]] = []
        # Top edges: pixel set, cell above unset → horizontal line at y.
        top = np.zeros_like(arr)
        top[1:, :] = arr[1:, :] & ~arr[:-1, :]
        top[0, :] = arr[0, :]
        ys, xs = np.nonzero(top)
        for x, y in zip(xs.tolist(), ys.tolist()):
            segs.append((x, y, x + 1, y))
        # Bottom edges.
        bot = np.zeros_like(arr)
        bot[:-1, :] = arr[:-1, :] & ~arr[1:, :]
        bot[-1, :] = arr[-1, :]
        ys, xs = np.nonzero(bot)
        for x, y in zip(xs.tolist(), ys.tolist()):
            segs.append((x, y + 1, x + 1, y + 1))
        # Left edges.
        left = np.zeros_like(arr)
        left[:, 1:] = arr[:, 1:] & ~arr[:, :-1]
        left[:, 0] = arr[:, 0]
        ys, xs = np.nonzero(left)
        for x, y in zip(xs.tolist(), ys.tolist()):
            segs.append((x, y, x, y + 1))
        # Right edges.
        right = np.zeros_like(arr)
        right[:, :-1] = arr[:, :-1] & ~arr[:, 1:]
        right[:, -1] = arr[:, -1]
        ys, xs = np.nonzero(right)
        for x, y in zip(xs.tolist(), ys.tolist()):
            segs.append((x + 1, y, x + 1, y + 1))
        self._sel_edge_cache = (id(mask), mask.size, segs)
        return segs

    def canvas_to_screen(self, cx: float, cy: float) -> tuple[float, float]:
        scaled_w = int(self.layer_stack.width * self.zoom)
        scaled_h = int(self.layer_stack.height * self.zoom)
        x0 = (super().width() - scaled_w) // 2 + self._pan.x()
        y0 = (super().height() - scaled_h) // 2 + self._pan.y()
        return x0 + cx * self.zoom, y0 + cy * self.zoom

    def _update_modifiers(self, e) -> None:
        tool = self.tool
        if tool is None:
            return
        ctx = getattr(tool, "ctx", None)
        if ctx is None:
            return
        mods = e.modifiers()
        ctx.shift_held = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        ctx.alt_held = bool(mods & Qt.KeyboardModifier.AltModifier)
        ctx.ctrl_held = bool(mods & Qt.KeyboardModifier.ControlModifier)
        try:
            ctx._canvas_zoom = self.zoom  # transform tool uses to size handles
        except Exception:
            pass

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._drag_origin = e.position().toPoint() - self._pan
            self._auto_fit = False
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return  # ignore right-click and others; tools only fire on left
        if self.tool is None or self.layer_stack.active is None:
            return
        self._update_modifiers(e)
        cx, cy = self._to_canvas_coords(e.position().toPoint())
        self.tool.press(self.layer_stack.active, cx, cy)
        self.refresh()
        self.layer_changed.emit()
        if getattr(self.tool, "commit_on", "release") == "press":
            self.action_committed.emit(self.tool.name)

    def mouseMoveEvent(self, e):  # noqa: N802
        if self._panning:
            self._pan = e.position().toPoint() - self._drag_origin
            self.update()
            return
        if self.tool is None or self.layer_stack.active is None:
            return
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._update_modifiers(e)
            cx, cy = self._to_canvas_coords(e.position().toPoint())
            self.tool.move(self.layer_stack.active, cx, cy)
            self.refresh()
            self.layer_changed.emit()

    def mouseReleaseEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.tool is None or self.layer_stack.active is None:
            return
        self._update_modifiers(e)
        cx, cy = self._to_canvas_coords(e.position().toPoint())
        self.tool.release(self.layer_stack.active, cx, cy)
        self.refresh()
        self.layer_changed.emit()
        if getattr(self.tool, "commit_on", "release") == "release":
            self.action_committed.emit(self.tool.name)

    def wheelEvent(self, e):  # noqa: N802
        delta = e.angleDelta().y()
        mods = e.modifiers()
        step = 40 if delta == 0 else int(delta / 120 * 40)
        if mods & Qt.KeyboardModifier.ShiftModifier:
            # Horizontal pan.
            self._pan = QPoint(self._pan.x() + step, self._pan.y())
            self._auto_fit = False
            self.update()
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            # Vertical pan.
            self._pan = QPoint(self._pan.x(), self._pan.y() + step)
            self._auto_fit = False
            self.update()
            return
        factor = 1.1 if delta > 0 else (1 / 1.1)
        self.zoom = max(0.05, min(32.0, self.zoom * factor))
        self._auto_fit = False
        self.update()

    # --- drag-drop ---

    def dragEnterEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            urls = [u for u in e.mimeData().urls() if u.isLocalFile()]
            if any(Path(u.toLocalFile()).suffix.lower() in IMAGE_EXTS for u in urls):
                e.acceptProposedAction()
                return
        e.ignore()

    def dragMoveEvent(self, e):  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):  # noqa: N802
        paths: list[Path] = []
        for url in e.mimeData().urls():
            if not url.isLocalFile():
                continue
            p = Path(url.toLocalFile())
            if p.suffix.lower() in IMAGE_EXTS:
                paths.append(p)
        if paths:
            e.acceptProposedAction()
            self.images_dropped.emit(paths)
        else:
            e.ignore()
