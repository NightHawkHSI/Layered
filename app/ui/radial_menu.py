"""radial_menu.py — Modern radial (pie) popup menu for PyQt6.

A lightweight cursor-anchored radial command menu designed for fast
tool/action selection without interrupting workflow focus.

Features
────────
• Smooth hover highlighting
• Crisp anti-aliased rendering
• Center cancel zone
• Escape / outside-click dismiss
• Popup-style transient behavior
• Angle-correct hit testing
• Adaptive text layout
• Animated hover transitions
• Keyboard navigation
• Optional center text
• Shadow/glow rendering
• DPI-friendly sizing

Signals
───────
chosen(int)
    Emitted with the selected wedge index.
"""

from __future__ import annotations

import math
from typing import Optional

from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QPointF,
    QRectF,
    QPropertyAnimation,
    Qt,
    pyqtProperty,
    pyqtSignal,
)

from PyQt6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
)

from PyQt6.QtWidgets import QWidget


class RadialMenu(QWidget):
    """Cursor-anchored radial popup menu."""

    chosen = pyqtSignal(int)

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    OUTER_RADIUS = 150
    INNER_RADIUS = 48
    PADDING = 32

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    BACKGROUND_COLOR = QColor(38, 42, 54, 235)
    HOVER_COLOR = QColor(75, 155, 255, 245)

    BORDER_COLOR = QColor(255, 255, 255, 170)
    HOVER_BORDER_COLOR = QColor(255, 255, 255, 240)

    TEXT_COLOR = QColor(245, 245, 245)

    CENTER_BG = QColor(18, 20, 26, 240)
    CENTER_BORDER = QColor(200, 200, 200, 180)

    SHADOW_COLOR = QColor(0, 0, 0, 110)

    FONT = QFont("Segoe UI", 9)

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def __init__(
        self,
        labels: list[str],
        parent: Optional[QWidget] = None,
        center_text: str = "Esc",
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Popup
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )

        self.labels = labels
        self.center_text = center_text

        self.hover_index = -1
        self.keyboard_index = 0

        self._hover_strength = 0.0

        side = (self.OUTER_RADIUS + self.PADDING) * 2
        self.resize(side, side)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )

        # Hover animation
        self.hover_anim = QPropertyAnimation(
            self,
            b"hover_strength",
        )

        self.hover_anim.setDuration(120)
        self.hover_anim.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )

    # ------------------------------------------------------------------
    # Animated property
    # ------------------------------------------------------------------

    def get_hover_strength(self) -> float:
        return self._hover_strength

    def set_hover_strength(self, value: float) -> None:
        self._hover_strength = value
        self.update()

    hover_strength = pyqtProperty(
        float,
        get_hover_strength,
        set_hover_strength,
    )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def show_at(self, global_pos: QPoint) -> None:
        """Show menu centered at a global screen position."""
        center = self.rect().center()

        self.move(
            global_pos.x() - center.x(),
            global_pos.y() - center.y(),
        )

        self.show()
        self.raise_()
        self.activateWindow()
        self.setFocus(
            Qt.FocusReason.PopupFocusReason
        )

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @property
    def center(self) -> tuple[float, float]:
        return (
            self.width() / 2.0,
            self.height() / 2.0,
        )

    @property
    def segment_count(self) -> int:
        return max(1, len(self.labels))

    @property
    def segment_angle(self) -> float:
        return 360.0 / self.segment_count

    # ------------------------------------------------------------------
    # Hit testing
    # ------------------------------------------------------------------

    def _angle_index(
        self,
        x: float,
        y: float,
    ) -> int:
        """Return wedge index under cursor or -1."""
        cx, cy = self.center

        dx = x - cx
        dy = y - cy

        radius = math.hypot(dx, dy)

        if (
            radius < self.INNER_RADIUS
            or radius > self.OUTER_RADIUS
        ):
            return -1

        # 0° = top
        # clockwise positive
        angle = math.degrees(
            math.atan2(dx, -dy)
        ) % 360.0

        return int(angle / self.segment_angle)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event):  # noqa: N802
        index = self._angle_index(
            event.position().x(),
            event.position().y(),
        )

        if index != self.hover_index:
            self.hover_index = index

            self.hover_anim.stop()
            self.hover_anim.setStartValue(
                self._hover_strength
            )
            self.hover_anim.setEndValue(
                1.0 if index >= 0 else 0.0
            )
            self.hover_anim.start()

            self.update()

    def leaveEvent(self, _event):  # noqa: N802
        self.hover_index = -1

        self.hover_anim.stop()
        self.hover_anim.setStartValue(
            self._hover_strength
        )
        self.hover_anim.setEndValue(0.0)
        self.hover_anim.start()

    def mousePressEvent(self, event):  # noqa: N802
        if (
            event.button()
            != Qt.MouseButton.LeftButton
        ):
            self.close()
            return

        index = self._angle_index(
            event.position().x(),
            event.position().y(),
        )

        if index >= 0:
            self.chosen.emit(index)

        self.close()

    def keyPressEvent(self, event):  # noqa: N802
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.close()
            return

        if not self.labels:
            return

        if key in (
            Qt.Key.Key_Right,
            Qt.Key.Key_Down,
        ):
            self.keyboard_index = (
                self.keyboard_index + 1
            ) % len(self.labels)

            self.hover_index = self.keyboard_index
            self.update()
            return

        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Up,
        ):
            self.keyboard_index = (
                self.keyboard_index - 1
            ) % len(self.labels)

            self.hover_index = self.keyboard_index
            self.update()
            return

        if key in (
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
            Qt.Key.Key_Space,
        ):
            self.chosen.emit(
                self.keyboard_index
            )

            self.close()
            return

        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

    def paintEvent(self, _event):  # noqa: N802
        if not self.labels:
            return

        painter = QPainter(self)

        # Important:
        # Explicit transparent clear avoids
        # edge artefacts on Windows.
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_Source
        )

        painter.fillRect(
            self.rect(),
            Qt.GlobalColor.transparent,
        )

        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceOver
        )

        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing
        )

        painter.setFont(self.FONT)

        cx, cy = self.center

        outer_rect = QRectF(
            cx - self.OUTER_RADIUS,
            cy - self.OUTER_RADIUS,
            self.OUTER_RADIUS * 2,
            self.OUTER_RADIUS * 2,
        )

        inner_rect = QRectF(
            cx - self.INNER_RADIUS,
            cy - self.INNER_RADIUS,
            self.INNER_RADIUS * 2,
            self.INNER_RADIUS * 2,
        )

        # --------------------------------------------------------------
        # Shadow
        # --------------------------------------------------------------

        shadow_rect = outer_rect.adjusted(
            4,
            4,
            4,
            4,
        )

        painter.setBrush(self.SHADOW_COLOR)
        painter.setPen(Qt.PenStyle.NoPen)

        painter.drawEllipse(shadow_rect)

        # --------------------------------------------------------------
        # Draw wedges
        # --------------------------------------------------------------

        for index, label in enumerate(
            self.labels
        ):
            start_deg = (
                90.0
                - (index * self.segment_angle)
            )

            path = QPainterPath()

            path.arcMoveTo(
                outer_rect,
                start_deg,
            )

            path.arcTo(
                outer_rect,
                start_deg,
                -self.segment_angle,
            )

            path.arcTo(
                inner_rect,
                start_deg - self.segment_angle,
                self.segment_angle,
            )

            path.closeSubpath()

            hovered = (
                index == self.hover_index
            )

            # Slight scale boost
            wedge_outer = self.OUTER_RADIUS

            if hovered:
                wedge_outer += (
                    5 * self._hover_strength
                )

            wedge_rect = QRectF(
                cx - wedge_outer,
                cy - wedge_outer,
                wedge_outer * 2,
                wedge_outer * 2,
            )

            if hovered:
                hover_path = QPainterPath()

                hover_path.arcMoveTo(
                    wedge_rect,
                    start_deg,
                )

                hover_path.arcTo(
                    wedge_rect,
                    start_deg,
                    -self.segment_angle,
                )

                hover_path.arcTo(
                    inner_rect,
                    start_deg - self.segment_angle,
                    self.segment_angle,
                )

                hover_path.closeSubpath()

                path = hover_path

            painter.setBrush(
                self.HOVER_COLOR
                if hovered
                else self.BACKGROUND_COLOR
            )

            painter.setPen(
                QPen(
                    self.HOVER_BORDER_COLOR
                    if hovered
                    else self.BORDER_COLOR,
                    1.6,
                )
            )

            painter.drawPath(path)

            self._draw_label(
                painter,
                label,
                start_deg,
                self.segment_angle,
                cx,
                cy,
                hovered,
            )

        # --------------------------------------------------------------
        # Center disc
        # --------------------------------------------------------------

        painter.setBrush(self.CENTER_BG)

        painter.setPen(
            QPen(
                self.CENTER_BORDER,
                1.2,
            )
        )

        painter.drawEllipse(
            QPointF(cx, cy),
            self.INNER_RADIUS - 2,
            self.INNER_RADIUS - 2,
        )

        painter.setPen(self.TEXT_COLOR)

        painter.drawText(
            QRectF(
                cx - self.INNER_RADIUS,
                cy - 10,
                self.INNER_RADIUS * 2,
                20,
            ),
            Qt.AlignmentFlag.AlignCenter,
            self.center_text,
        )

    # ------------------------------------------------------------------
    # Label rendering
    # ------------------------------------------------------------------

    def _draw_label(
        self,
        painter: QPainter,
        text: str,
        start_deg: float,
        segment_angle: float,
        cx: float,
        cy: float,
        hovered: bool,
    ) -> None:
        """Draw wedge label."""
        mid_deg = (
            start_deg - segment_angle / 2.0
        )

        radius = (
            self.OUTER_RADIUS
            + self.INNER_RADIUS
        ) / 2.0

        if hovered:
            radius += (
                4 * self._hover_strength
            )

        x = cx + radius * math.cos(
            math.radians(mid_deg)
        )

        y = cy - radius * math.sin(
            math.radians(mid_deg)
        )

        font = QFont(self.FONT)

        if hovered:
            font.setBold(True)

        painter.setFont(font)

        metrics = QFontMetrics(font)

        max_width = max(
            100,
            int(segment_angle * 1.8),
        )

        bounds = metrics.boundingRect(
            QRectF(
                0,
                0,
                max_width,
                64,
            ).toRect(),
            Qt.TextFlag.TextWordWrap,
            text,
        )

        rect = QRectF(
            x - bounds.width() / 2 - 8,
            y - bounds.height() / 2 - 4,
            bounds.width() + 16,
            bounds.height() + 8,
        )

        painter.setPen(self.TEXT_COLOR)

        painter.drawText(
            rect,
            Qt.AlignmentFlag.AlignCenter
            | Qt.TextFlag.TextWordWrap,
            text,
        )


# ----------------------------------------------------------------------
# Standalone test
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from PyQt6.QtGui import QCursor
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    menu = RadialMenu(
        [
            "Brush Tool",
            "Eraser",
            "Fill Bucket",
            "Magic Wand",
            "Move Layer",
            "Crop Tool",
            "Gradient",
            "Settings",
        ]
    )

    menu.chosen.connect(
        lambda i: print(
            f"Selected: {i} -> {menu.labels[i]}"
        )
    )

    menu.show_at(QCursor.pos())

    sys.exit(app.exec())