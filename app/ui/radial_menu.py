"""Radial (pie) menu popup.

Used for cursor-anchored multi-choice prompts where a modal dialog would
break flow. Each label is a wedge in a ring; hover highlights the wedge,
click emits `chosen(int)`. Esc or click outside closes without firing.
"""
from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PyQt6.QtWidgets import QWidget


class RadialMenu(QWidget):
    chosen = pyqtSignal(int)

    OUTER = 150
    INNER = 42

    def __init__(self, labels: list[str], parent: Optional[QWidget] = None):
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.labels = labels
        self.hover = -1
        side = (self.OUTER + 24) * 2
        self.resize(side, side)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        # Auto-emit -1 / close on focus loss handled by Popup window flag.

    # --- public ---

    def show_at(self, global_pos: QPoint) -> None:
        c = self.rect().center()
        self.move(global_pos.x() - c.x(), global_pos.y() - c.y())
        self.show()
        self.activateWindow()
        self.setFocus(Qt.FocusReason.PopupFocusReason)

    # --- hit test ---

    def _angle_index(self, x: float, y: float) -> int:
        cx, cy = self.width() / 2.0, self.height() / 2.0
        dx, dy = x - cx, y - cy
        r = math.hypot(dx, dy)
        if r < self.INNER or r > self.OUTER:
            return -1
        # Angle 0 at 12 o'clock, clockwise.
        a = math.degrees(math.atan2(dx, -dy)) % 360.0
        n = max(1, len(self.labels))
        seg = 360.0 / n
        return int(a / seg) % n

    # --- events ---

    def mouseMoveEvent(self, e):  # noqa: N802
        idx = self._angle_index(e.position().x(), e.position().y())
        if idx != self.hover:
            self.hover = idx
            self.update()

    def mousePressEvent(self, e):  # noqa: N802
        idx = self._angle_index(e.position().x(), e.position().y())
        if idx >= 0:
            self.chosen.emit(idx)
        self.close()

    def keyPressEvent(self, e):  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(e)

    def paintEvent(self, _e):  # noqa: N802
        p = QPainter(self)
        # Explicitly clear the back buffer to fully-transparent before
        # drawing — without this, a translucent frameless popup on
        # Windows can leave previous-frame artefacts along the right
        # and bottom edges (the Qt buffer is allocated with WA_TR but
        # not auto-cleared each repaint).
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2.0, self.height() / 2.0
        n = len(self.labels)
        if n == 0:
            return
        seg = 360.0 / n
        outer_rect = QRectF(cx - self.OUTER, cy - self.OUTER,
                            self.OUTER * 2, self.OUTER * 2)
        inner_rect = QRectF(cx - self.INNER, cy - self.INNER,
                            self.INNER * 2, self.INNER * 2)
        for i in range(n):
            # Each wedge spans `seg` degrees clockwise starting at top.
            start_deg = 90.0 - i * seg  # Qt: 0 at 3 o'clock, ccw; here start
            path = QPainterPath()
            path.arcMoveTo(outer_rect, start_deg)
            path.arcTo(outer_rect, start_deg, -seg)
            path.arcTo(inner_rect, start_deg - seg, seg)
            path.closeSubpath()
            fill = QColor(64, 132, 200, 235) if i == self.hover else QColor(40, 44, 56, 230)
            p.setBrush(fill)
            p.setPen(QPen(QColor(255, 255, 255, 200), 1.4))
            p.drawPath(path)

            mid_deg = start_deg - seg / 2.0
            lr = (self.OUTER + self.INNER) / 2.0
            lx = cx + lr * math.cos(math.radians(mid_deg))
            ly = cy - lr * math.sin(math.radians(mid_deg))
            p.setPen(QColor(255, 255, 255))
            p.setFont(QFont("Arial", 9))
            label_rect = QRectF(lx - 80, ly - 18, 160, 36)
            p.drawText(label_rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self.labels[i])

        # Center disc cancel hint.
        p.setBrush(QColor(20, 22, 28, 230))
        p.setPen(QPen(QColor(180, 180, 180, 200), 1))
        p.drawEllipse(QPointF(cx, cy), self.INNER - 2, self.INNER - 2)
        p.setPen(QColor(220, 220, 220))
        p.drawText(QRectF(cx - self.INNER, cy - 8, self.INNER * 2, 16),
                   Qt.AlignmentFlag.AlignCenter, "Esc")
