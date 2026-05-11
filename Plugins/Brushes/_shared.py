"""
Shared helpers and base classes for brush and transform plugins.

One-stop import for any brush. Re-exports stdlib, PIL, PyQt6, app.tools
helpers, and SliderField so brush authors only need:

    from Plugins.Brushes._shared import *

This module handles the complex math for:
1. Interactive shape transformation (Move, Scale, Rotate).
2. Pixel-perfect selection lifting and moving.
3. Localized image filtering (blur/sharpen brushes).
"""
from __future__ import annotations

# --- stdlib --------------------------------------------------------------
import colorsys
import enum
import math
import random
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, NamedTuple, Optional, Tuple, TypedDict, Union

# --- PIL -----------------------------------------------------------------
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --- app.* ---------------------------------------------------------------
from app.layer import Layer
from app.tools import (
    Color,
    Tool,
    ToolContext,
    _apply_selection_to_stamp,
    _brush_mask,
    _clip_layer_to_selection,
    _scaled_mask,
    _selection_at_layer,
    _stamp_color,
    _stamp_erase,
    _walk,
    build_brush_settings_ui,
    resolve_font_path,
)
from app.ui.slider_field import SliderField

# --- PyQt6 (safe to import here; brushes load after QApplication exists) -
from PyQt6.QtCore import QLineF, QPoint, QPointF, QRect, QRectF, QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)


def __getattr__(name: str):
    # Lazy numpy import — only pay the cost if a brush actually uses it.
    if name in ("np", "numpy"):
        import numpy as _np
        globals()["np"] = _np
        globals()["numpy"] = _np
        return _np
    raise AttributeError(f"module 'Plugins.Brushes._shared' has no attribute {name!r}")


def _Qt_DashLine():
    from PyQt6.QtCore import Qt
    return Qt.PenStyle.DashLine


def _Qt_NoBrush():
    from PyQt6.QtCore import Qt
    return Qt.BrushStyle.NoBrush


def _right_button_held() -> bool:
    """Return True if the right mouse button is currently pressed.

    Uses Qt's global mouse state so any tool can call this without
    needing a button parameter threaded through press/move/release.
    """
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtCore import Qt
        return bool(QApplication.mouseButtons() & Qt.MouseButton.RightButton)
    except Exception:
        return False


__all__ = [
    # core
    "Tool", "ToolContext", "Layer", "ToolPhase", "Box", "Color",
    "_ShapeTool", "_SelectionToolBase", "_local_filter_stamp",
    # painting helpers
    "_walk", "_stamp_color", "_stamp_erase", "_brush_mask", "_scaled_mask",
    "_selection_at_layer", "_apply_selection_to_stamp",
    "_clip_layer_to_selection",
    # UI helpers
    "build_brush_settings_ui", "SliderField", "resolve_font_path",
    "_Qt_DashLine", "_Qt_NoBrush", "_right_button_held",
    # stdlib re-exports
    "colorsys", "deque", "enum", "math", "random", "sys",
    "dataclass", "Path",
    "Any", "Callable", "NamedTuple", "Optional", "Tuple", "TypedDict", "Union",
    # PIL
    "Image", "ImageChops", "ImageDraw", "ImageFilter", "ImageFont",
    # PyQt6
    "Qt", "QTimer", "QPoint", "QPointF", "QRect", "QRectF", "QLineF",
    "QBrush", "QColor", "QPainter", "QPen", "QPolygonF",
    "QApplication", "QWidget", "QLabel", "QFormLayout", "QGridLayout",
    "QHBoxLayout", "QVBoxLayout", "QSpinBox", "QCheckBox", "QComboBox",
    "QPushButton", "QToolButton", "QMenu", "QWidgetAction",
    # lazy
    "np", "numpy",
]

# ---------------------------------------------------------------------------
# Constants & Enums
# ---------------------------------------------------------------------------

class ToolPhase(enum.Enum):
    IDLE     = 0
    DRAWING  = 1
    EDITING  = 2
    MOVING   = 3
    SCALING  = 4
    ROTATING = 5


# ---------------------------------------------------------------------------
# Box — immutable canvas-space rectangle
# ---------------------------------------------------------------------------

