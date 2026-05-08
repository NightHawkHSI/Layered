"""
Shared helpers and base classes for brush and transform plugins.

This module handles the complex math for:
1. Interactive shape transformation (Move, Scale, Rotate).
2. Pixel-perfect selection lifting and moving.
3. Localized image filtering (blur/sharpen brushes).
"""
from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from typing import Optional, Any, NamedTuple, Union
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from app.layer import Layer
from app.tools import (
    Tool,
    ToolContext,
    _brush_mask,
    _clip_layer_to_selection,
    _selection_at_layer,
    _stamp_color,
    _stamp_erase,
    _walk,
)

def _Qt_DashLine():
    from PyQt6.QtCore import Qt
    return Qt.PenStyle.DashLine

__all__ = [
    "Tool", "ToolContext", "Layer", "ToolPhase", "Box",
    "_ShapeTool", "_SelectionToolBase", "_local_filter_stamp",
    "_walk", "_stamp_color", "_stamp_erase", "_Qt_DashLine",
]

# --- Constants & Enums ---

class ToolPhase(enum.Enum):
    IDLE = 0
    DRAWING = 1
    EDITING = 2
    MOVING = 3
    SCALING = 4
    ROTATING = 5

class Box(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def width(self) -> float: return abs(self.x1 - self.x0)
    @property
    def height(self) -> float: return abs(self.y1 - self.y0)
    @property
    def center(self) -> tuple[float, float]: 
        return (self.x0 + self.x1) / 2, (self.y0 + self.y1) / 2
    
    def normalized(self) -> Box:
        return Box(min(self.x0, self.x1), min(self.y0, self.y1),
                   max(self.x0, self.x1), max(self.y0, self.y1))

# --- Math Helpers ---

def _rotate_pt(x: float, y: float, cx: float, cy: float, angle_deg: float) -> tuple[float, float]:
    """Rotates a point (x, y) around (cx, cy) by angle_deg."""
    rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    nx = cx + cos_a * (x - cx) - sin_a * (y - cy)
    ny = cy + sin_a * (x - cx) + cos_a * (y - cy)
    return nx, ny

def _shape_geom(origin: tuple[int, int], x: int, y: int, ctx: ToolContext) -> Box:
    ox, oy = origin
    if ctx.shift_held:
        dx, dy = x - ox, y - oy
        side = max(abs(dx), abs(dy))
        return Box(ox, oy, ox + (side if dx >= 0 else -side), oy + (side if dy >= 0 else -side))
    return Box(ox, oy, x, y)

def _local_filter_stamp(layer: Layer, ctx: ToolContext, x: int, y: int, filt: ImageFilter.Filter) -> None:
    size = ctx.brush_size
    r = size // 2
    x0, y0 = max(x - r, 0), max(y - r, 0)
    x1, y1 = min(x - r + size, layer.image.width), min(y - r + size, layer.image.height)
    if x1 <= x0 or y1 <= y0: return
    
    region = layer.image.crop((x0, y0, x1, y1))
    blurred = region.filter(filt)
    mask = _brush_mask(size, ctx.brush_hardness)
    mx0, my0 = x0 - (x - r), y0 - (y - r)
    sub_mask = mask.crop((mx0, my0, mx0 + (x1 - x0), my0 + (y1 - y0)))
    
    if ctx.brush_opacity < 1.0:
        sub_mask = sub_mask.point(lambda v: int(v * ctx.brush_opacity))
    
    sel = _selection_at_layer(ctx, layer)
    if sel:
        sub_mask = ImageChops.multiply(sub_mask, sel.crop((x0, y0, x1, y1)))
        
    blurred.putalpha(sub_mask)
    layer.image.alpha_composite(blurred, dest=(x0, y0))

# --- Base Tool Classes ---

class _ShapeTool(Tool):
    """Base for shape tools with full Move, Scale, and Rotate support."""
    commit_on = None
    HANDLE_SIZE = 10
    ROTATION_OFFSET = 30 # Screen pixels above shape

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._reset_state()

    def _reset_state(self):
        self._snapshot: Optional[Image.Image] = None
        self._bbox: Optional[Box] = None
        self._angle: float = 0.0
        self._phase = ToolPhase.IDLE
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[float, float]] = None
        self._bbox_at_press: Optional[Box] = None
        self._angle_at_press: float = 0.0

    def _get_handle_positions(self) -> dict[str, tuple[float, float]]:
        if not self._bbox: return {}
        b = self._bbox
        cx, cy = b.center
        zoom = max(0.01, getattr(self.ctx, "_canvas_zoom", 1.0))
        
        # Local relative points
        handles = {
            "nw": (b.x0, b.y0), "n": (cx, b.y0), "ne": (b.x1, b.y0),
            "w":  (b.x0, cy),                    "e":  (b.x1, cy),
            "sw": (b.x0, b.y1), "s": (cx, b.y1), "se": (b.x1, b.y1),
            "rot": (cx, b.y0 - (self.ROTATION_OFFSET / zoom))
        }
        # Rotate all handles around center
        return {k: _rotate_pt(v[0], v[1], cx, cy, self._angle) for k, v in handles.items()}

    def _hit_handle(self, x: float, y: float) -> Optional[str]:
        if not self._bbox: return None
        zoom = max(0.01, getattr(self.ctx, "_canvas_zoom", 1.0))
        hit_r_sq = (self.HANDLE_SIZE / zoom * 1.5) ** 2
        
        handles = self._get_handle_positions()
        best_name, best_dist = None, float('inf')
        for name, pos in handles.items():
            dist = (x - pos[0])**2 + (y - pos[1])**2
            if dist < hit_r_sq and dist < best_dist:
                best_name, best_dist = name, dist
        
        if best_name: return best_name
        
        # Body hit test: Rotate mouse point back to local space to check against AABB
        cx, cy = self._bbox.center
        lx, ly = _rotate_pt(x, y, cx, cy, -self._angle)
        b = self._bbox.normalized()
        if b.x0 <= lx <= b.x1 and b.y0 <= ly <= b.y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == ToolPhase.EDITING:
            hit = self._hit_handle(x, y)
            if hit:
                self._anchor = hit
                self._press_pt = (float(x), float(y))
                self._bbox_at_press = self._bbox
                self._angle_at_press = self._angle
                if hit == "move": self._phase = ToolPhase.MOVING
                elif hit == "rot": self._phase = ToolPhase.ROTATING
                else: self._phase = ToolPhase.SCALING
                return
            self._commit_session()

        self._snapshot = layer.image.copy()
        self._bbox = Box(x, y, x, y)
        self._angle = 0.0
        self._phase = ToolPhase.DRAWING
        self._press_pt = (float(x), float(y))

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == ToolPhase.IDLE: return
        
        xf, yf = float(x), float(y)
        
        if self._phase == ToolPhase.DRAWING:
            self._bbox = Box(self._press_pt[0], self._press_pt[1], xf, yf)
            
        elif self._phase == ToolPhase.MOVING:
            dx, dy = xf - self._press_pt[0], yf - self._press_pt[1]
            b = self._bbox_at_press
            self._bbox = Box(b.x0 + dx, b.y0 + dy, b.x1 + dx, b.y1 + dy)
            
        elif self._phase == ToolPhase.ROTATING:
            cx, cy = self._bbox_at_press.center
            angle_now = math.degrees(math.atan2(yf - cy, xf - cx))
            angle_press = math.degrees(math.atan2(self._press_pt[1] - cy, self._press_pt[0] - cx))
            self._angle = self._angle_at_press + (angle_now - angle_press) + 90
            
        elif self._phase == ToolPhase.SCALING:
            self._handle_scaling(xf, yf)
            
        self._render(layer)

    def _handle_scaling(self, x: float, y: float):
        b = self._bbox_at_press
        cx, cy = b.center
        # Rotate current mouse into local unrotated space
        lx, ly = _rotate_pt(x, y, cx, cy, -self._angle)
        plx, ply = _rotate_pt(self._press_pt[0], self._press_pt[1], cx, cy, -self._angle)
        
        dx, dy = lx - plx, ly - ply
        nx0, ny0, nx1, ny1 = b.x0, b.y0, b.x1, b.y1
        
        if "w" in self._anchor: nx0 += dx
        if "e" in self._anchor: nx1 += dx
        if "n" in self._anchor: ny0 += dy
        if "s" in self._anchor: ny1 += dy
        
        if self.ctx.shift_held:
            # Maintain aspect ratio
            orig_w, orig_h = max(1, b.width), max(1, b.height)
            new_w, new_h = abs(nx1 - nx0), abs(ny1 - ny0)
            scale = max(new_w / orig_w, new_h / orig_h)
            if "e" in self._anchor: nx1 = nx0 + orig_w * scale
            elif "w" in self._anchor: nx0 = nx1 - orig_w * scale
            if "s" in self._anchor: ny1 = ny0 + orig_h * scale
            elif "n" in self._anchor: ny0 = ny1 - orig_h * scale

        self._bbox = Box(nx0, ny0, nx1, ny1)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._phase in (ToolPhase.DRAWING, ToolPhase.MOVING, ToolPhase.SCALING, ToolPhase.ROTATING):
            self._phase = ToolPhase.EDITING
        super().release(layer, x, y)

    def _render(self, layer: Layer):
        if not self._snapshot or not self._bbox: return
        layer.image = self._snapshot.copy()
        self._draw(layer, self._bbox.normalized(), self._angle)
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def _commit_session(self):
        ca = getattr(self.ctx, "commit_action", None)
        if ca and self._snapshot and self._bbox:
            try: ca(self.name)
            except: pass
        self._reset_state()

    def commit(self) -> Optional[str]:
        name = self.name if self._snapshot and self._bbox else None
        self._reset_state()
        return name

    def paint_overlay(self, painter, canvas):
        if not self._bbox or self._phase == ToolPhase.IDLE: return
        from PyQt6.QtGui import QColor, QPen, QPolygonF
        from PyQt6.QtCore import QPointF, Qt
        
        hpts = self._get_handle_positions()
        scr = {k: QPointF(*canvas.canvas_to_screen(v[0], v[1])) for k, v in hpts.items()}
        
        # Draw Box
        painter.setPen(QPen(QColor(0, 180, 255), 1.5))
        painter.drawPolygon(QPolygonF([scr["nw"], scr["ne"], scr["se"], scr["sw"]]))
        painter.drawLine(scr["n"], scr["rot"])
        
        # Draw Handles
        painter.setBrush(QColor(255, 255, 255))
        hs = self.HANDLE_SIZE
        for pt in scr.values():
            painter.drawRect(int(pt.x() - hs/2), int(pt.y() - hs/2), hs, hs)

    def _draw(self, layer: Layer, bbox: Box, angle: float):
        raise NotImplementedError

