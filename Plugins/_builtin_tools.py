"""Built-in drawing tools plugin.

Provides all default tools (Brush, Eraser, Fill, Line, shapes, selection
tools, text, effect brushes, etc.) and loads brush presets from the
top-level ``Brushes/`` folder.  Separating these from the base application
code means you can override, extend, or replace any tool by editing this
file (or disabling it and shipping your own tool plugin) without touching
the core engine.
"""
from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from app.layer import Layer
from app.plugin_api import Plugin, PluginContext
from app.tools import (
    Color,
    Tool,
    ToolContext,
    _brush_mask,
    _clip_layer_to_selection,
    _scaled_mask,
    _selection_at_layer,
    _stamp_color,
    _stamp_erase,
    _walk,
    _build_windows_font_cache,
    _resolve_windows_font,
)


# ---------------------------------------------------------------------------
# Concrete tool implementations
# ---------------------------------------------------------------------------

class BrushTool(Tool):
    name = "Brush"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color, mask, self.ctx.brush_opacity, ctx=self.ctx)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = self._spacing()
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_color(layer, px, py, self.ctx.primary_color, mask, self.ctx.brush_opacity, ctx=self.ctx)
        self._last_pt = (x, y)


class EraserTool(Tool):
    name = "Eraser"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_erase(layer, x, y, mask, self.ctx.brush_opacity, ctx=self.ctx)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = self._spacing()
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_erase(layer, px, py, mask, self.ctx.brush_opacity, ctx=self.ctx)
        self._last_pt = (x, y)


class FillTool(Tool):
    name = "Fill"
    commit_on = "press"

    def press(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        lx, ly = x - ox, y - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return
        rgba = layer.image
        target = rgba.getpixel((lx, ly))
        replacement = self.ctx.primary_color
        if target == replacement:
            return
        before = rgba.copy()
        ImageDraw.floodfill(rgba, (lx, ly), replacement, thresh=self.ctx.fill_tolerance)
        _clip_layer_to_selection(layer, self.ctx, before)


class LineTool(Tool):
    name = "Line"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snapshot.copy()
        ImageDraw.Draw(layer.image).line(
            [self._origin, (x, y)], fill=self.ctx.primary_color, width=self.ctx.brush_size
        )
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)


def _shape_geom(origin, x, y, ctx: ToolContext) -> tuple[int, int, int, int]:
    ox, oy = origin
    x0, x1 = sorted((ox, x))
    y0, y1 = sorted((oy, y))
    if ctx.shift_held:
        s = min(x1 - x0, y1 - y0)
        x1, y1 = x0 + s, y0 + s
    return x0, y0, x1, y1


class _ShapeTool(Tool):
    """Base for shape tools that stay editable after release."""
    commit_on = None
    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._snapshot: Optional[Image.Image] = None
        self._bbox: Optional[tuple[int, int, int, int]] = None
        self._phase: str = "idle"
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._bbox_at_press: Optional[tuple[int, int, int, int]] = None

    def _draw(self, layer: Layer, bbox: tuple[int, int, int, int]) -> None:
        raise NotImplementedError

    def _hit_handle(self, x: int, y: int) -> Optional[str]:
        if self._bbox is None:
            return None
        x0, y0, x1, y1 = self._bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        hit_r = max(8, int(self.HANDLE_SIZE / zoom))
        best: Optional[tuple[str, int]] = None
        for name, (hx, hy) in handles.items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= hit_r * hit_r and (best is None or d < best[1]):
                best = (name, d)
        if best:
            return best[0]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == "editing":
            hit = self._hit_handle(x, y)
            if hit == "move":
                self._phase = "moving"
                self._press_pt = (x, y)
                self._bbox_at_press = self._bbox
                return
            if hit is not None:
                self._phase = "scaling"
                self._anchor = hit
                self._press_pt = (x, y)
                self._bbox_at_press = self._bbox
                return
            self._commit_session()
        self._snapshot = layer.image.copy()
        self._bbox = (x, y, x, y)
        self._phase = "drawing"
        self._press_pt = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._phase == "drawing":
            ox, oy = self._press_pt or (x, y)
            x0, x1 = sorted((ox, x))
            y0, y1 = sorted((oy, y))
            if self.ctx.shift_held:
                s = min(x1 - x0, y1 - y0)
                if x >= ox:
                    x1 = x0 + s
                else:
                    x0 = x1 - s
                if y >= oy:
                    y1 = y0 + s
                else:
                    y0 = y1 - s
            self._bbox = (x0, y0, x1, y1)
            self._render(layer)
        elif self._phase == "scaling":
            if self._bbox_at_press is None or self._press_pt is None:
                return
            x0, y0, x1, y1 = self._bbox_at_press
            px, py = self._press_pt
            dx, dy = x - px, y - py
            a = self._anchor or ""
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
            if "w" in a: nx0 += dx
            if "e" in a: nx1 += dx
            if "n" in a: ny0 += dy
            if "s" in a: ny1 += dy
            nx0, nx1 = sorted((nx0, nx1))
            ny0, ny1 = sorted((ny0, ny1))
            if self.ctx.shift_held:
                ow = max(1, x1 - x0); oh = max(1, y1 - y0)
                nw = max(1, nx1 - nx0); nh = max(1, ny1 - ny0)
                scale = max(nw / ow, nh / oh)
                tw = max(1, int(round(ow * scale)))
                th = max(1, int(round(oh * scale)))
                if "e" in a:
                    nx0, nx1 = x0, x0 + tw
                elif "w" in a:
                    nx0, nx1 = x1 - tw, x1
                else:
                    cx = (x0 + x1) // 2
                    nx0, nx1 = cx - tw // 2, cx - tw // 2 + tw
                if "s" in a:
                    ny0, ny1 = y0, y0 + th
                elif "n" in a:
                    ny0, ny1 = y1 - th, y1
                else:
                    cy = (y0 + y1) // 2
                    ny0, ny1 = cy - th // 2, cy - th // 2 + th
            self._bbox = (nx0, ny0, nx1, ny1)
            self._render(layer)
        elif self._phase == "moving":
            if self._bbox_at_press is None or self._press_pt is None:
                return
            x0, y0, x1, y1 = self._bbox_at_press
            px, py = self._press_pt
            dx, dy = x - px, y - py
            if self.ctx.shift_held:
                if abs(dx) > abs(dy):
                    dy = 0
                else:
                    dx = 0
            self._bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
            self._render(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._phase in ("drawing", "scaling", "moving"):
            self._phase = "editing"
            self._anchor = None
            self._press_pt = None
            self._bbox_at_press = None
        super().release(layer, x, y)

    def _render(self, layer: Layer) -> None:
        if self._snapshot is None or self._bbox is None:
            return
        layer.image = self._snapshot.copy()
        self._draw(layer, self._bbox)
        _clip_layer_to_selection(layer, self.ctx, self._snapshot)

    def _commit_session(self) -> None:
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None and self._snapshot is not None and self._bbox is not None:
            try:
                ca(self.name)
            except Exception:
                pass
        self._snapshot = None
        self._bbox = None
        self._phase = "idle"
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None

    def commit(self) -> Optional[str]:
        if self._snapshot is None or self._bbox is None:
            label = None
        else:
            label = self.name
        self._snapshot = None
        self._bbox = None
        self._phase = "idle"
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None
        return label

    def paint_overlay(self, painter, canvas) -> None:
        if self._bbox is None or self._phase == "idle":
            return
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        x0, y0, x1, y1 = self._bbox
        sx0, sy0 = canvas.canvas_to_screen(x0, y0)
        sx1, sy1 = canvas.canvas_to_screen(x1, y1)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        pen = QPen(QColor(0, 200, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 0, 0, 0))
        painter.drawRect(rect)
        if self._phase == "drawing":
            return
        painter.setBrush(QColor(255, 255, 255, 255))
        cx = rect.center().x()
        cy = rect.center().y()
        hs = self.HANDLE_SIZE
        for hx, hy in (
            (rect.left(), rect.top()), (cx, rect.top()), (rect.right(), rect.top()),
            (rect.left(), cy),                            (rect.right(), cy),
            (rect.left(), rect.bottom()), (cx, rect.bottom()), (rect.right(), rect.bottom()),
        ):
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)