class Box(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def width(self) -> float:
        return abs(self.x1 - self.x0)

    @property
    def height(self) -> float:
        return abs(self.y1 - self.y0)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2

    @property
    def area(self) -> float:
        return self.width * self.height

    @property
    def is_empty(self) -> bool:
        return self.width == 0 or self.height == 0

    # ------------------------------------------------------------------
    # Transforms
    # ------------------------------------------------------------------

    def normalized(self) -> Box:
        """Return a Box where x0 <= x1 and y0 <= y1."""
        return Box(
            min(self.x0, self.x1), min(self.y0, self.y1),
            max(self.x0, self.x1), max(self.y0, self.y1),
        )

    def offset(self, dx: float, dy: float) -> Box:
        """Translate this box by (dx, dy)."""
        return Box(self.x0 + dx, self.y0 + dy, self.x1 + dx, self.y1 + dy)

    def expanded(self, amount: float) -> Box:
        """Expand all edges outward by *amount* pixels."""
        return Box(self.x0 - amount, self.y0 - amount,
                   self.x1 + amount, self.y1 + amount)

    def clamp(self, bounds: Box) -> Box:
        """Clamp this box so it stays inside *bounds*."""
        b = bounds.normalized()
        return Box(
            max(self.x0, b.x0), max(self.y0, b.y0),
            min(self.x1, b.x1), min(self.y1, b.y1),
        )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def contains(self, x: float, y: float) -> bool:
        """Return True if the point (x, y) is inside this (normalised) box."""
        b = self.normalized()
        return b.x0 <= x <= b.x1 and b.y0 <= y <= b.y1

    def intersects(self, other: Box) -> bool:
        """Return True if this box and *other* overlap (touching counts)."""
        a = self.normalized()
        b = other.normalized()
        return a.x0 <= b.x1 and a.x1 >= b.x0 and a.y0 <= b.y1 and a.y1 >= b.y0

    def intersection(self, other: Box) -> Optional[Box]:
        """Return the overlapping region, or None if they don't intersect."""
        a, b = self.normalized(), other.normalized()
        rx0, ry0 = max(a.x0, b.x0), max(a.y0, b.y0)
        rx1, ry1 = min(a.x1, b.x1), min(a.y1, b.y1)
        if rx0 > rx1 or ry0 > ry1:
            return None
        return Box(rx0, ry0, rx1, ry1)

    def union(self, other: Box) -> Box:
        """Return the smallest box that contains both boxes."""
        a, b = self.normalized(), other.normalized()
        return Box(min(a.x0, b.x0), min(a.y0, b.y0),
                   max(a.x1, b.x1), max(a.y1, b.y1))

    def to_int_tuple(self) -> tuple[int, int, int, int]:
        """Return (x0, y0, x1, y1) as integers (floor/ceil for containment)."""
        b = self.normalized()
        return (int(math.floor(b.x0)), int(math.floor(b.y0)),
                int(math.ceil(b.x1)),  int(math.ceil(b.y1)))


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _rotate_pt(
    x: float, y: float,
    cx: float, cy: float,
    angle_deg: float,
) -> tuple[float, float]:
    """Rotate point (x, y) around (cx, cy) by *angle_deg* degrees."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    nx = cx + cos_a * (x - cx) - sin_a * (y - cy)
    ny = cy + sin_a * (x - cx) + cos_a * (y - cy)
    return nx, ny


def _shape_geom(
    origin: tuple[int, int],
    x: int,
    y: int,
    ctx: ToolContext,
) -> Box:
    ox, oy = origin
    if ctx.shift_held:
        dx, dy = x - ox, y - oy
        side = max(abs(dx), abs(dy))
        return Box(
            ox, oy,
            ox + (side if dx >= 0 else -side),
            oy + (side if dy >= 0 else -side),
        )
    return Box(ox, oy, x, y)


def _local_filter_stamp(
    layer: Layer,
    ctx: ToolContext,
    x: int,
    y: int,
    filt: ImageFilter.Filter,
) -> None:
    size = ctx.brush_size
    r = size // 2
    x0, y0 = max(x - r, 0), max(y - r, 0)
    x1 = min(x - r + size, layer.image.width)
    y1 = min(y - r + size, layer.image.height)
    if x1 <= x0 or y1 <= y0:
        return

    region  = layer.image.crop((x0, y0, x1, y1))
    blurred = region.filter(filt)
    mask    = _brush_mask(size, ctx.brush_hardness)
    mx0, my0 = x0 - (x - r), y0 - (y - r)
    sub_mask = mask.crop((mx0, my0, mx0 + (x1 - x0), my0 + (y1 - y0)))

    if ctx.brush_opacity < 1.0:
        sub_mask = sub_mask.point(lambda v: int(v * ctx.brush_opacity))

    sel = _selection_at_layer(ctx, layer)
    if sel:
        sub_mask = ImageChops.multiply(sub_mask, sel.crop((x0, y0, x1, y1)))

    blurred.putalpha(sub_mask)
    layer.image.alpha_composite(blurred, dest=(x0, y0))


# ---------------------------------------------------------------------------
# _ShapeTool
# ---------------------------------------------------------------------------

class _ShapeTool(Tool):
    """Base for shape tools with full Move, Scale, and Rotate support."""

    commit_on    = None
    HANDLE_SIZE  = 10
    ROTATION_OFFSET = 30  # Screen pixels above shape

    def __init__(self, ctx: ToolContext) -> None:
        super().__init__(ctx)
        self._reset_state()

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        self._snapshot:      Optional[Image.Image]        = None
        self._bbox:          Optional[Box]                = None
        self._angle:         float                        = 0.0
        self._phase:         ToolPhase                    = ToolPhase.IDLE
        self._anchor:        Optional[str]                = None
        self._press_pt:      Optional[tuple[float, float]] = None
        self._bbox_at_press: Optional[Box]                = None
        self._angle_at_press: float                       = 0.0

    # ------------------------------------------------------------------
    # Handle geometry
    # ------------------------------------------------------------------

    def _get_handle_positions(self) -> dict[str, tuple[float, float]]:
        if not self._bbox:
            return {}
        b  = self._bbox
        cx, cy = b.center
        zoom = max(0.01, getattr(self.ctx, "_canvas_zoom", 1.0))

        handles = {
            "nw": (b.x0, b.y0), "n": (cx, b.y0), "ne": (b.x1, b.y0),
            "w":  (b.x0,  cy),                    "e":  (b.x1,  cy),
            "sw": (b.x0, b.y1), "s": (cx, b.y1), "se": (b.x1, b.y1),
            "rot": (cx, b.y0 - self.ROTATION_OFFSET / zoom),
        }
        return {
            k: _rotate_pt(v[0], v[1], cx, cy, self._angle)
            for k, v in handles.items()
        }

    def _hit_handle(self, x: float, y: float) -> Optional[str]:
        if not self._bbox:
            return None
        zoom     = max(0.01, getattr(self.ctx, "_canvas_zoom", 1.0))
        hit_r_sq = (self.HANDLE_SIZE / zoom * 1.5) ** 2

        handles = self._get_handle_positions()
        best_name, best_dist = None, float("inf")
        for name, pos in handles.items():
            dist = (x - pos[0]) ** 2 + (y - pos[1]) ** 2
            if dist < hit_r_sq and dist < best_dist:
                best_name, best_dist = name, dist

        if best_name:
            return best_name

        # Body hit: rotate mouse back into local (unrotated) space
        cx, cy = self._bbox.center
        lx, ly = _rotate_pt(x, y, cx, cy, -self._angle)
        b = self._bbox.normalized()
        if b.x0 <= lx <= b.x1 and b.y0 <= ly <= b.y1:
            return "move"
        return None

    # ------------------------------------------------------------------
    # Input handlers
    # ------------------------------------------------------------------

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == ToolPhase.EDITING:
            hit = self._hit_handle(x, y)
            if hit:
                self._anchor         = hit
                self._press_pt       = (float(x), float(y))
                self._bbox_at_press  = self._bbox
                self._angle_at_press = self._angle
                if   hit == "move": self._phase = ToolPhase.MOVING
                elif hit == "rot":  self._phase = ToolPhase.ROTATING
                else:               self._phase = ToolPhase.SCALING
                return
            self._commit_session()

        self._snapshot = layer.image.copy()
        self._bbox     = Box(x, y, x, y)
        self._angle    = 0.0
        self._phase    = ToolPhase.DRAWING
        self._press_pt = (float(x), float(y))

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == ToolPhase.IDLE:
            return
        xf, yf = float(x), float(y)

        if self._phase == ToolPhase.DRAWING:
            self._bbox = Box(self._press_pt[0], self._press_pt[1], xf, yf)

        elif self._phase == ToolPhase.MOVING:
            dx, dy = xf - self._press_pt[0], yf - self._press_pt[1]
            b = self._bbox_at_press
            self._bbox = Box(b.x0 + dx, b.y0 + dy, b.x1 + dx, b.y1 + dy)

        elif self._phase == ToolPhase.ROTATING:
            cx, cy      = self._bbox_at_press.center
            angle_now   = math.degrees(math.atan2(yf - cy, xf - cx))
            angle_press = math.degrees(
                math.atan2(self._press_pt[1] - cy, self._press_pt[0] - cx)
            )
            self._angle = self._angle_at_press + (angle_now - angle_press) + 90

        elif self._phase == ToolPhase.SCALING:
            self._handle_scaling(xf, yf)

        self._render(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._phase in (
            ToolPhase.DRAWING, ToolPhase.MOVING,
            ToolPhase.SCALING, ToolPhase.ROTATING,
        ):
            self._phase = ToolPhase.EDITING
        super().release(layer, x, y)

    def cancel(self) -> None:
        """Abort the current session without committing."""
        self._reset_state()

    # ------------------------------------------------------------------
    # Scaling
    # ------------------------------------------------------------------

    def _handle_scaling(self, x: float, y: float) -> None:
        b  = self._bbox_at_press
        cx, cy = b.center

        lx, ly   = _rotate_pt(x,                  y,                  cx, cy, -self._angle)
        plx, ply = _rotate_pt(self._press_pt[0], self._press_pt[1], cx, cy, -self._angle)
        dx, dy   = lx - plx, ly - ply

        nx0, ny0, nx1, ny1 = b.x0, b.y0, b.x1, b.y1
        if "w" in self._anchor: nx0 += dx
        if "e" in self._anchor: nx1 += dx
        if "n" in self._anchor: ny0 += dy
        if "s" in self._anchor: ny1 += dy

        if self.ctx.shift_held:
            orig_w  = max(1, b.width)
            orig_h  = max(1, b.height)
            new_w   = abs(nx1 - nx0)
            new_h   = abs(ny1 - ny0)
            scale   = max(new_w / orig_w, new_h / orig_h)
            if "e" in self._anchor:   nx1 = nx0 + orig_w * scale
            elif "w" in self._anchor: nx0 = nx1 - orig_w * scale
            if "s" in self._anchor:   ny1 = ny0 + orig_h * scale
            elif "n" in self._anchor: ny0 = ny1 - orig_h * scale

        self._bbox = Box(nx0, ny0, nx1, ny1)

    # ------------------------------------------------------------------
    # Rendering & commit
    # ------------------------------------------------------------------

    def _render(self, layer: Layer) -> None:
        if not self._snapshot or not self._bbox:
            return
        layer.image = self._snapshot.copy()
        self._draw(layer, self._bbox.normalized(), self._angle)
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def _commit_session(self) -> None:
        ca = getattr(self.ctx, "commit_action", None)
        if ca and self._snapshot and self._bbox:
            try:
                ca(self.name)
            except Exception as exc:
                print(f"[{self.__class__.__name__}] commit_action failed: {exc}")
        self._reset_state()

    def commit(self) -> Optional[str]:
        name = self.name if (self._snapshot and self._bbox) else None
        self._reset_state()
        return name

    def paint_overlay(self, painter, canvas) -> None:
        if not self._bbox or self._phase == ToolPhase.IDLE:
            return
        from PyQt6.QtGui import QColor, QPen, QPolygonF
        from PyQt6.QtCore import QPointF

        hpts = self._get_handle_positions()
        scr  = {
            k: QPointF(*canvas.canvas_to_screen(v[0], v[1]))
            for k, v in hpts.items()
        }

        painter.setPen(QPen(QColor(0, 180, 255), 1.5))
        painter.drawPolygon(QPolygonF([scr["nw"], scr["ne"], scr["se"], scr["sw"]]))
        painter.drawLine(scr["n"], scr["rot"])

        painter.setBrush(QColor(255, 255, 255))
        hs = self.HANDLE_SIZE
        for pt in scr.values():
            painter.drawRect(int(pt.x() - hs / 2), int(pt.y() - hs / 2), hs, hs)

    def _draw(self, layer: Layer, bbox: Box, angle: float) -> None:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# _MoveState — typed state bag for _SelectionToolBase drag-move
# ---------------------------------------------------------------------------

class _MoveState(TypedDict):
    anchor:      tuple[int, int]
    current_pos: tuple[int, int]
    has_moved:   bool
    mask:        Image.Image
    layer:       Layer
    lifted:      Image.Image
    base:        Image.Image


# ---------------------------------------------------------------------------
# _SelectionToolBase
# ---------------------------------------------------------------------------

class _SelectionToolBase(Tool):
    """Base for Marquee / Lasso / MagicWand with stable lifting logic.

    Public API for subclasses
    -------------------------
    _begin_move_if_inside(layer, x, y) -> bool
        Call at the top of press().  Returns True if the click landed on
        the current selection and a drag-move was initiated.  The layer's
        pixels are lifted into a floating buffer; the base layer shows the
        "hole" underneath until the move is committed.

    _continue_move(x, y)
        Call inside move() while _move_mode is True.

    _end_move() -> bool
        Call inside release().  Commits the move (or restores the pixels
        unchanged if the mouse never moved).  Returns True if a move was
        active.

    cancel_move()
        Abort a drag-move in progress and restore pixels to their original
        position.  Safe to call even when not moving.

    _move_mode  (bool, read-only)
        True while a drag-move is in progress.

    _canvas_size(layer) -> (w, h)
    _combine_with_current(mask, layer) -> Image  [Shift=add, Alt=subtract]
    _commit_mask(mask)
    """

    commit_on = None

    def __init__(self, ctx: ToolContext) -> None:
        super().__init__(ctx)
        self._moving = False
        self._state: _MoveState = {}          # type: ignore[assignment]

    @property
    def _move_mode(self) -> bool:
        return self._moving

    # ------------------------------------------------------------------
    # Canvas helpers
    # ------------------------------------------------------------------

    def _canvas_size(self, layer: Layer) -> tuple[int, int]:
        getter = getattr(self.ctx, "get_canvas_size", None)
        if getter is not None:
            try:
                size = getter()
                if size is not None:
                    return int(size[0]), int(size[1])
            except Exception:
                pass
        # Fallback: derive from layer position + dimensions
        ox, oy = layer.offset
        return layer.image.width + max(0, ox), layer.image.height + max(0, oy)

    def _current_mask_canvas(self, layer: Layer) -> Optional[Image.Image]:
        if not callable(getattr(self.ctx, "get_selection", None)):
            return None
        sel = self.ctx.get_selection()
        if sel is None or getattr(sel, "mask", None) is None:
            return None
        cw, ch = self._canvas_size(layer)
        m = sel.mask
        if m.size == (cw, ch):
            return m.copy()
        full = Image.new("L", (cw, ch), 0)
        full.paste(m, (0, 0))
        return full

    # ------------------------------------------------------------------
    # Mask operations
    # ------------------------------------------------------------------

    def _combine_with_current(
        self, new_mask: Image.Image, layer: Layer
    ) -> Image.Image:
        """Union (Shift) or subtract (Alt) *new_mask* against the active selection."""
        if not (self.ctx.shift_held or self.ctx.alt_held):
            return new_mask
        current = self._current_mask_canvas(layer)
        if current is None:
            return new_mask
        if current.size != new_mask.size:
            cw, ch  = current.size
            padded  = Image.new("L", (cw, ch), 0)
            padded.paste(new_mask, (0, 0))
            new_mask = padded
        if self.ctx.shift_held:
            return ImageChops.lighter(current, new_mask)
        # Alt — subtract: keep pixels in current that are NOT in new_mask
        inv = new_mask.point(lambda v: 255 - v)
        return ImageChops.multiply(current, inv).point(
            lambda v: 255 if v >= 128 else 0
        )

    def _commit_mask(self, mask: Image.Image) -> None:
        if not callable(getattr(self.ctx, "set_selection", None)):
            return
        from app.project import Selection
        self.ctx.set_selection(Selection.from_mask(mask))

    def _clear_selection(self) -> None:
        """Remove the active selection entirely."""
        if callable(getattr(self.ctx, "set_selection", None)):
            self.ctx.set_selection(None)

    # ------------------------------------------------------------------
    # Drag-move: begin
    # ------------------------------------------------------------------

    def _begin_move_if_inside(self, layer: Layer, x: int, y: int) -> bool:
        """Initiate a drag-move if (x, y) is inside the current selection.

        Returns True and lifts the selected pixels out of the layer.
        Returns False and leaves everything untouched otherwise.
        """
        # Additive-mode clicks should never start a move
        if self.ctx.shift_held or self.ctx.alt_held:
            return False

        sel = (
            self.ctx.get_selection()
            if callable(getattr(self.ctx, "get_selection", None))
            else None
        )
        if not sel or getattr(sel, "mask", None) is None:
            return False

        mw, mh = sel.mask.size
        if not (0 <= x < mw and 0 <= y < mh):
            return False
        if sel.mask.getpixel((x, y)) == 0:
            return False

        # Build a layer-space copy of the selection mask
        ox, oy     = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(sel.mask, (-ox, -oy))

        src           = layer.image.convert("RGBA")
        r, g, b, a   = src.split()
        lift_a        = ImageChops.multiply(a, layer_mask)

        # Nothing visible to lift (fully transparent region)
        if lift_a.getextrema()[1] == 0:
            return False

        base_a = ImageChops.multiply(a, ImageChops.invert(layer_mask))

        self._moving = True
        self._state  = {
            "anchor":      (x, y),
            "current_pos": (x, y),
            "has_moved":   False,
            "mask":        sel.mask.copy(),
            "layer":       layer,
            "lifted":      Image.merge("RGBA", (r, g, b, lift_a)),
            "base":        Image.merge("RGBA", (r, g, b, base_a)),
        }
        # Show the "hole" beneath the lifted pixels
        layer.image = self._state["base"].copy()
        return True

    # ------------------------------------------------------------------
    # Drag-move: update
    # ------------------------------------------------------------------

    def _continue_move(self, x: int, y: int) -> None:
        if not self._moving:
            return
        s  = self._state
        dx = x - s["anchor"][0]
        dy = y - s["anchor"][1]

        s["current_pos"] = (x, y)
        s["has_moved"]   = s["has_moved"] or (dx != 0 or dy != 0)

        # Composite lifted pixels over the base at the new offset
        canvas = s["base"].copy()
        dest_x, dest_y = dx, dy
        canvas.alpha_composite(s["lifted"], dest=(dest_x, dest_y))
        s["layer"].image = canvas

        # Shift the selection mask to follow
        shifted = Image.new("L", s["mask"].size, 0)
        shifted.paste(s["mask"], (dx, dy))

        from app.project import Selection
        bb = shifted.getbbox()
        if callable(getattr(self.ctx, "set_selection", None)):
            self.ctx.set_selection(
                Selection(bbox=bb, mask=shifted) if bb else None
            )

    # ------------------------------------------------------------------
    # Drag-move: end / cancel
    # ------------------------------------------------------------------

    def _end_move(self) -> bool:
        """Commit the drag-move (or restore pixels if nothing moved).

        Returns True if a move was active.
        """
        if not self._moving:
            return False

        s = self._state

        if not s.get("has_moved"):
            # Click-without-drag → put the pixels back exactly where they were
            self._restore_lifted()
        else:
            # Merge the floating layer into the canvas permanently and commit
            ca = getattr(self.ctx, "commit_action", None)
            if callable(ca):
                ca("Move Selection")

        self._moving = False
        self._state  = {}  # type: ignore[assignment]
        return True

    def cancel_move(self) -> None:
        """Abort a drag-move in progress and restore the original pixels."""
        if not self._moving:
            return
        self._restore_lifted()
        self._moving = False
        self._state  = {}  # type: ignore[assignment]

    def _restore_lifted(self) -> None:
        """Put lifted pixels back and restore the original selection mask."""
        if not self._state:
            return
        s = self._state

        # Restore layer pixels
        restored = s["base"].copy()
        restored.alpha_composite(s["lifted"])
        s["layer"].image = restored

        # Restore selection mask
        from app.project import Selection
        mask = s["mask"]
        bb   = mask.getbbox()
        if callable(getattr(self.ctx, "set_selection", None)):
            self.ctx.set_selection(
                Selection(bbox=bb, mask=mask) if bb else None
            )