class _SelectionToolBase(Tool):
    """Base for Marquee/Lasso with stable lifting logic."""
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._moving = False
        self._state: dict = {}

    def _begin_move_if_inside(self, layer: Layer, x: int, y: int) -> bool:
        if self.ctx.shift_held or self.ctx.alt_held: return False
        sel = self.ctx.get_selection()
        if not sel or not hasattr(sel, "mask") or sel.mask.getpixel((x, y)) == 0: return False

        # Lift pixels
        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(sel.mask, (-ox, -oy))
        
        src = layer.image.convert("RGBA")
        r, g, b, a = src.split()
        lift_a = ImageChops.multiply(a, layer_mask)
        if lift_a.getextrema()[1] == 0: return False
        
        base_a = ImageChops.multiply(a, ImageChops.invert(layer_mask))
        self._moving = True
        self._state = {
            "anchor": (x, y), "mask": sel.mask.copy(), "layer": layer,
            "lifted": Image.merge("RGBA", (r, g, b, lift_a)),
            "base": Image.merge("RGBA", (r, g, b, base_a))
        }
        layer.image = self._state["base"].copy()
        return True

    def _continue_move(self, x: int, y: int):
        if not self._moving: return
        s = self._state
        dx, dy = x - s["anchor"][0], y - s["anchor"][1]
        
        canvas = s["base"].copy()
        canvas.alpha_composite(s["lifted"], dest=(dx, dy))
        s["layer"].image = canvas
        
        shifted = Image.new("L", s["mask"].size, 0)
        shifted.paste(s["mask"], (dx, dy))
        
        from app.project import Selection
        bb = shifted.getbbox()
        if self.ctx.set_selection:
            self.ctx.set_selection(Selection(bbox=bb, mask=shifted) if bb else None)

    def _end_move(self) -> bool:
        if not self._moving: return False
        ca = getattr(self.ctx, "commit_action", None)
        if ca: ca("Move Selection")
        self._moving = False
        self._state = {}
        return True