class RectTool(_ShapeTool):
    name = "Rectangle"

    def _draw(self, layer: Layer, bbox: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = bbox
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.rectangle([x0, y0, x1, y1], fill=self.ctx.primary_color,
                        outline=self.ctx.primary_color, width=self.ctx.brush_size)
        else:
            d.rectangle([x0, y0, x1, y1], outline=self.ctx.primary_color,
                        width=self.ctx.brush_size)


class EllipseTool(_ShapeTool):
    name = "Ellipse"

    def _draw(self, layer: Layer, bbox: tuple[int, int, int, int]) -> None:
        x0, y0, x1, y1 = bbox
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.ellipse([x0, y0, x1, y1], fill=self.ctx.primary_color,
                      outline=self.ctx.primary_color, width=self.ctx.brush_size)
        else:
            d.ellipse([x0, y0, x1, y1], outline=self.ctx.primary_color,
                      width=self.ctx.brush_size)


class PickerTool(Tool):
    name = "Picker"
    commit_on = None

    def __init__(self, ctx: ToolContext, on_pick=None):
        super().__init__(ctx)
        self.on_pick = on_pick

    def press(self, layer: Layer, x: int, y: int) -> None:
        if 0 <= x < layer.image.width and 0 <= y < layer.image.height:
            color = layer.image.getpixel((x, y))
            if self.on_pick:
                self.on_pick(color)


class MoveTool(Tool):
    """Drag the active layer - or the pixels inside a selection - around the canvas."""
    name = "Move"
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._origin: Optional[Tuple[int, int]] = None
        self._initial_offset: Optional[Tuple[int, int]] = None
        self._sel_drag: bool = False
        self._sel_anchor: Optional[Tuple[int, int]] = None
        self._sel_start_mask: Optional[Image.Image] = None
        self._sel_base: Optional[Image.Image] = None
        self._sel_lifted: Optional[Image.Image] = None
        self._sel_layer: Optional[Layer] = None

    def _begin_selection_drag(self, layer: Layer, x: int, y: int) -> bool:
        if self.ctx.get_selection is None or self.ctx.set_selection is None:
            return False
        sel = self.ctx.get_selection()
        if sel is None or getattr(sel, "mask", None) is None:
            return False
        mask: Image.Image = sel.mask
        ox, oy = layer.offset
        lw, lh = layer.image.size
        layer_mask = Image.new("L", (lw, lh), 0)
        layer_mask.paste(mask, (-ox, -oy))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        lr, lg, lb, la = src.split()
        lifted_alpha = ImageChops.multiply(la, layer_mask)
        if lifted_alpha.getextrema()[1] == 0:
            return False
        lifted = Image.merge("RGBA", (lr, lg, lb, lifted_alpha))
        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base_r = ImageChops.multiply(lr, keep)
        base_g = ImageChops.multiply(lg, keep)
        base_b = ImageChops.multiply(lb, keep)
        base = Image.merge("RGBA", (base_r, base_g, base_b, base_alpha))
        layer.image = base.copy()
        self._sel_drag = True
        self._sel_anchor = (x, y)
        self._sel_start_mask = mask.copy()
        self._sel_base = base
        self._sel_lifted = lifted
        self._sel_layer = layer
        self._continue_selection_drag(x, y)
        return True

    def _continue_selection_drag(self, x: int, y: int) -> None:
        if (not self._sel_drag or self._sel_anchor is None
                or self._sel_start_mask is None
                or self._sel_base is None or self._sel_lifted is None
                or self._sel_layer is None
                or self.ctx.set_selection is None):
            return
        ax, ay = self._sel_anchor
        dx, dy = int(x - ax), int(y - ay)
        layer = self._sel_layer
        canvas_layer = self._sel_base.copy()
        shifted = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
        shifted.paste(self._sel_lifted, (dx, dy))
        canvas_layer.alpha_composite(shifted)
        layer.image = canvas_layer
        mw, mh = self._sel_start_mask.size
        shifted_mask = Image.new("L", (mw, mh), 0)
        shifted_mask.paste(self._sel_start_mask, (dx, dy))
        from app.project import Selection
        bb = shifted_mask.getbbox()
        if bb is None:
            self.ctx.set_selection(None)
        else:
            self.ctx.set_selection(Selection(bbox=bb, mask=shifted_mask))

    def _end_selection_drag(self) -> bool:
        if not self._sel_drag:
            return False
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None:
            try:
                ca("Move selection")
            except Exception:
                pass
        self._sel_drag = False
        self._sel_anchor = None
        self._sel_start_mask = None
        self._sel_base = None
        self._sel_lifted = None
        self._sel_layer = None
        return True

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._begin_selection_drag(layer, x, y):
            self._origin = None
            self._initial_offset = None
            return
        self._origin = (x, y)
        self._initial_offset = layer.offset

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._sel_drag:
            self._continue_selection_drag(x, y)
            return
        if not self._origin or self._initial_offset is None:
            return
        ox, oy = self._origin
        ix, iy = self._initial_offset
        layer.offset = (ix + (x - ox), iy + (y - oy))

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._end_selection_drag():
            super().release(layer, x, y)
            return
        if self._origin is not None and self._initial_offset is not None:
            ca = getattr(self.ctx, "commit_action", None)
            if ca is not None and layer.offset != self._initial_offset:
                try:
                    ca("Move layer")
                except Exception:
                    pass
        self._origin = None
        self._initial_offset = None
        super().release(layer, x, y)


class TransformTool(Tool):
    """Scale the active layer by dragging anchor handles on its bbox."""
    name = "Transform"
    commit_on = "release"

    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._mode: Optional[str] = None
        self._anchor: Optional[str] = None
        self._bbox0: Optional[tuple[int, int, int, int]] = None
        self._cropped: Optional[Image.Image] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._cur_bbox: Optional[tuple[int, int, int, int]] = None

    def _layer_bbox(self, layer: Layer) -> Optional[tuple[int, int, int, int]]:
        ox, oy = layer.offset
        lw, lh = layer.image.size
        if lw <= 0 or lh <= 0:
            return None
        return (ox, oy, ox + lw, oy + lh)

    def _hit_handle(self, layer: Layer, x: int, y: int, hit_radius: int) -> Optional[str]:
        bb = self._layer_bbox(layer)
        if bb is None:
            return None
        x0, y0, x1, y1 = bb
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        best: Optional[tuple[str, int]] = None
        for name, (hx, hy) in handles.items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= hit_radius * hit_radius and (best is None or d < best[1]):
                best = (name, d)
        if best:
            return best[0]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        bb = self._layer_bbox(layer)
        if bb is None:
            return
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        hit_radius = max(8, int(self.HANDLE_SIZE / zoom))
        h = self._hit_handle(layer, x, y, hit_radius)
        if h is None:
            return
        self._anchor = h
        self._mode = "move" if h == "move" else f"scale-{h}"
        self._bbox0 = bb
        self._cur_bbox = bb
        self._press_pt = (x, y)
        ox, oy = layer.offset
        local = (bb[0] - ox, bb[1] - oy, bb[2] - ox, bb[3] - oy)
        self._cropped = layer.image.crop(local).convert("RGBA")

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._mode is None or self._bbox0 is None or self._press_pt is None:
            return
        x0, y0, x1, y1 = self._bbox0
        px, py = self._press_pt
        dx, dy = x - px, y - py

        if self._mode == "move":
            new_bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
            self._apply(layer, new_bbox)
            return

        a = self._anchor or ""
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        if "w" in a: nx0 = x0 + dx
        if "e" in a: nx1 = x1 + dx
        if "n" in a: ny0 = y0 + dy
        if "s" in a: ny1 = y1 + dy
        nx0, nx1 = sorted((nx0, nx1))
        ny0, ny1 = sorted((ny0, ny1))

        if self.ctx.shift_held:
            ow = max(1, x1 - x0)
            oh = max(1, y1 - y0)
            nw = max(1, nx1 - nx0)
            nh = max(1, ny1 - ny0)
            scale = max(nw / ow, nh / oh)
            tw = max(1, int(round(ow * scale)))
            th = max(1, int(round(oh * scale)))
            if "e" in a or a == "n" or a == "s" or a == "move":
                ax = x0
            elif "w" in a:
                ax = x1
            else:
                ax = (x0 + x1) // 2
            if "s" in a or a == "w" or a == "e":
                ay = y0
            elif "n" in a:
                ay = y1
            else:
                ay = (y0 + y1) // 2
            if "e" in a:
                nx0, nx1 = ax, ax + tw
            elif "w" in a:
                nx0, nx1 = ax - tw, ax
            else:
                cx = (x0 + x1) // 2
                nx0, nx1 = cx - tw // 2, cx - tw // 2 + tw
            if "s" in a:
                ny0, ny1 = ay, ay + th
            elif "n" in a:
                ny0, ny1 = ay - th, ay
            else:
                cy = (y0 + y1) // 2
                ny0, ny1 = cy - th // 2, cy - th // 2 + th

        new_bbox = (nx0, ny0, nx1, ny1)
        self._apply(layer, new_bbox)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._mode = None
        self._anchor = None
        self._bbox0 = None
        self._cropped = None
        self._press_pt = None
        self._cur_bbox = None
        super().release(layer, x, y)

    def commit(self) -> Optional[str]:
        self._mode = None
        self._anchor = None
        self._bbox0 = None
        self._cropped = None
        self._press_pt = None
        self._cur_bbox = None
        return None

    def _apply(self, layer: Layer, new_bbox: tuple[int, int, int, int]) -> None:
        if self._cropped is None:
            return
        nx0, ny0, nx1, ny1 = new_bbox
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        resized = self._cropped.resize((nw, nh), Image.Resampling.LANCZOS)
        new_img = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
        new_img.paste(resized, (0, 0), resized)
        layer.image = new_img
        layer.offset = (nx0, ny0)
        self._cur_bbox = new_bbox

    def paint_overlay(self, painter, canvas) -> None:
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        layer = canvas.layer_stack.active
        if layer is None:
            return
        bb = self._cur_bbox or self._layer_bbox(layer)
        if bb is None:
            return
        x0, y0, x1, y1 = bb
        sx0, sy0 = canvas.canvas_to_screen(x0, y0)
        sx1, sy1 = canvas.canvas_to_screen(x1, y1)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        pen = QPen(QColor(0, 200, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 200, 255, 40))
        painter.drawRect(rect)
        painter.setBrush(QColor(255, 255, 255, 255))
        cx = rect.center().x()
        cy = rect.center().y()
        hs = self.HANDLE_SIZE
        for hx, hy in (
            (rect.left(), rect.top()), (cx, rect.top()), (rect.right(), rect.top()),
            (rect.left(), cy),                            (rect.right(), cy),
            (rect.left(), rect.bottom()), (cx, rect.bottom()), (rect.right(), rect.bottom()),
        ):
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)


