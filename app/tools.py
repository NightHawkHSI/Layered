"""Drawing tools.

Tools operate on a Pillow Image (RGBA) given canvas-space coordinates from the
canvas widget. Each tool implements `press`, `move`, and `release`.

The brush and eraser stamp a cached circular mask along the stroke path with
configurable size, hardness, opacity, and spacing — giving soft edges and
flow control rather than the previous hard-line behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from .layer import Layer


Color = Tuple[int, int, int, int]


@dataclass
class ToolContext:
    primary_color: Color = (0, 0, 0, 255)
    secondary_color: Color = (255, 255, 255, 255)
    brush_size: int = 8
    brush_hardness: float = 1.0   # 0=soft, 1=hard
    brush_opacity: float = 1.0    # 0-1, multiplies stamp alpha
    brush_spacing: float = 0.2    # fraction of brush size between stamps
    fill_tolerance: int = 32
    shift_held: bool = False      # set by canvas before each event


class Tool:
    name = "Tool"
    # When the canvas should ask the host to commit a history snapshot:
    #   "release" — after the mouse-up of a stroke (Brush, Eraser, Line, …)
    #   "press"   — single-click tools (Fill)
    #   None      — never (Picker)
    commit_on: Optional[str] = "release"

    def __init__(self, ctx: ToolContext):
        self.ctx = ctx
        self._last_pt: Optional[Tuple[int, int]] = None

    def press(self, layer: Layer, x: int, y: int) -> None: ...
    def move(self, layer: Layer, x: int, y: int) -> None: ...
    def release(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = None

    def paint_overlay(self, painter, canvas) -> None:  # noqa: D401
        """Optional canvas overlay (handles, guides). Default: nothing."""
        return None


# --- soft circular brush mask cache -----------------------------------------

_MASK_CACHE: dict[tuple[int, int], Image.Image] = {}


def _brush_mask(size: int, hardness: float) -> Image.Image:
    """Return an L-mode Pillow image of a circular soft stamp.

    `hardness` ∈ [0, 1]: 1 = hard disk, 0 = full Gaussian-ish falloff.
    """
    size = max(1, int(size))
    h_key = max(0, min(100, int(hardness * 100)))
    key = (size, h_key)
    cached = _MASK_CACHE.get(key)
    if cached is not None:
        return cached

    h = h_key / 100.0
    r = size / 2.0
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt((xx - r + 0.5) ** 2 + (yy - r + 0.5) ** 2)
    if h >= 0.999:
        arr = (d <= r).astype(np.float32)
    else:
        inner = r * h
        arr = np.clip((r - d) / max(r - inner, 1e-6), 0.0, 1.0)
    mask = Image.fromarray((arr * 255.0).astype(np.uint8), mode="L")
    if len(_MASK_CACHE) > 64:
        _MASK_CACHE.clear()
    _MASK_CACHE[key] = mask
    return mask


def _scaled_mask(mask: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return mask
    return mask.point(lambda v: int(v * opacity))


def _stamp_color(layer: Layer, x: int, y: int, color: Color, mask: Image.Image, opacity: float) -> None:
    """Paint a color stamp using `mask` as alpha, blended onto layer.image."""
    r = mask.size[0] // 2
    final_alpha = (color[3] / 255.0) * opacity
    m = _scaled_mask(mask, final_alpha)
    stamp = Image.new("RGBA", mask.size, color[:3] + (0,))
    stamp.putalpha(m)
    layer.image.alpha_composite(stamp, dest=(x - r, y - r))


def _stamp_erase(layer: Layer, x: int, y: int, mask: Image.Image, opacity: float) -> None:
    """Erase by reducing alpha where `mask` is set."""
    r = mask.size[0] // 2
    m = _scaled_mask(mask, opacity)
    s = mask.size[0]
    x0 = max(x - r, 0)
    y0 = max(y - r, 0)
    x1 = min(x - r + s, layer.image.width)
    y1 = min(y - r + s, layer.image.height)
    if x1 <= x0 or y1 <= y0:
        return
    mx0 = x0 - (x - r)
    my0 = y0 - (y - r)
    mx1 = mx0 + (x1 - x0)
    my1 = my0 + (y1 - y0)

    region = layer.image.crop((x0, y0, x1, y1)).convert("RGBA")
    sub_mask = m.crop((mx0, my0, mx1, my1))
    arr = np.asarray(region, dtype=np.uint8).copy()
    mk = np.asarray(sub_mask, dtype=np.uint16)
    keep = (255 - mk).astype(np.uint16)
    arr[..., 3] = (arr[..., 3].astype(np.uint16) * keep // 255).astype(np.uint8)
    new_region = Image.fromarray(arr, mode="RGBA")
    layer.image.paste(new_region, (x0, y0))


def _walk(p0: Tuple[int, int], p1: Tuple[int, int], spacing: float):
    """Yield integer points along the segment p0 -> p1 every `spacing` px."""
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    dist = (dx * dx + dy * dy) ** 0.5
    step = max(1.0, spacing)
    n = max(1, int(dist / step))
    for i in range(n + 1):
        t = i / n
        yield int(round(x0 + dx * t)), int(round(y0 + dy * t))


# --- tools ------------------------------------------------------------------

class BrushTool(Tool):
    name = "Brush"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color, mask, self.ctx.brush_opacity)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = self._spacing()
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_color(layer, px, py, self.ctx.primary_color, mask, self.ctx.brush_opacity)
        self._last_pt = (x, y)


class EraserTool(Tool):
    name = "Eraser"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_erase(layer, x, y, mask, self.ctx.brush_opacity)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = self._spacing()
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_erase(layer, px, py, mask, self.ctx.brush_opacity)
        self._last_pt = (x, y)


class FillTool(Tool):
    name = "Fill"
    commit_on = "press"

    def press(self, layer: Layer, x: int, y: int) -> None:
        if not (0 <= x < layer.image.width and 0 <= y < layer.image.height):
            return
        rgba = layer.image
        target = rgba.getpixel((x, y))
        replacement = self.ctx.primary_color
        if target == replacement:
            return
        ImageDraw.floodfill(rgba, (x, y), replacement, thresh=self.ctx.fill_tolerance)


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

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)


class RectTool(Tool):
    name = "Rectangle"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snapshot.copy()
        ox, oy = self._origin
        x0, x1 = sorted((ox, x))
        y0, y1 = sorted((oy, y))
        ImageDraw.Draw(layer.image).rectangle(
            [x0, y0, x1, y1], outline=self.ctx.primary_color, width=self.ctx.brush_size
        )

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)


class EllipseTool(Tool):
    name = "Ellipse"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._snapshot = layer.image.copy()

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        layer.image = self._snapshot.copy()
        ox, oy = self._origin
        x0, x1 = sorted((ox, x))
        y0, y1 = sorted((oy, y))
        ImageDraw.Draw(layer.image).ellipse(
            [x0, y0, x1, y1], outline=self.ctx.primary_color, width=self.ctx.brush_size
        )

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)


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
    """Drag the active layer around the canvas by adjusting its offset."""
    name = "Move"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._origin = (x, y)
        self._initial_offset = layer.offset

    def move(self, layer: Layer, x: int, y: int) -> None:
        if not getattr(self, "_origin", None):
            return
        ox, oy = self._origin
        ix, iy = self._initial_offset
        layer.offset = (ix + (x - ox), iy + (y - oy))

    def release(self, layer: Layer, x: int, y: int) -> None:
        self._origin = None
        super().release(layer, x, y)


class TransformTool(Tool):
    """Scale the active layer by dragging anchor handles on its bbox.

    Hold Shift to keep aspect ratio. Center handle moves the bbox.
    """
    name = "Transform"
    commit_on = "release"

    HANDLE_SIZE = 10  # screen px

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._mode: Optional[str] = None  # "scale-<corner>" / "move" / None
        self._anchor: Optional[str] = None
        self._bbox0: Optional[tuple[int, int, int, int]] = None  # x0,y0,x1,y1 in canvas coords (= layer coords + offset)
        self._cropped: Optional[Image.Image] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._cur_bbox: Optional[tuple[int, int, int, int]] = None

    # --- bbox helpers ---

    def _layer_bbox(self, layer: Layer) -> Optional[tuple[int, int, int, int]]:
        bb = layer.image.getbbox()
        if bb is None:
            return None
        ox, oy = layer.offset
        return (bb[0] + ox, bb[1] + oy, bb[2] + ox, bb[3] + oy)

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

    # --- events ---

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

        # Normalize so x0<x1, y0<y1 (allow flip during drag).
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
            # anchor opposite corner / edge
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
            # rebuild around anchor
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

    # --- apply transform to layer image ---

    def _apply(self, layer: Layer, new_bbox: tuple[int, int, int, int]) -> None:
        if self._cropped is None:
            return
        nx0, ny0, nx1, ny1 = new_bbox
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        resized = self._cropped.resize((nw, nh), Image.Resampling.LANCZOS)
        canvas_w, canvas_h = layer.image.size
        new_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        ox, oy = layer.offset
        paste_x = nx0 - ox
        paste_y = ny0 - oy
        new_img.paste(resized, (paste_x, paste_y), resized)
        layer.image = new_img
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


def build_default_tools(ctx: ToolContext) -> dict[str, Tool]:
    return {
        "Brush": BrushTool(ctx),
        "Eraser": EraserTool(ctx),
        "Move": MoveTool(ctx),
        "Transform": TransformTool(ctx),
        "Fill": FillTool(ctx),
        "Line": LineTool(ctx),
        "Rectangle": RectTool(ctx),
        "Ellipse": EllipseTool(ctx),
        "Picker": PickerTool(ctx),
    }
