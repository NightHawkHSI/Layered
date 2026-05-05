"""Tool base classes and drawing primitives.

The core provides:
  - ToolContext  : shared state passed to every tool call (colors, input
                   state, selection hooks, canvas hooks). Tool-specific
                   settings (brush size, tolerance, etc.) live in each
                   individual Tool subclass, NOT in ToolContext.
  - Tool         : abstract base class with the new plugin interface.
  - Drawing helpers: _brush_mask, _stamp_color, _stamp_erase, _walk, etc.
  - build_brush_settings_ui: convenience UI builder for brush-style tools.

Tools live under Plugins/Brushes/<Group>/<Tool>/tool.py and are loaded
by app.tool_loader.  Each tool.py exposes TOOL_CLASS pointing to the
Tool subclass to instantiate.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .layer import Layer


# ---------------------------------------------------------------------------
# Windows font helpers (used by TextTool.build_ui)
# ---------------------------------------------------------------------------

_FONT_PATH_CACHE: dict[str, str] = {}
_FONT_CACHE_BUILT = False


def _build_windows_font_cache() -> None:
    global _FONT_CACHE_BUILT
    if _FONT_CACHE_BUILT or sys.platform != "win32":
        _FONT_CACHE_BUILT = True
        return
    try:
        import winreg  # type: ignore
    except ImportError:
        _FONT_CACHE_BUILT = True
        return
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
    hives = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
        (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
    ]
    for hive, sub in hives:
        try:
            with winreg.OpenKey(hive, sub) as k:
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    family = name.split("(")[0].strip().lower()
                    path = value if os.path.isabs(value) else os.path.join(fonts_dir, value)
                    _FONT_PATH_CACHE.setdefault(family, path)
        except OSError:
            continue
    _FONT_CACHE_BUILT = True


def _resolve_windows_font(family: str) -> Optional[str]:
    _build_windows_font_cache()
    key = family.strip().lower()
    if key in _FONT_PATH_CACHE:
        return _FONT_PATH_CACHE[key]
    parts = key.split()
    while len(parts) > 1:
        parts.pop()
        cand = " ".join(parts)
        if cand in _FONT_PATH_CACHE:
            return _FONT_PATH_CACHE[cand]
    return None


# ---------------------------------------------------------------------------
# Shared types
# ---------------------------------------------------------------------------

Color = Tuple[int, int, int, int]


# ---------------------------------------------------------------------------
# ToolContext  - only core shared state; NO tool-specific settings
# ---------------------------------------------------------------------------

@dataclass
class ToolContext:
    """State passed to every tool call.

    Tools must NOT store their own settings here.  Each Tool subclass
    owns its own settings (brush_size, tolerance, text content, etc.)
    as instance variables and exposes them through build_ui().
    """
    # --- colours (shared, used by all painting tools) ---
    primary_color: Color = (0, 0, 0, 255)
    secondary_color: Color = (255, 255, 255, 255)

    # --- input state (set by Canvas before each event) ---
    shift_held: bool = False
    alt_held: bool = False
    ctrl_held: bool = False
    canvas_zoom: float = field(default=1.0, repr=False)

    # --- active layer (set by Canvas before each event) ---
    active_layer: Any = field(default=None, repr=False)

    # --- selection hooks ---
    get_selection: Optional[Callable[[], Any]] = field(default=None, repr=False)
    set_selection: Optional[Callable[[Any], None]] = field(default=None, repr=False)

    # --- history / canvas hooks ---
    commit_action: Optional[Callable[[str], None]] = field(default=None, repr=False)
    get_canvas_size: Optional[Callable[[], Tuple[int, int]]] = field(default=None, repr=False)

    # --- extensible hook registry ---
    # Tools look up named callbacks here instead of coupling to the host:
    #   "set_primary_color"  -> callable(color)   -- for Picker
    #   "get_layer_stack"    -> callable()         -- for Text
    #   "refresh_layers"     -> callable()         -- for Text
    hooks: dict = field(default_factory=dict, repr=False)

    # --- DEPRECATED: legacy tool-specific state ---
    # Pre-refactor tools (Plugins/builtin_tools.py, app/ui/tool_panel.py,
    # app/ui/text_panel.py) still read these off the shared context. Kept
    # here as a compat shim so the app starts; once every tool owns its
    # own state and exposes it through build_ui(), delete this block.
    brush_size: int = 8
    brush_hardness: float = 1.0
    brush_opacity: float = 1.0
    brush_spacing: float = 0.2
    fill_tolerance: int = 32
    fill_shape: bool = False
    text: str = "Text"
    text_size: int = 32
    text_font: str = ""
    on_tolerance_changed: Optional[Callable[[], None]] = field(default=None, repr=False)


# ---------------------------------------------------------------------------
# Tool base class - new plugin interface
# ---------------------------------------------------------------------------

class Tool:
    """Base class for all tool plugins.

    Subclasses override whichever methods they need.  No-op defaults are
    provided for every method so tools only implement what they use.

    Semantic roles (role string) let the core route certain actions
    without knowing concrete tool names:
      "default"       -- returned to after paste / commit (is_default=True preferred)
      "transform"     -- free transform; baked on Enter
      "sel_transform" -- selection transform
      "move"          -- layer / selection move
      "text"          -- text entry (Tab shortcut focuses settings widget)
    """
    name: str = "Tool"
    group: str = ""           # set by tool_loader from the parent folder name
    role: str = ""            # semantic role; see above
    is_default: bool = False
    commit_on: Optional[str] = "release"   # "press" | "release" | None

    def __init__(self, ctx: Optional["ToolContext"] = None):
        # Old-style tools call super().__init__(ctx); new-style tools call
        # super().__init__() with no args. Both work.
        if ctx is not None:
            self.ctx = ctx
        self._last_pt: Optional[Tuple[int, int]] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_select(self, ctx: ToolContext) -> None:
        """Called when this tool becomes the active tool."""

    def on_deselect(self, ctx: ToolContext) -> None:
        """Called just before another tool becomes active."""

    # ------------------------------------------------------------------
    # Mouse events
    # ------------------------------------------------------------------

    def on_mouse_down(self, ctx: ToolContext, x: int, y: int) -> None: ...
    def on_mouse_drag(self, ctx: ToolContext, x: int, y: int) -> None: ...
    def on_mouse_up(self, ctx: ToolContext, x: int, y: int) -> None: ...

    # Legacy adapters: Canvas still calls press/move/release with the active
    # layer. Stash the layer on ctx and forward to on_mouse_*. Old tools that
    # override press/move/release directly continue to work unchanged.
    def press(self, layer, x: int, y: int) -> None:
        ctx = getattr(self, "ctx", None)
        if ctx is not None:
            ctx.active_layer = layer
            self.on_mouse_down(ctx, x, y)

    def move(self, layer, x: int, y: int) -> None:
        ctx = getattr(self, "ctx", None)
        if ctx is not None:
            ctx.active_layer = layer
            self.on_mouse_drag(ctx, x, y)

    def release(self, layer, x: int, y: int) -> None:
        ctx = getattr(self, "ctx", None)
        if ctx is not None:
            ctx.active_layer = layer
            self.on_mouse_up(ctx, x, y)

    # ------------------------------------------------------------------
    # UI - tool provides its own settings widget
    # ------------------------------------------------------------------

    def build_ui(self, parent, ctx: ToolContext):
        """Return a QWidget (or None) to mount in the tool-settings area.

        Called every time the tool is activated.  The returned widget is
        owned by the tool panel; the previous tool's widget is destroyed
        before this is called.
        """
        return None

    # ------------------------------------------------------------------
    # Overlay / commit
    # ------------------------------------------------------------------

    def paint_overlay(self, painter, canvas) -> None:
        """Optional canvas overlay (handles, guides). Default: nothing."""

    def commit(self) -> Optional[str]:
        """Flush any in-progress edit; return a history label or None."""
        return None


# ---------------------------------------------------------------------------
# Soft circular brush mask cache
# ---------------------------------------------------------------------------

_MASK_CACHE: dict[tuple[int, int], Image.Image] = {}


def _brush_mask(size: int, hardness: float) -> Image.Image:
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
    if ctx.get_selection is None:
        return None
    sel = ctx.get_selection()
    if sel is None or getattr(sel, "mask", None) is None:
        return None
    ox, oy = layer.offset
    lw, lh = layer.image.size
    if getattr(sel, "is_full", False) and (ox, oy) == (0, 0) and sel.mask.size == (lw, lh):
        return None
    canvas_mask: Image.Image = sel.mask
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


def _clip_layer_to_selection(layer: Layer, ctx: ToolContext, before: Image.Image) -> None:
    if ctx.get_selection is not None:
        sel_obj = ctx.get_selection()
        if sel_obj is not None and getattr(sel_obj, "is_full", False):
            ox, oy = layer.offset
            cw_ch = sel_obj.mask.size if getattr(sel_obj, "mask", None) is not None else (0, 0)
            if (ox, oy) == (0, 0) and layer.image.size == cw_ch:
                return
    sel = _selection_at_layer(ctx, layer)
    if sel is None:
        return
    if before.size != layer.image.size or before.mode != layer.image.mode:
        before = before.convert(layer.image.mode).resize(layer.image.size)
    layer.image = Image.composite(layer.image, before, sel)


def _stamp_color(layer: Layer, x: int, y: int, color: Color, mask: Image.Image, opacity: float,
                 ctx: Optional[ToolContext] = None) -> None:
    r = mask.size[0] // 2
    ox, oy = layer.offset
    lx, ly = x - ox, y - oy
    final_alpha = (color[3] / 255.0) * opacity
    m = _scaled_mask(mask, final_alpha)
    if ctx is not None:
        m = _apply_selection_to_stamp(m, ctx, layer, (lx - r, ly - r))
    stamp = Image.new("RGBA", mask.size, color[:3] + (0,))
    stamp.putalpha(m)
    layer.image.alpha_composite(stamp, dest=(lx - r, ly - r))


def _stamp_erase(layer: Layer, x: int, y: int, mask: Image.Image, opacity: float,
                 ctx: Optional[ToolContext] = None) -> None:
    r = mask.size[0] // 2
    ox, oy = layer.offset
    lx, ly = x - ox, y - oy
    m = _scaled_mask(mask, opacity)
    if ctx is not None:
        m = _apply_selection_to_stamp(m, ctx, layer, (lx - r, ly - r))
    s = mask.size[0]
    x0 = max(lx - r, 0);  y0 = max(ly - r, 0)
    x1 = min(lx - r + s, layer.image.width)
    y1 = min(ly - r + s, layer.image.height)
    if x1 <= x0 or y1 <= y0:
        return
    mx0 = x0 - (lx - r);  my0 = y0 - (ly - r)
    mx1 = mx0 + (x1 - x0); my1 = my0 + (y1 - y0)
    region = layer.image.crop((x0, y0, x1, y1)).convert("RGBA")
    sub_mask = m.crop((mx0, my0, mx1, my1))
    arr = np.asarray(region, dtype=np.uint8).copy()
    mk = np.asarray(sub_mask, dtype=np.uint16)
    keep = (255 - mk).astype(np.uint16)
    arr[..., 3] = (arr[..., 3].astype(np.uint16) * keep // 255).astype(np.uint8)
    layer.image.paste(Image.fromarray(arr, mode="RGBA"), (x0, y0))


def _walk(p0: Tuple[int, int], p1: Tuple[int, int], spacing: float):
    x0, y0 = p0; x1, y1 = p1
    dx = x1 - x0; dy = y1 - y0
    dist = (dx * dx + dy * dy) ** 0.5
    step = max(1.0, spacing)
    n = max(1, int(dist / step))
    for i in range(n + 1):
        t = i / n
        yield int(round(x0 + dx * t)), int(round(y0 + dy * t))


# ---------------------------------------------------------------------------
# Shared UI helper - used by brush-style tool plugins
# ---------------------------------------------------------------------------

def build_brush_settings_ui(tool, parent, fields=("size", "hardness", "opacity", "spacing")):
    """Build a standard settings QWidget for a brush-style tool.

    ``tool`` must have attributes matching the requested ``fields``:
      - brush_size       (int)
      - brush_hardness   (float 0-1)
      - brush_opacity    (float 0-1)
      - brush_spacing    (float 0-1)
      - tolerance        (int 0-255)
      - fill_shape       (bool)

    Returns a QWidget or None if no fields are requested.
    """
    if not fields:
        return None
    from PyQt6.QtWidgets import QFormLayout, QSpinBox, QWidget
    try:
        from .ui.slider_field import SliderField
    except Exception:
        from app.ui.slider_field import SliderField

    w = QWidget(parent)
    layout = QFormLayout(w)
    layout.setContentsMargins(4, 4, 4, 4)

    if "size" in fields:
        spin = QSpinBox()
        spin.setRange(1, 1024)
        spin.setValue(int(getattr(tool, "brush_size", 20)))
        spin.valueChanged.connect(lambda v: setattr(tool, "brush_size", v))
        layout.addRow("Size:", spin)

    if "hardness" in fields:
        sf = SliderField(0, 100, int(getattr(tool, "brush_hardness", 0.8) * 100), suffix="%")
        sf.valueChanged.connect(lambda v: setattr(tool, "brush_hardness", v / 100.0))
        layout.addRow("Hardness:", sf)

    if "opacity" in fields:
        sf = SliderField(1, 100, int(getattr(tool, "brush_opacity", 1.0) * 100), suffix="%")
        sf.valueChanged.connect(lambda v: setattr(tool, "brush_opacity", v / 100.0))
        layout.addRow("Opacity:", sf)

    if "spacing" in fields:
        sf = SliderField(1, 200, int(getattr(tool, "brush_spacing", 0.05) * 100), suffix="%")
        sf.valueChanged.connect(lambda v: setattr(tool, "brush_spacing", v / 100.0))
        layout.addRow("Spacing:", sf)

    if "tolerance" in fields:
        sf = SliderField(0, 255, int(getattr(tool, "tolerance", 32)))
        sf.valueChanged.connect(lambda v: setattr(tool, "tolerance", int(v)))
        layout.addRow("Tolerance:", sf)

    if "fill_shape" in fields:
        from PyQt6.QtWidgets import QCheckBox
        cb = QCheckBox("Fill shape")
        cb.setChecked(bool(getattr(tool, "fill_shape", False)))
        cb.toggled.connect(lambda v: setattr(tool, "fill_shape", bool(v)))
        layout.addRow(cb)

    return w