# --- selection tools --------------------------------------------------------

class _SelectionToolBase(Tool):
    """Shared helpers for marquee / lasso / magic-wand."""
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._move_mode: bool = False
        self._move_anchor: Optional[tuple[int, int]] = None
        self._move_start_mask: Optional[Image.Image] = None
        self._lift_base: Optional[Image.Image] = None
        self._lift_image: Optional[Image.Image] = None
        self._lift_layer: Optional[Layer] = None

    def _canvas_size(self, layer: Layer) -> tuple[int, int]:
        getter = getattr(self.ctx, "get_canvas_size", None)
        if getter is not None:
            try:
                size = getter()
                if size is not None:
                    return int(size[0]), int(size[1])
            except Exception:
                pass
        ox, oy = layer.offset
        return layer.image.width + max(0, ox), layer.image.height + max(0, oy)

    def _current_mask_canvas(self, layer: Layer) -> Optional[Image.Image]:
        if self.ctx.get_selection is None:
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

    def _combine_with_current(self, new_mask: Image.Image, layer: Layer) -> Image.Image:
        if not (self.ctx.shift_held or self.ctx.alt_held):
            return new_mask
        current = self._current_mask_canvas(layer)
        if current is None:
            return new_mask
        if current.size != new_mask.size:
            cw, ch = current.size
            padded = Image.new("L", (cw, ch), 0)
            padded.paste(new_mask, (0, 0))
            new_mask = padded
        if self.ctx.shift_held:
            return ImageChops.lighter(current, new_mask)
        inv = new_mask.point(lambda v: 255 - v)
        return ImageChops.multiply(current, inv).point(lambda v: 255 if v >= 128 else 0)

    def _commit_mask(self, mask: Image.Image) -> None:
        if self.ctx.set_selection is None:
            return
        from app.project import Selection
        sel = Selection.from_mask(mask)
        self.ctx.set_selection(sel)

    def _begin_move_if_inside(self, layer: Layer, x: int, y: int) -> bool:
        if self.ctx.shift_held or self.ctx.alt_held:
            return False
        if self.ctx.get_selection is None:
            return False
        sel = self.ctx.get_selection()
        if sel is None or getattr(sel, "mask", None) is None:
            return False
        mask: Image.Image = sel.mask
        mw, mh = mask.size
        if not (0 <= x < mw and 0 <= y < mh):
            return False
        if mask.getpixel((x, y)) <= 0:
            return False

        ox, oy = layer.offset
        lw, lh = layer.image.size
        layer_mask = Image.new("L", (lw, lh), 0)
        layer_mask.paste(mask, (-ox, -oy))

        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        lr, lg, lb, la = src.split()
        lifted_alpha = ImageChops.multiply(la, layer_mask)
        if lifted_alpha.getextrema()[1] == 0:
            return False
        lifted = Image.merge("RGBA", (lr, lg, lb, lifted_alpha))

        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base_r = ImageChops.multiply(lr, keep)
        base_g = ImageChops.multiply(lg, keep)
        base_b = ImageChops.multiply(lb, keep)
        base = Image.merge("RGBA", (base_r, base_g, base_b, base_alpha))

        layer.image = base.copy()
        self._move_mode = True
        self._move_anchor = (x, y)
        self._move_start_mask = mask.copy()
        self._lift_base = base
        self._lift_image = lifted
        self._lift_layer = layer
        self._continue_move(x, y)
        return True

    def _continue_move(self, x: int, y: int) -> None:
        if (not self._move_mode or self._move_start_mask is None
                or self._move_anchor is None
                or self._lift_base is None or self._lift_image is None
                or self._lift_layer is None
                or self.ctx.set_selection is None):
            return
        ax, ay = self._move_anchor
        dx, dy = int(x - ax), int(y - ay)
        layer = self._lift_layer
        canvas_layer = self._lift_base.copy()
        lifted_shifted = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
        lifted_shifted.paste(self._lift_image, (dx, dy))
        canvas_layer.alpha_composite(lifted_shifted)
        layer.image = canvas_layer
        mw, mh = self._move_start_mask.size
        shifted_mask = Image.new("L", (mw, mh), 0)
        shifted_mask.paste(self._move_start_mask, (dx, dy))
        from app.project import Selection
        bb = shifted_mask.getbbox()
        if bb is None:
            self.ctx.set_selection(None)
        else:
            self.ctx.set_selection(Selection(bbox=bb, mask=shifted_mask))

    def _end_move(self) -> bool:
        if not self._move_mode:
            return False
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None:
            try:
                ca("Move selection")
            except Exception:
                pass
        self._move_mode = False
        self._move_anchor = None
        self._move_start_mask = None
        self._lift_base = None
        self._lift_image = None
        self._lift_layer = None
        return True


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


