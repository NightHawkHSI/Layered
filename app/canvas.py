"""Interactive canvas widget.

Renders the composited layer stack as a pixmap and forwards mouse events to
the active tool. The canvas auto-fits zoom on resize, accepts dropped images,
and only routes left-button presses to drawing tools (right-click is reserved
for future context menus).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL.ImageQt import ImageQt
from PyQt6.QtCore import QPoint, QRectF, Qt, pyqtSignal
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

    # --- mouse → tool routing ---

    def _to_canvas_coords(self, pos) -> tuple[int, int]:
        scaled_w = int(self.layer_stack.width * self.zoom)
        scaled_h = int(self.layer_stack.height * self.zoom)
        x0 = (super().width() - scaled_w) // 2 + self._pan.x()
        y0 = (super().height() - scaled_h) // 2 + self._pan.y()
        cx = int((pos.x() - x0) / max(self.zoom, 1e-6))
        cy = int((pos.y() - y0) / max(self.zoom, 1e-6))
        return cx, cy

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
        cx, cy = self._to_canvas_coords(e.position().toPoint())
        self.tool.release(self.layer_stack.active, cx, cy)
        self.refresh()
        self.layer_changed.emit()
        if getattr(self.tool, "commit_on", "release") == "release":
            self.action_committed.emit(self.tool.name)

    def wheelEvent(self, e):  # noqa: N802
        delta = e.angleDelta().y()
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
