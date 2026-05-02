"""Drawing tools.

Tools operate on a Pillow Image (RGBA) given canvas-space coordinates from the
canvas widget. Each tool implements `press`, `move`, and `release`.

The brush and eraser stamp a cached circular mask along the stroke path with
configurable size, hardness, opacity, and spacing — giving soft edges and
flow control rather than the previous hard-line behavior.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

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
    alt_held: bool = False        # used by clone-stamp & sampling tools
    ctrl_held: bool = False       # selection tools: Ctrl = select-similar (non-contiguous) for wand
    fill_shape: bool = False      # rect/ellipse: fill instead of outline
    text: str = "Text"
    text_size: int = 32
    text_font: str = ""           # font family; empty = system default
    # Project hooks (set by canvas/main window so tools can access selection).
    get_selection: Optional[Callable[[], object]] = None
    set_selection: Optional[Callable[[object], None]] = None
    # Tools that batch multiple presses into one undo step (e.g. shape edit
    # sessions) call this with their label to flush a history snapshot.
    commit_action: Optional[Callable[[str], None]] = None
    # Returns (canvas_w, canvas_h) for the currently active project so
    # selection tools can build canvas-sized masks regardless of where
    # the active layer sits.
    get_canvas_size: Optional[Callable[[], Tuple[int, int]]] = None


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


def _selection_at_layer(ctx: ToolContext, layer: Layer) -> Optional[Image.Image]:
    """Return an L-mask aligned with `layer.image` if a selection is active."""
    if ctx.get_selection is None:
        return None
    sel = ctx.get_selection()
    if sel is None or getattr(sel, "mask", None) is None:
        return None
    canvas_mask: Image.Image = sel.mask
    ox, oy = layer.offset
    lw, lh = layer.image.size
    if canvas_mask.size == (lw, lh) and (ox, oy) == (0, 0):
        return canvas_mask
    out = Image.new("L", (lw, lh), 0)
    out.paste(canvas_mask, (-ox, -oy))
    return out


def _apply_selection_to_stamp(stamp_alpha: Image.Image, ctx: ToolContext, layer: Layer,
                              dest_xy: tuple[int, int]) -> Image.Image:
    sel_mask = _selection_at_layer(ctx, layer)
    if sel_mask is None:
        return stamp_alpha
    sw, sh = stamp_alpha.size
    dx, dy = dest_xy
    x0 = max(dx, 0); y0 = max(dy, 0)
    x1 = min(dx + sw, sel_mask.size[0]); y1 = min(dy + sh, sel_mask.size[1])
    if x1 <= x0 or y1 <= y0:
        return Image.new("L", (sw, sh), 0)
    sub = sel_mask.crop((x0, y0, x1, y1))
    pad = Image.new("L", (sw, sh), 0)
    pad.paste(sub, (x0 - dx, y0 - dy))
    return ImageChops.multiply(stamp_alpha, pad)


def _stamp_color(layer: Layer, x: int, y: int, color: Color, mask: Image.Image, opacity: float,
                 ctx: Optional[ToolContext] = None) -> None:
    """Paint a color stamp using `mask` as alpha, blended onto layer.image."""
    r = mask.size[0] // 2
    final_alpha = (color[3] / 255.0) * opacity
    m = _scaled_mask(mask, final_alpha)
    if ctx is not None:
        m = _apply_selection_to_stamp(m, ctx, layer, (x - r, y - r))
    stamp = Image.new("RGBA", mask.size, color[:3] + (0,))
    stamp.putalpha(m)
    layer.image.alpha_composite(stamp, dest=(x - r, y - r))


def _stamp_erase(layer: Layer, x: int, y: int, mask: Image.Image, opacity: float,
                 ctx: Optional[ToolContext] = None) -> None:
    """Erase by reducing alpha where `mask` is set."""
    r = mask.size[0] // 2
    m = _scaled_mask(mask, opacity)
    if ctx is not None:
        m = _apply_selection_to_stamp(m, ctx, layer, (x - r, y - r))
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


def _shape_geom(origin, x, y, ctx: ToolContext) -> tuple[int, int, int, int]:
    ox, oy = origin
    x0, x1 = sorted((ox, x))
    y0, y1 = sorted((oy, y))
    if ctx.shift_held:
        # Square / circle: keep aspect.
        s = min(x1 - x0, y1 - y0)
        x1, y1 = x0 + s, y0 + s
    return x0, y0, x1, y1


class _ShapeTool(Tool):
    """Base for shape tools that stay editable after release.

    After the initial drag, the shape's bbox sticks around with 8 corner /
    edge handles + a center move region. Dragging a handle resizes; dragging
    inside the bbox moves; clicking outside commits the current shape and
    starts a new one. Hold Shift for aspect-locked scale or axis-locked move.
    Switching tools also commits.
    """
    commit_on = None  # we manage our own history snapshots
    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._snapshot: Optional[Image.Image] = None
        self._bbox: Optional[tuple[int, int, int, int]] = None
        self._phase: str = "idle"   # idle | drawing | editing | scaling | moving
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._bbox_at_press: Optional[tuple[int, int, int, int]] = None

    # subclass hook
    def _draw(self, layer: Layer, bbox: tuple[int, int, int, int]) -> None:
        raise NotImplementedError

    # --- handle hit testing ---

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

    # --- events ---

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
            # Outside bbox — commit current and begin a new shape.
            self._commit_session()
        # New session.
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
                # Lock to the dominant axis.
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

    # --- render / commit ---

    def _render(self, layer: Layer) -> None:
        if self._snapshot is None or self._bbox is None:
            return
        layer.image = self._snapshot.copy()
        self._draw(layer, self._bbox)

    def _commit_session(self) -> None:
        """Flush the in-progress shape as its own history snapshot."""
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
        """Called by the host on tool switch. Returns label or None."""
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

    # --- overlay ---

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


# --- selection / paint tools added in round 8 -------------------------------


class _SelectionToolBase(Tool):
    """Shared helpers for marquee / lasso / magic-wand.

    Also implements drag-to-move: pressing inside an existing selection
    grabs the mask and shifts it as the cursor drags, so users can
    reposition a selection without redrawing it.
    """
    commit_on = None  # selection isn't a layer-image change; no history snap

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._move_mode: bool = False
        self._move_anchor: Optional[tuple[int, int]] = None
        self._move_start_mask: Optional[Image.Image] = None
        # Float-selection state: pixels are lifted from the active layer
        # at press time, follow the cursor as a floating buffer, then
        # land at the drop position on release.
        self._lift_base: Optional[Image.Image] = None     # layer pixels with selection erased
        self._lift_image: Optional[Image.Image] = None    # selection pixels in layer space
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
        """Return the active selection mask resized to canvas dims, or None."""
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
        """Apply Shift = add / Alt = subtract against the current mask.

        Returns the mask that should be committed. With no modifier, the
        new mask replaces the old one.
        """
        if not (self.ctx.shift_held or self.ctx.alt_held):
            return new_mask
        current = self._current_mask_canvas(layer)
        if current is None:
            return new_mask
        # Make sure shapes match before chops.
        if current.size != new_mask.size:
            cw, ch = current.size
            padded = Image.new("L", (cw, ch), 0)
            padded.paste(new_mask, (0, 0))
            new_mask = padded
        if self.ctx.shift_held:
            return ImageChops.lighter(current, new_mask)
        # Alt: subtract new from current = current AND NOT new.
        inv = new_mask.point(lambda v: 255 - v)
        return ImageChops.multiply(current, inv).point(lambda v: 255 if v >= 128 else 0)

    def _commit_mask(self, mask: Image.Image) -> None:
        if self.ctx.set_selection is None:
            return
        from .project import Selection
        sel = Selection.from_mask(mask)
        self.ctx.set_selection(sel)

    # --- drag-to-move shared logic ---

    def _begin_move_if_inside(self, layer: Layer, x: int, y: int) -> bool:
        """If (x, y) lands on the current selection mask, lift the pixels
        under that mask off the active layer and enter drag-move mode.
        The selection (and its pixels) then follow the cursor until
        release. Returns True iff drag-move started.

        Suppressed when Shift/Alt are held: those modifiers reserve the
        next press for an add/subtract selection, even when it lands
        inside the current selection.
        """
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

        # Translate canvas-space mask into layer-image space.
        ox, oy = layer.offset
        lw, lh = layer.image.size
        layer_mask = Image.new("L", (lw, lh), 0)
        layer_mask.paste(mask, (-ox, -oy))

        # Lifted pixels: copy of the layer with alpha multiplied by the
        # layer-space mask so only the selected region survives.
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        lr, lg, lb, la = src.split()
        lifted_alpha = ImageChops.multiply(la, layer_mask)
        lifted = Image.merge("RGBA", (lr, lg, lb, lifted_alpha))

        # Base layer: same pixels but with the selected region erased
        # (alpha multiplied by the inverted mask).
        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base = Image.merge("RGBA", (lr, lg, lb, base_alpha))

        layer.image = base.copy()

        self._move_mode = True
        self._move_anchor = (x, y)
        self._move_start_mask = mask.copy()
        self._lift_base = base
        self._lift_image = lifted
        self._lift_layer = layer
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

        # Repaint the active layer: start from the erased base, paste
        # the lifted pixels shifted by (dx, dy). Tool x,y are canvas
        # coordinates; layer.offset is constant during a drag so the
        # delta applies directly in layer-image space.
        layer = self._lift_layer
        canvas_layer = self._lift_base.copy()
        lifted_shifted = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
        lifted_shifted.paste(self._lift_image, (dx, dy))
        canvas_layer.alpha_composite(lifted_shifted)
        layer.image = canvas_layer

        # Move the selection mask by the same canvas-space delta.
        mw, mh = self._move_start_mask.size
        shifted_mask = Image.new("L", (mw, mh), 0)
        shifted_mask.paste(self._move_start_mask, (dx, dy))
        from .project import Selection
        bb = shifted_mask.getbbox()
        if bb is None:
            self.ctx.set_selection(None)
        else:
            self.ctx.set_selection(Selection(bbox=bb, mask=shifted_mask))

    def _end_move(self) -> bool:
        if not self._move_mode:
            return False
        # Final layer state already reflects the moved pixels from the
        # last _continue_move call. Snapshot history so the move is
        # undoable as a single discrete action.
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
    """Drag a rectangular selection. Click inside an existing selection
    to drag-move it instead of starting a new one."""
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
        pen = QPen(QColor(255, 255, 255, 220), 1, Qt_DashLine())
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt_NoBrush())
        painter.drawRect(rect)


class LassoTool(_SelectionToolBase):
    """Freehand polygon selection. Click inside an existing selection
    to drag-move it instead of starting a new lasso."""
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
        # Lasso points are already in canvas coordinates.
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
        pen = QPen(QColor(255, 255, 255, 220), 1, Qt_DashLine())
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt_NoBrush())
        poly = QPolygon([QPoint(int(canvas.canvas_to_screen(px, py)[0]),
                                 int(canvas.canvas_to_screen(px, py)[1])) for px, py in pts])
        painter.drawPolyline(poly)


def Qt_DashLine():
    from PyQt6.QtCore import Qt
    return Qt.PenStyle.DashLine


def Qt_NoBrush():
    from PyQt6.QtCore import Qt
    return Qt.BrushStyle.NoBrush


class MagicWandTool(_SelectionToolBase):
    """Click empty space to select all contiguous pixels within tolerance
    of the clicked color. Click inside an existing selection to drag-move
    it (lifting the pixels with the mask)."""
    name = "Magic Wand"
    commit_on = None

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._begin_move_if_inside(layer, x, y):
            return
        # Convert canvas coords to layer-local coords for sampling.
        ox, oy = layer.offset
        lx, ly = x - ox, y - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return
        arr = np.asarray(layer.image.convert("RGBA"), dtype=np.int16)
        target = arr[ly, lx].astype(np.int16)
        tol = max(0, int(self.ctx.fill_tolerance))
        diff = np.abs(arr - target).max(axis=-1)
        match = (diff <= tol)
        h, w = match.shape
        if self.ctx.ctrl_held:
            # Select-similar: every pixel in the layer that matches the
            # target colour, regardless of contiguity. Useful for
            # grabbing all whitespace, all of one color across an image,
            # etc. — Photoshop's "Select → Similar".
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
        # Canvas-sized mask with the layer's region pasted at its offset
        # — keeps every Selection.mask aligned to canvas coords regardless
        # of which tool produced it.
        canvas_w, canvas_h = self._canvas_size(layer)
        canvas_mask = Image.new("L", (canvas_w, canvas_h), 0)
        layer_mask = Image.fromarray((visited * 255).astype(np.uint8), mode="L")
        canvas_mask.paste(layer_mask, (ox, oy))
        combined = self._combine_with_current(canvas_mask, layer)
        self._commit_mask(combined)

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
        # Respect selection if any.
        sel_mask = _selection_at_layer(self.ctx, layer)
        if sel_mask is not None:
            grad_alpha = grad.split()[3]
            grad.putalpha(ImageChops.multiply(grad_alpha, sel_mask))
        layer.image.alpha_composite(grad)


class TextTool(Tool):
    """Click to drop a re-editable text layer.

    On press, creates (or moves) a dedicated text layer, then re-renders it
    live as the Text panel updates `ctx.text` / `ctx.text_size` /
    `ctx.text_font` / `ctx.primary_color`. Switching tools or pressing
    `commit()` finalises the current text and clears tool state.
    """
    name = "Text"
    commit_on = None  # we manage commits ourselves through canvas.action_committed

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._target_stack = None  # set externally so we can add layers
        self._target_layer: Optional[Layer] = None
        self._position: tuple[int, int] = (0, 0)

    def attach_stack(self, stack) -> None:
        self._target_stack = stack

    def press(self, layer: Layer, x: int, y: int) -> None:
        if self._target_stack is None:
            return
        if self._target_layer is None or self._target_layer not in self._target_stack.layers:
            new_layer = Layer(
                name="Text",
                image=Image.new("RGBA", (self._target_stack.width, self._target_stack.height), (0, 0, 0, 0)),
            )
            self._target_stack.add_layer(new_layer)
            self._target_layer = new_layer
        self._position = (x, y)
        self.rerender()

    def move(self, layer: Layer, x: int, y: int) -> None:
        # Drag to relocate text.
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
            d.text(self._position, text, fill=self.ctx.primary_color, font=font)
        self._target_layer.image = canvas
        self._target_stack.invalidate_cache()

    def commit(self) -> Optional[str]:
        """Stop editing the current text layer. Returns the label or None."""
        if self._target_layer is None:
            return None
        label = f"Text: {self.ctx.text or ''}"[:40]
        self._target_layer = None
        return label

    def _load_font(self, family: str, size: int):
        # Try a TrueType font; fall back to default. Allow selecting by family
        # name (Qt's font-name) by mapping to common TTFs on Windows.
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


# --- pixel-sample brushes ---------------------------------------------------


def _local_filter_stamp(layer: Layer, ctx: ToolContext, x: int, y: int,
                        filt: ImageFilter.Filter) -> None:
    """Apply a PIL filter inside the brush mask area."""
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
        # Reduced opacity per stamp keeps smudge progressive.
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
    """Alt-click sets a source point; subsequent drags stamp the source pixels
    offset by where the user clicked."""
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
        # Build matching mask trimmed to sample bounds.
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
    """Transform the active selection: drag handles to scale, drag inside
    to move, click outside to commit.

    On the first interaction the tool lifts the pixels under the active
    selection mask off the layer and tracks them as a floating buffer.
    Each handle drag rescales that buffer (and its mask) live; the
    re-rendered pixels are composited back onto the erased base each
    frame so undo captures the whole transform as one snapshot.
    """
    name = "Sel Transform"
    commit_on = None  # we issue our own commit_action when committing
    HANDLE_SIZE = 10

    def __init__(self, ctx: ToolContext):
        super().__init__(ctx)
        self._lift_layer: Optional[Layer] = None
        self._base: Optional[Image.Image] = None        # layer pixels with selection erased (layer-image space)
        self._floating: Optional[Image.Image] = None    # lifted RGBA pixels (canvas space, full canvas size)
        self._float_mask: Optional[Image.Image] = None  # L mask matching `_floating` (canvas size)
        self._bbox: Optional[tuple[int, int, int, int]] = None  # canvas-space bbox of floating pixels
        self._mode: Optional[str] = None
        self._anchor: Optional[str] = None
        self._press_pt: Optional[tuple[int, int]] = None
        self._bbox_at_press: Optional[tuple[int, int, int, int]] = None

    # --- selection lift ---

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

        # Floating buffer at canvas size: layer pixels with alpha gated
        # by the canvas-space selection mask, placed at the layer offset.
        floating_layer_alpha = ImageChops.multiply(la, layer_mask)
        floating_layer = Image.merge("RGBA", (lr, lg, lb, floating_layer_alpha))
        floating = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        floating.paste(floating_layer, (ox, oy))

        # Erase the selected pixels on the source layer so the transform
        # preview composites cleanly (we'll restore from this base each
        # frame rather than mutating layer.image cumulatively).
        keep = layer_mask.point(lambda v: 255 - v)
        base_alpha = ImageChops.multiply(la, keep)
        base = Image.merge("RGBA", (lr, lg, lb, base_alpha))

        self._lift_layer = layer
        self._base = base
        self._floating = floating
        self._float_mask = canvas_mask
        self._bbox = bb
        layer.image = base.copy()
        # Re-render the floating buffer at its original bbox so a click
        # that doesn't drag still leaves the canvas pixel-identical to
        # before the lift.
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

    # --- handle hit testing ---

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

    # --- events ---

    def press(self, layer: Layer, x: int, y: int) -> None:
        if not self._ensure_lifted(layer):
            return
        hit = self._hit_handle(x, y)
        if hit is None:
            # Clicked outside — drop floating pixels at current bbox.
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

    # --- preview / commit ---

    def _render_preview(self, layer: Layer) -> None:
        if self._floating is None or self._base is None or self._bbox is None:
            return
        # Resample the original floating buffer to the new bbox, then
        # composite onto the erased base. Working from the original each
        # frame keeps repeated scales from accumulating quality loss.
        scaled, scaled_mask = self._scaled_floating()
        nx0, ny0, nx1, ny1 = self._bbox
        ox, oy = layer.offset
        # Build a layer-image-sized surface aligned with `_base`.
        canvas_layer = self._base.copy()
        # Convert canvas-space bbox to layer-image-space dest.
        dest = (nx0 - ox, ny0 - oy)
        if scaled.size[0] > 0 and scaled.size[1] > 0:
            tmp = Image.new("RGBA", canvas_layer.size, (0, 0, 0, 0))
            tmp.paste(scaled, dest, scaled_mask)
            canvas_layer.alpha_composite(tmp)
        layer.image = canvas_layer
        # Update the live selection mask so the dashed outline tracks
        # the new bbox while the transform is in progress.
        if self.ctx.set_selection is not None and scaled_mask is not None:
            from .project import Selection
            cw, ch = self._canvas_size(layer)
            new_mask = Image.new("L", (cw, ch), 0)
            new_mask.paste(scaled_mask, (nx0, ny0))
            self.ctx.set_selection(Selection(bbox=(nx0, ny0, nx1, ny1), mask=new_mask))

    def _scaled_floating(self) -> tuple[Image.Image, Image.Image]:
        assert self._floating is not None and self._float_mask is not None and self._bbox is not None
        nx0, ny0, nx1, ny1 = self._bbox
        nw = max(1, nx1 - nx0)
        nh = max(1, ny1 - ny0)
        # Get the bounding box of the original floating content so we
        # only resample the meaningful pixels.
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
        # Already rendered into layer.image; just snapshot history and clear state.
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
        """Called by the host on tool switch."""
        had = self._floating is not None
        self._reset_state()
        return "Transform Selection" if had else None

    # --- overlay ---

    def paint_overlay(self, painter, canvas) -> None:
        # Use the live selection bbox as the source of truth so handles
        # always sit on the user-visible selection rectangle, even before
        # the first lift.
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


def build_default_tools(ctx: ToolContext) -> dict[str, Tool]:
    return {
        "Brush": BrushTool(ctx),
        "Eraser": EraserTool(ctx),
        "Move": MoveTool(ctx),
        "Transform": TransformTool(ctx),
        "Marquee": MarqueeTool(ctx),
        "Lasso": LassoTool(ctx),
        "Magic Wand": MagicWandTool(ctx),
        "Sel Transform": SelectionTransformTool(ctx),
        "Fill": FillTool(ctx),
        "Gradient": GradientTool(ctx),
        "Text": TextTool(ctx),
        "Line": LineTool(ctx),
        "Rectangle": RectTool(ctx),
        "Ellipse": EllipseTool(ctx),
        "Blur": BlurTool(ctx),
        "Sharpen": SharpenTool(ctx),
        "Smudge": SmudgeTool(ctx),
        "Clone Stamp": CloneStampTool(ctx),
        "Picker": PickerTool(ctx),
    }