class LassoTool(_SelectionToolBase):
    """Freehand polygon selection."""
    name = "Lasso"

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._begin_move_if_inside(layer, x, y):
            self._points = None
            return
        self._points: list[tuple[int, int]] = [(x, y)]

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._move_mode:
            self._continue_move(x, y)
            return
        pts = getattr(self, "_points", None)
        if pts is None:
            return
        if not pts or (x, y) != pts[-1]:
            pts.append((x, y))

    def release(self, layer: Layer, x: int, y: int) -> None:
        if self._end_move():
            super().release(layer, x, y)
            return
        pts = getattr(self, "_points", None)
        if pts is None or len(pts) < 3:
            self._points = None
            super().release(layer, x, y)
            return
        canvas_w, canvas_h = self._canvas_size(layer)
        mask = Image.new("L", (canvas_w, canvas_h), 0)
        poly = [(int(px), int(py)) for px, py in pts]
        if poly[0] != poly[-1]:
            poly.append(poly[0])
        ImageDraw.Draw(mask).polygon(poly, fill=255, outline=255)
        combined = self._combine_with_current(mask, layer)
        self._commit_mask(combined)
        self._points = None
        super().release(layer, x, y)

    def paint_overlay(self, painter, canvas) -> None:
        pts = getattr(self, "_points", None)
        if not pts or len(pts) < 2:
            return
        from PyQt6.QtCore import QPoint
        from PyQt6.QtGui import QColor, QPen, QPolygon
        pen = QPen(QColor(255, 255, 255, 220), 1, _Qt_DashLine())
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(_Qt_NoBrush())
        poly = QPolygon([QPoint(int(canvas.canvas_to_screen(px, py)[0]),
                                 int(canvas.canvas_to_screen(px, py)[1])) for px, py in pts])
        painter.drawPolyline(poly)


