"""Startup splash screen with stylized layered art, glow, and animated progress."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QRect, QRectF, QPointF, QTimer
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
    QRegion,
)
from PyQt6.QtWidgets import QSplashScreen, QWidget

from app import __version__ as APP_VERSION


_WIDTH = 560
_HEIGHT = 340
_RADIUS = 16
_ICON_SIZE = 112
_ICON_TOP = 44
_BAR_HEIGHT = 10
_BAR_MARGIN_X = 44
_BAR_MARGIN_BOTTOM = 64

_BG_TOP = QColor(14, 18, 46)
_BG_MID = QColor(36, 22, 78)
_BG_BOTTOM = QColor(18, 78, 110)
_RIBBON_A = QColor(120, 90, 220, 70)
_RIBBON_B = QColor(80, 200, 230, 55)
_RIBBON_C = QColor(255, 120, 180, 40)
_GLOW_INNER = QColor(255, 255, 255, 110)
_GLOW_OUTER = QColor(180, 220, 255, 0)
_BAR_BG = QColor(255, 255, 255, 38)
_BAR_STROKE = QColor(255, 255, 255, 60)
_BAR_FG_A = QColor(140, 220, 255)
_BAR_FG_B = QColor(220, 160, 255)
_SHIMMER = QColor(255, 255, 255, 90)
_TEXT = QColor(245, 250, 255)
_SUBTEXT = QColor(200, 215, 240, 220)
_MUTED = QColor(180, 195, 225, 170)
_BORDER = QColor(255, 255, 255, 45)


def _build_base_pixmap() -> QPixmap:
    pm = QPixmap(_WIDTH, _HEIGHT)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0, 0, _WIDTH, _HEIGHT), _RADIUS, _RADIUS)
    p.setClipPath(clip)

    grad = QLinearGradient(0, 0, _WIDTH, _HEIGHT)
    grad.setColorAt(0.0, _BG_TOP)
    grad.setColorAt(0.55, _BG_MID)
    grad.setColorAt(1.0, _BG_BOTTOM)
    p.fillRect(0, 0, _WIDTH, _HEIGHT, grad)

    radial = QRadialGradient(QPointF(_WIDTH * 0.78, _HEIGHT * 0.15), _WIDTH * 0.6)
    radial.setColorAt(0.0, QColor(255, 200, 240, 70))
    radial.setColorAt(1.0, QColor(255, 200, 240, 0))
    p.fillRect(0, 0, _WIDTH, _HEIGHT, QBrush(radial))

    p.setPen(Qt.PenStyle.NoPen)
    for i, color in enumerate((_RIBBON_C, _RIBBON_B, _RIBBON_A)):
        path = QPainterPath()
        offset = i * 28
        path.moveTo(-40, _HEIGHT - 110 + offset)
        path.cubicTo(
            _WIDTH * 0.3, _HEIGHT - 200 + offset,
            _WIDTH * 0.6, _HEIGHT - 40 + offset,
            _WIDTH + 40, _HEIGHT - 90 + offset,
        )
        path.lineTo(_WIDTH + 40, _HEIGHT + 40)
        path.lineTo(-40, _HEIGHT + 40)
        path.closeSubpath()
        p.fillPath(path, color)

    p.setPen(QPen(_BORDER, 1))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(0.5, 0.5, _WIDTH - 1, _HEIGHT - 1), _RADIUS, _RADIUS)

    p.end()
    return pm


class SplashScreen(QSplashScreen):
    def __init__(self, icon_png: Optional[Path] = None) -> None:
        super().__init__(_build_base_pixmap(), Qt.WindowType.WindowStaysOnTopHint)
        self.setFixedSize(_WIDTH, _HEIGHT)
        mask_path = QPainterPath()
        mask_path.addRoundedRect(QRectF(0, 0, _WIDTH, _HEIGHT), _RADIUS, _RADIUS)
        self.setMask(QRegion(mask_path.toFillPolygon().toPolygon()))

        self._progress: int = 0
        self._message: str = ""
        self._anim: float = 0.0
        self._icon: Optional[QPixmap] = None
        if icon_png is not None and Path(icon_png).exists():
            raw = QPixmap(str(icon_png))
            if not raw.isNull():
                self._icon = raw.scaled(
                    _ICON_SIZE,
                    _ICON_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self) -> None:
        self._anim = (self._anim + 0.04) % (2 * math.pi)
        self.repaint()

    def set_progress(self, percent: int, message: str = "") -> None:
        self._progress = max(0, min(100, int(percent)))
        if message:
            self._message = message
        self.repaint()
        from PyQt6.QtWidgets import QApplication
        QApplication.processEvents()

    def drawContents(self, painter: QPainter) -> None:  # type: ignore[override]
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        icon_cx = _WIDTH // 2
        icon_cy = _ICON_TOP + _ICON_SIZE // 2
        halo = QRadialGradient(QPointF(icon_cx, icon_cy), _ICON_SIZE)
        halo.setColorAt(0.0, _GLOW_INNER)
        halo.setColorAt(1.0, _GLOW_OUTER)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(halo))
        painter.drawEllipse(QPointF(icon_cx, icon_cy), _ICON_SIZE * 0.95, _ICON_SIZE * 0.95)

        if self._icon is not None:
            x = (_WIDTH - self._icon.width()) // 2
            y = _ICON_TOP + (_ICON_SIZE - self._icon.height()) // 2
            painter.drawPixmap(x, y, self._icon)

        title_y = _ICON_TOP + _ICON_SIZE + 12
        title_font = QFont()
        title_font.setFamily("Segoe UI")
        title_font.setPointSize(28)
        title_font.setBold(True)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 102)
        painter.setFont(title_font)

        shadow_rect = QRect(0, title_y + 2, _WIDTH, 40)
        painter.setPen(QColor(0, 0, 0, 130))
        painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, "Layered")

        title_rect = QRect(0, title_y, _WIDTH, 40)
        painter.setPen(_TEXT)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, "Layered")

        sub_font = QFont()
        sub_font.setFamily("Segoe UI")
        sub_font.setPointSize(10)
        sub_font.setItalic(True)
        sub_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 110)
        painter.setFont(sub_font)
        painter.setPen(_SUBTEXT)
        sub_rect = QRect(0, title_y + 42, _WIDTH, 18)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter, "Painting & Animation Studio")

        ver_font = QFont()
        ver_font.setFamily("Consolas")
        ver_font.setPointSize(8)
        painter.setFont(ver_font)
        painter.setPen(_MUTED)
        ver_rect = QRect(0, _HEIGHT - 22, _WIDTH - 14, 16)
        painter.drawText(ver_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"v{APP_VERSION}")

        bar_y = _HEIGHT - _BAR_MARGIN_BOTTOM
        bar_w = _WIDTH - 2 * _BAR_MARGIN_X
        bar_rect = QRectF(_BAR_MARGIN_X, bar_y, bar_w, _BAR_HEIGHT)

        painter.setPen(QPen(_BAR_STROKE, 1))
        painter.setBrush(_BAR_BG)
        painter.drawRoundedRect(bar_rect, _BAR_HEIGHT / 2, _BAR_HEIGHT / 2)

        fill_w = bar_w * (self._progress / 100.0)
        if fill_w > 0:
            fill_rect = QRectF(_BAR_MARGIN_X, bar_y, fill_w, _BAR_HEIGHT)
            fg_grad = QLinearGradient(_BAR_MARGIN_X, 0, _BAR_MARGIN_X + bar_w, 0)
            fg_grad.setColorAt(0.0, _BAR_FG_A)
            fg_grad.setColorAt(1.0, _BAR_FG_B)
            clip = QPainterPath()
            clip.addRoundedRect(bar_rect, _BAR_HEIGHT / 2, _BAR_HEIGHT / 2)
            painter.save()
            painter.setClipPath(clip)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(fg_grad))
            painter.drawRect(fill_rect)

            shimmer_x = _BAR_MARGIN_X + (fill_w + 60) * ((self._anim / (2 * math.pi))) - 60
            shimmer_grad = QLinearGradient(shimmer_x, 0, shimmer_x + 60, 0)
            shimmer_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
            shimmer_grad.setColorAt(0.5, _SHIMMER)
            shimmer_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            painter.setBrush(QBrush(shimmer_grad))
            painter.drawRect(QRectF(shimmer_x, bar_y, 60, _BAR_HEIGHT))
            painter.restore()

        msg_font = QFont()
        msg_font.setFamily("Segoe UI")
        msg_font.setPointSize(9)
        painter.setFont(msg_font)

        dot_y = bar_y + _BAR_HEIGHT + 14
        dot_x = _BAR_MARGIN_X + 4
        for i in range(3):
            phase = self._anim + i * (math.pi / 3)
            alpha = int(80 + 140 * (0.5 + 0.5 * math.sin(phase)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(180, 220, 255, alpha))
            painter.drawEllipse(QPointF(dot_x + i * 9, dot_y + 4), 2.6, 2.6)

        text_left = dot_x + 3 * 9 + 8
        msg_rect = QRect(text_left, dot_y - 4, _WIDTH - text_left - _BAR_MARGIN_X - 40, 18)
        painter.setPen(_TEXT)
        painter.drawText(msg_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self._message or "Loading...")

        pct_rect = QRect(_WIDTH - _BAR_MARGIN_X - 40, dot_y - 4, 40, 18)
        pct_font = QFont()
        pct_font.setFamily("Consolas")
        pct_font.setPointSize(9)
        pct_font.setBold(True)
        painter.setFont(pct_font)
        painter.setPen(_SUBTEXT)
        painter.drawText(pct_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         f"{self._progress:>3d}%")

    def finish(self, window: QWidget) -> None:  # type: ignore[override]
        if self._timer.isActive():
            self._timer.stop()
        super().finish(window)