def _Qt_DashLine():
    from PyQt6.QtCore import Qt
    return Qt.PenStyle.DashLine


def _Qt_NoBrush():
    from PyQt6.QtCore import Qt
    return Qt.BrushStyle.NoBrush


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


class GradientTool(Tool):
    """Drag to draw a linear gradient from primary -> secondary color."""
    name = "Gradient"
    commit_on = "release"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()
        self._cur = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if getattr(self, "_origin", None) is None:
            return
        self._cur = (x, y)
        self._render(layer, x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        if getattr(self, "_origin", None) is None:
            return
        self._render(layer, x, y)
        self._origin = None
        super().release(layer, x, y)

    def _render(self, layer: Layer, x: int, y: int) -> None:
        layer.image = self._snapshot.copy()
        ox, oy = self._origin
        dx, dy = x - ox, y - oy
        length2 = dx * dx + dy * dy
        if length2 <= 0:
            return
        w, h = layer.image.size
        ys, xs = np.mgrid[0:h, 0:w]
        t = ((xs - ox) * dx + (ys - oy) * dy) / length2
        t = np.clip(t, 0.0, 1.0).astype(np.float32)
        c1 = np.array(self.ctx.primary_color, dtype=np.float32)
        c2 = np.array(self.ctx.secondary_color, dtype=np.float32)
        out = c1 * (1 - t)[..., None] + c2 * t[..., None]
        out = np.clip(out, 0, 255).astype(np.uint8)
        grad = Image.fromarray(out, mode="RGBA")
        sel_mask = _selection_at_layer(self.ctx, layer)
        if sel_mask is not None:
            grad_alpha = grad.split()[3]
            grad.putalpha(ImageChops.multiply(grad_alpha, sel_mask))
        layer.image.alpha_composite(grad)


class TextTool(Tool):
    """Click to drop a re-editable text layer."""
    name = "Text"
    commit_on = None

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._target_stack = None
        self._target_layer: Optional[Layer] = None
        self._position: tuple[int, int] = (0, 0)
        self.on_layer_committed: Optional[Callable[[str], None]] = None
        self.on_layer_created: Optional[Callable[[], None]] = None

    def attach_stack(self, stack) -> None:
        self._target_stack = stack

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._target_stack is None:
            return
        if self._target_layer is not None and self._target_layer in self._target_stack.layers:
            label = self._commit_active()
            if label and self.on_layer_committed is not None:
                try:
                    self.on_layer_committed(label)
                except Exception:
                    pass
        new_layer = Layer(
            name="Text",
            image=Image.new("RGBA", (self._target_stack.width, self._target_stack.height), (0, 0, 0, 0)),
        )
        self._target_stack.add_layer(new_layer)
        self._target_layer = new_layer
        self._position = (x, y)
        self.rerender()
        if self.on_layer_created is not None:
            try:
                self.on_layer_created()
            except Exception:
                pass

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._target_layer is None:
            return
        self._position = (x, y)
        self.rerender()

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    def rerender(self) -> None:
        if self._target_layer is None or self._target_stack is None:
            return
        text = self.ctx.text or ""
        size = max(4, int(self.ctx.text_size))
        font = self._load_font(getattr(self.ctx, "text_font", "") or "", size)
        canvas = Image.new(
            "RGBA",
            (self._target_stack.width, self._target_stack.height),
            (0, 0, 0, 0),
        )
        if text:
            d = ImageDraw.Draw(canvas)
            try:
                d.multiline_text(self._position, text, fill=self.ctx.primary_color, font=font)
            except Exception:
                d.text(self._position, text, fill=self.ctx.primary_color, font=font)
        self._target_layer.image = canvas
        self._target_stack.invalidate_cache()

    def _commit_active(self) -> Optional[str]:
        if self._target_layer is None:
            return None
        label = f"Text: {self.ctx.text or ''}"[:40]
        self._target_layer = None
        return label

    def commit(self) -> Optional[str]:
        return self._commit_active()

    def _load_font(self, family: str, size: int):
        if family:
            path = _resolve_windows_font(family)
            if path:
                try:
                    return ImageFont.truetype(path, size)
                except Exception:
                    pass
        candidates = []
        if family:
            candidates.append(family)
            candidates.append(f"{family}.ttf")
            candidates.append(f"{family.lower()}.ttf")
        candidates.extend(["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"])
        for c in candidates:
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                continue
        return ImageFont.load_default()


# --- pixel-sample effect brushes --------------------------------------------

def _local_filter_stamp(layer: Layer, ctx: ToolContext, x: int, y: int,
                        filt: ImageFilter.Filter) -> None:
    size = ctx.brush_size
    r = size // 2
    x0 = max(x - r, 0); y0 = max(y - r, 0)
    x1 = min(x - r + size, layer.image.width)
    y1 = min(y - r + size, layer.image.height)
    if x1 <= x0 or y1 <= y0:
        return
    region = layer.image.crop((x0, y0, x1, y1))
    blurred = region.filter(filt)
    mask = _brush_mask(size, ctx.brush_hardness)
    mx0 = x0 - (x - r); my0 = y0 - (y - r)
    mx1 = mx0 + (x1 - x0); my1 = my0 + (y1 - y0)
    sub_mask = mask.crop((mx0, my0, mx1, my1))
    sub_mask = sub_mask.point(lambda v: int(v * ctx.brush_opacity))
    sel_mask = _selection_at_layer(ctx, layer)
    if sel_mask is not None:
        sub_sel = sel_mask.crop((x0, y0, x1, y1))
        sub_mask = ImageChops.multiply(sub_mask, sub_sel)
    blurred.putalpha(sub_mask)
    layer.image.alpha_composite(blurred, dest=(x0, y0))


class BlurTool(Tool):
    name = "Blur"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        _local_filter_stamp(layer, self.ctx, x, y,
                            ImageFilter.GaussianBlur(radius=max(1, self.ctx.brush_size // 4)))

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        f = ImageFilter.GaussianBlur(radius=max(1, self.ctx.brush_size // 4))
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _local_filter_stamp(layer, self.ctx, px, py, f)
        self._last_pt = (x, y)


class SharpenTool(Tool):
    name = "Sharpen"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        _local_filter_stamp(layer, self.ctx, x, y, ImageFilter.SHARPEN)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _local_filter_stamp(layer, self.ctx, px, py, ImageFilter.SHARPEN)
        self._last_pt = (x, y)


class SmudgeTool(Tool):
    """Pull the pixels at the previous sample point along the stroke direction."""
    name = "Smudge"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        size = self.ctx.brush_size
        r = size // 2
        sx, sy = self._last_pt
        sx0 = max(sx - r, 0); sy0 = max(sy - r, 0)
        sx1 = min(sx - r + size, layer.image.width)
        sy1 = min(sy - r + size, layer.image.height)
        if sx1 <= sx0 or sy1 <= sy0:
            self._last_pt = (x, y)
            return
        sample = layer.image.crop((sx0, sy0, sx1, sy1))
        mask = _brush_mask(sx1 - sx0, self.ctx.brush_hardness)
        opa = max(0.05, min(1.0, self.ctx.brush_opacity * 0.4))
        m = mask.point(lambda v: int(v * opa))
        sel_mask = _selection_at_layer(self.ctx, layer)
        dx = x - r; dy = y - r
        if sel_mask is not None:
            sx_clip0 = max(dx, 0); sy_clip0 = max(dy, 0)
            sx_clip1 = min(dx + (sx1 - sx0), sel_mask.size[0])
            sy_clip1 = min(dy + (sy1 - sy0), sel_mask.size[1])
            if sx_clip1 > sx_clip0 and sy_clip1 > sy_clip0:
                pad = Image.new("L", m.size, 0)
                sub = sel_mask.crop((sx_clip0, sy_clip0, sx_clip1, sy_clip1))
                pad.paste(sub, (sx_clip0 - dx, sy_clip0 - dy))
                m = ImageChops.multiply(m, pad)
        sample.putalpha(m)
        layer.image.alpha_composite(sample, dest=(dx, dy))
        self._last_pt = (x, y)


class CloneStampTool(Tool):
    """Alt-click sets a source point; subsequent drags stamp the source pixels."""
    name = "Clone Stamp"

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._source: Optional[tuple[int, int]] = None
        self._delta: Optional[tuple[int, int]] = None
        self._last_pt: Optional[tuple[int, int]] = None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self.ctx.alt_held:
            self._source = (x, y)
            return
        if self._source is None:
            return
        self._delta = (self._source[0] - x, self._source[1] - y)
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._source is None or self._delta is None or self._last_pt is None:
            return
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = None
        super().release(layer, x, y)

    def _stamp(self, layer: Layer, x: int, y: int) -> None:
        if self._delta is None:
            return
        dx, dy = self._delta
        size = self.ctx.brush_size
        r = size // 2
        sx, sy = x + dx, y + dy
        sx0 = max(sx - r, 0); sy0 = max(sy - r, 0)
        sx1 = min(sx - r + size, layer.image.width)
        sy1 = min(sy - r + size, layer.image.height)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        sample = layer.image.crop((sx0, sy0, sx1, sy1))
        mw, mh = sx1 - sx0, sy1 - sy0
        mask = _brush_mask(size, self.ctx.brush_hardness)
        mx0 = sx0 - (sx - r); my0 = sy0 - (sy - r)
        sub_mask = mask.crop((mx0, my0, mx0 + mw, my0 + mh))
        sub_mask = sub_mask.point(lambda v: int(v * self.ctx.brush_opacity))
        sel_mask = _selection_at_layer(self.ctx, layer)
        if sel_mask is not None:
            tgt_x = x - r + (sx0 - (sx - r))
            tgt_y = y - r + (sy0 - (sy - r))
            tgt_x0 = max(tgt_x, 0); tgt_y0 = max(tgt_y, 0)
            tgt_x1 = min(tgt_x + mw, sel_mask.size[0])
            tgt_y1 = min(tgt_y + mh, sel_mask.size[1])
            pad = Image.new("L", (mw, mh), 0)
            if tgt_x1 > tgt_x0 and tgt_y1 > tgt_y0:
                sub = sel_mask.crop((tgt_x0, tgt_y0, tgt_x1, tgt_y1))
                pad.paste(sub, (tgt_x0 - tgt_x, tgt_y0 - tgt_y))
            sub_mask = ImageChops.multiply(sub_mask, pad)
        sample.putalpha(sub_mask)
        target_x = x - r + (sx0 - (sx - r))
        target_y = y - r + (sy0 - (sy - r))
        layer.image.alpha_composite(sample, dest=(target_x, target_y))


class SelectionTransformTool(Tool):
    """Transform the active selection: drag handles to scale/move."""
    name = "Sel Transform"
    commit_on = None
    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._lift_layer: Optional[Layer] = None
        self._base: Optional[Image.Image] = None
        self._floating: Optional[Image.Image] = None
        self._float_mask: Optional[Image.Image] = None
        self._bbox: Optional[tuple[int, int, int, int]] = None
        self._mode: Optional[str] = None
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._bbox_at_press: Optional[tuple[int, int, int, int]] = None

    def _ensure_lifted(self, layer: Layer) -> bool:
        if self._floating is not None and self._lift_layer is layer:
            return True
        if self.ctx.get_selection is None:
            return False
        sel = self.ctx.get_selection()
        if sel is None or getattr(sel, "mask", None) is None:
            return False
        bb = sel.mask.getbbox()
        if bb is None:
            return False

        canvas_w, canvas_h = self._canvas_size(layer)
        canvas_mask = sel.mask
        if canvas_mask.size != (canvas_w, canvas_h):
            full = Image.new("L", (canvas_w, canvas_h), 0)
            full.paste(canvas_mask, (0, 0))
            canvas_mask = full

        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(canvas_mask, (-ox, -oy))

        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        lr, lg, lb, la = src.split()

        floating_layer_alpha = ImageChops.multiply(la, layer_mask)
        floating_layer = Image.merge("RGBA", (lr, lg, lb, floating_layer_alpha))
        floating = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        floating.paste(floating_layer, (ox, oy))

        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base = Image.merge("RGBA", (lr, lg, lb, base_alpha))

        self._lift_layer = layer
        self._base = base
        self._floating = floating
        self._float_mask = canvas_mask
        self._bbox = bb
        layer.image = base.copy()
        self._render_preview(layer)
        return True

    def _canvas_size(self, layer: Layer) -> tuple[int, int]:
        getter = getattr(self.ctx, "get_canvas_size", None)
        if getter is not None:
            try:
                size = getter()
                if size is not None:
                    return int(size[0]), int(size[1])
            except Exception:
                pass
        ox, oy = layer.offset
        return layer.image.width + max(0, ox), layer.image.height + max(0, oy)

    def _hit_handle(self, x: int, y: int) -> Optional[str]:
        if self._bbox is None:
            return None
        x0, y0, x1, y1 = self._bbox
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        handles = {
            "nw": (x0, y0), "n": (cx, y0), "ne": (x1, y0),
            "w":  (x0, cy),                "e":  (x1, cy),
            "sw": (x0, y1), "s": (cx, y1), "se": (x1, y1),
        }
        zoom = max(getattr(self.ctx, "_canvas_zoom", 1.0), 1e-6)
        hit_r = max(8, int(self.HANDLE_SIZE / zoom))
        best: Optional[tuple[str, int]] = None
        for name, (hx, hy) in handles.items():
            d = (x - hx) ** 2 + (y - hy) ** 2
            if d <= hit_r * hit_r and (best is None or d < best[1]):
                best = (name, d)
        if best:
            return best[0]
        if x0 <= x <= x1 and y0 <= y <= y1:
            return "move"
        return None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if not self._ensure_lifted(layer):
            return
        hit = self._hit_handle(x, y)
        if hit is None:
            self._commit_floating(layer)
            return
        self._press_pt = (x, y)
        self._bbox_at_press = self._bbox
        if hit == "move":
            self._mode = "move"
        else:
            self._mode = "scale"
            self._anchor = hit

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._mode is None or self._bbox_at_press is None or self._press_pt is None:
            return
        x0, y0, x1, y1 = self._bbox_at_press
        px, py = self._press_pt
        dx, dy = x - px, y - py

        if self._mode == "move":
            self._bbox = (x0 + dx, y0 + dy, x1 + dx, y1 + dy)
        else:
            a = self._anchor or ""
            nx0, ny0, nx1, ny1 = x0, y0, x1, y1
            if "w" in a: nx0 += dx
            if "e" in a: nx1 += dx
            if "n" in a: ny0 += dy
            if "s" in a: ny1 += dy
            nx0, nx1 = sorted((nx0, nx1))
            ny0, ny1 = sorted((ny0, ny1))
            if self.ctx.shift_held:
                ow = max(1, x1 - x0); oh = max(1, y1 - y0)
                nw = max(1, nx1 - nx0); nh = max(1, ny1 - ny0)
                scale = max(nw / ow, nh / oh)
                tw = max(1, int(round(ow * scale)))
                th = max(1, int(round(oh * scale)))
                if "e" in a:
                    nx0, nx1 = x0, x0 + tw
                elif "w" in a:
                    nx0, nx1 = x1 - tw, x1
                else:
                    cx = (x0 + x1) // 2
                    nx0, nx1 = cx - tw // 2, cx - tw // 2 + tw
                if "s" in a:
                    ny0, ny1 = y0, y0 + th
                elif "n" in a:
                    ny0, ny1 = y1 - th, y1
                else:
                    cy = (y0 + y1) // 2
                    ny0, ny1 = cy - th // 2, cy - th // 2 + th
            self._bbox = (nx0, ny0, nx1, ny1)

        self._render_preview(layer)

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._mode = None
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None
        super().release(layer, x, y)

    def _render_preview(self, layer: Layer) -> None:
        if self._floating is None or self._base is None or self._bbox is None:
            return
        scaled, scaled_mask = self._scaled_floating()
        nx0, ny0, nx1, ny1 = self._bbox
        ox, oy = layer.offset
        canvas_layer = self._base.copy()
        dest = (nx0 - ox, ny0 - oy)
        if scaled.size[0] > 0 and scaled.size[1] > 0:
            tmp = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
            tmp.paste(scaled, dest, scaled_mask)
            canvas_layer.alpha_composite(tmp)
        layer.image = canvas_layer
        if self.ctx.set_selection is not None and scaled_mask is not None:
            from app.project import Selection
            cw, ch = self._canvas_size(layer)
            new_mask = Image.new("L", (cw, ch), 0)
            new_mask.paste(scaled_mask, (nx0, ny0))
            self.ctx.set_selection(Selection(bbox=(nx0, ny0, nx1, ny1), mask=new_mask))

    def _scaled_floating(self) -> tuple[Image.Image, Image.Image]:
        assert self._floating is not None and self._float_mask is not None and self._bbox is not None
        nx0, ny0, nx1, ny1 = self._bbox
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        orig_bb = self._float_mask.getbbox()
        if orig_bb is None:
            empty = Image.new("RGBA", (nw, nh), (0, 0, 0, 0))
            empty_mask = Image.new("L", (nw, nh), 0)
            return empty, empty_mask
        crop_rgba = self._floating.crop(orig_bb)
        crop_mask = self._float_mask.crop(orig_bb)
        scaled = crop_rgba.resize((nw, nh), Image.Resampling.LANCZOS)
        scaled_mask = crop_mask.resize((nw, nh), Image.Resampling.LANCZOS)
        return scaled, scaled_mask

    def _commit_floating(self, layer: Layer) -> None:
        ca = getattr(self.ctx, "commit_action", None)
        if ca is not None:
            try:
                ca("Transform Selection")
            except Exception:
                pass
        self._reset_state()

    def _reset_state(self) -> None:
        self._lift_layer = None
        self._base = None
        self._floating = None
        self._float_mask = None
        self._bbox = None
        self._mode = None
        self._anchor = None
        self._press_pt = None
        self._bbox_at_press = None

    def commit(self) -> Optional[str]:
        had = self._floating is not None
        self._reset_state()
        return "Transform Selection" if had else None

    def paint_overlay(self, painter, canvas) -> None:
        bb = self._bbox
        if bb is None:
            sel = self.ctx.get_selection() if self.ctx.get_selection else None
            if sel is None or getattr(sel, "bbox", None) is None:
                return
            bb = sel.bbox
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        x0, y0, x1, y1 = bb
        sx0, sy0 = canvas.canvas_to_screen(x0, y0)
        sx1, sy1 = canvas.canvas_to_screen(x1, y1)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        pen = QPen(QColor(0, 200, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(0, 200, 255, 30))
        painter.drawRect(rect)
        painter.setBrush(QColor(255, 255, 255, 255))
        cx = rect.center().x()
        cy = rect.center().y()
        hs = self.HANDLE_SIZE
        for hx, hy in (
            (rect.left(), rect.top()), (cx, rect.top()), (rect.right(), rect.top()),
            (rect.left(), cy),                            (rect.right(), cy),
            (rect.left(), rect.bottom()), (cx, rect.bottom()), (rect.right(), rect.bottom()),
        ):
            painter.drawRect(int(hx - hs / 2), int(hy - hs / 2), hs, hs)


# ---------------------------------------------------------------------------
# Plugin registration
# ---------------------------------------------------------------------------

class BuiltinToolsPlugin(Plugin):
    """Registers all built-in tools and loads brush/tool presets from disk."""

    name = "Builtin Tools"
    version = "1.0.0"
    author = "Layered"

    def register(self, ctx: PluginContext) -> None:
        tc = ctx.tool_context

        tools = {
            "??? Brush":         BrushTool(tc),
            "?? Eraser":        EraserTool(tc),
            "? Move":          MoveTool(tc),
            "?? Transform":     TransformTool(tc),
            "? Marquee":       MarqueeTool(tc),
            "?? Lasso":         LassoTool(tc),
            "?? Magic Wand":    MagicWandTool(tc),
            "?? Sel Transform": SelectionTransformTool(tc),
            "?? Fill":          FillTool(tc),
            "?? Gradient":      GradientTool(tc),
            "?? Text":          TextTool(tc),
            "?? Line":          LineTool(tc),
            "?? Rectangle":     RectTool(tc),
            "? Ellipse":       EllipseTool(tc),
            "?????? Blur":          BlurTool(tc),
            "? Sharpen":       SharpenTool(tc),
            "?? Smudge":        SmudgeTool(tc),
            "?? Clone Stamp":   CloneStampTool(tc),
            "?? Picker":        PickerTool(tc),
        }

        for name, tool in tools.items():
            ctx.register_tool(name, tool)

        # Discover additional tools from Brushes/<Cat>/<ToolFolder>/tool.json.
        brushes_dir = Path(__file__).resolve().parent.parent / "Brushes"
        try:
            from app.tool_loader import load_tools
            discovered, categories = load_tools(brushes_dir, tc)
            for name, tool in discovered.items():
                ctx.register_tool(name, tool)
            if categories:
                ctx.set_tool_categories(categories)
        except Exception as exc:
            ctx.logger.warning("tool_loader failed: %s", exc)

        # Load brush presets from Brushes/.
        try:
            from app.brush_loader import load_brush_presets
            presets = load_brush_presets(brushes_dir)
            if presets:
                ctx.set_brush_presets(presets)
        except Exception as exc:
            ctx.logger.warning("brush_loader failed: %s", exc)
