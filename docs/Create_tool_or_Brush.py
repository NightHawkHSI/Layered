"""
========================================================================
 Create_tool_or_Brush.py  -  Reference template for Layered tool plugins
========================================================================

This is a STANDALONE reference / cheat-sheet that shows every hook, every
helper, and every convention available when authoring a tool or brush
plugin for Layered. It is NOT loaded by the app: it lives at the project
root, outside the Plugins/ tree, so the loader ignores it. Copy any
section into your own `Plugins/Brushes/<Group>/<Tool>/tool.py` to start a
new tool.

------------------------------------------------------------------------
 1. WHERE TOOLS LIVE
------------------------------------------------------------------------

    Plugins/Brushes/
        <Group>/                 <- becomes a split-button group in the
                                    Tool panel (e.g. Paint, Draw, Effects,
                                    Select, Shapes, Lines, Custom Brushes)
            <ToolName>/
                tool.py          <- REQUIRED. Must define `TOOL_CLASS`.
                tool.json        <- OPTIONAL manifest (icon / display name)

The folder name of `<Group>` is used as the category label unless the
tool.json sets `"category"` explicitly.

------------------------------------------------------------------------
 2. MINIMAL TOOL  (~10 lines)
------------------------------------------------------------------------

    from app.tools import Tool
    from app.layer import Layer

    class HelloTool(Tool):
        name      = "Hello"        # label in the tool panel
        icon      = "👋"           # optional glyph
        commit_on = "release"      # "press" | "release" | None

        def press(self, layer: Layer, x: int, y: int) -> None: ...
        def move(self, layer: Layer, x: int, y: int) -> None: ...
        def release(self, layer: Layer, x: int, y: int) -> None:
            super().release(layer, x, y)   # forwards to history hook

    TOOL_CLASS = HelloTool

------------------------------------------------------------------------
 3. THE Tool BASE CLASS  (app/tools.py)
------------------------------------------------------------------------

Class attributes you can override:

    name          str    Display name. Required.
    group         str    Auto-set by the loader from parent folder name.
    role          str    Semantic hint:
                            "default"       - returned to after paste/commit
                            "transform"     - free transform; baked on Enter
                            "sel_transform" - selection transform
                            "move"          - layer/selection move
                            "text"          - text entry (Tab focuses widget)
    icon          str    Single emoji or glyph for the tool button.
    is_default    bool   If True, becomes the tool active at startup.
    commit_on     str    When the canvas should record history:
                            "press"   - immediately on mouse-down
                            "release" - on mouse-up (most common)
                            None      - tool calls ctx.commit_action(...) itself

Lifecycle hooks (override as needed):

    on_select(ctx)         called when this tool becomes active
    on_deselect(ctx)       called just before another tool takes over

Pointer events (two equivalent APIs - pick ONE per tool):

    Modern:                            Legacy / what Canvas actually calls:
      on_mouse_down(ctx, x, y)           press(layer, x, y)
      on_mouse_drag(ctx, x, y)           move(layer, x, y)
      on_mouse_up  (ctx, x, y)           release(layer, x, y)

The legacy `press/move/release` hooks default-forward to the modern
`on_mouse_*` versions, putting `layer` on `ctx.active_layer`. If you
override `release`, ALWAYS call `super().release(layer, x, y)` so the
canvas can fire the commit-on-release history snapshot.

UI:

    build_ui(parent, ctx) -> QWidget | None
        Return a QWidget shown in the tool-settings strip whenever the
        tool is active. Rebuilt on every activation; the previous
        widget is destroyed. Return None for no settings.

Overlay / commit:

    paint_overlay(painter, canvas)
        Draw on top of the canvas in screen coordinates. Use for
        marching ants, transform handles, etc. Do NOT mutate the layer
        here - it is purely cosmetic.

    commit() -> str | None
        Flush an in-progress edit. Return a history label if a commit
        actually happened, otherwise None. Used by tools with
        commit_on=None that batch multi-press edits (Shape, Transform,
        Sel Transform, Text).

------------------------------------------------------------------------
 4. ToolContext - what `self.ctx` exposes
------------------------------------------------------------------------

Set by Canvas before each pointer event. Tool-specific state (size,
tolerance, text content, etc.) belongs on the tool instance, NOT here.

    Colours:
        primary_color    : (r, g, b, a) ints 0-255
        secondary_color  : same

    Modifier keys (live):
        shift_held, alt_held, ctrl_held : bool
        canvas_zoom      : float    (1.0 = 100%)

    Active layer (set just before the event):
        active_layer     : Layer

    Selection hooks (None if no selection support):
        get_selection()  -> Selection | None
        set_selection(sel_or_None)

    History / canvas hooks:
        commit_action(label)        -> snapshot history with `label`
        get_canvas_size()           -> (width, height) in canvas pixels

    Hook registry (named callbacks injected by the host):
        ctx.hooks["set_primary_color"]  -- called by Picker
        ctx.hooks["get_layer_stack"]    -- used by Text
        ctx.hooks["refresh_layers"]     -- used by Text

    Legacy compat shim (still read by built-in tools):
        brush_size, brush_hardness, brush_opacity, brush_spacing
        fill_tolerance, fill_shape
        text, text_size, text_font

------------------------------------------------------------------------
 5. SHARED HELPERS  (Plugins/Brushes/_shared.py)
------------------------------------------------------------------------

Plugins/Brushes/ is not a Python package, so each tool.py loads the
shared module via importlib. Standard preamble:

    import importlib.util as _iu, sys as _sys
    from pathlib import Path as _P
    _SHARED_KEY = "_layered_brushes_shared"
    if _SHARED_KEY not in _sys.modules:
        _src = _P(__file__).resolve().parents[2] / "_shared.py"
        _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
        _mod = _iu.module_from_spec(_spec)
        _sys.modules[_SHARED_KEY] = _mod
        _spec.loader.exec_module(_mod)
    _sh = _sys.modules[_SHARED_KEY]

Then pull what you need off `_sh`:

    Re-exports from app.tools / app.layer / PIL:
        Tool, ToolContext, Layer
        Image, ImageChops, ImageDraw, ImageFilter

    Drawing primitives:
        _brush_mask(size, hardness) -> Image
            Cached circular soft-edge alpha mask (mode "L").
        _stamp_color(layer, x, y, color, mask, opacity, ctx=None)
            Composite a coloured stamp at (x, y). Selection-aware
            when `ctx` is provided.
        _stamp_erase(layer, x, y, mask, opacity, ctx=None)
            Subtract alpha at (x, y).
        _walk(p0, p1, spacing) -> generator of (x, y)
            Yields evenly spaced points between p0 and p1 - used to
            convert sparse drag samples into continuous strokes.
        _local_filter_stamp(layer, ctx, x, y, pil_filter)
            Apply a PIL ImageFilter inside one brush-radius circle
            (used by Blur / Sharpen).

    Selection:
        _selection_at_layer(ctx, layer) -> Image | None
            Returns the selection mask reprojected to the layer's
            local coordinates, or None if no selection.
        _clip_layer_to_selection(layer, ctx, before_image)
            Restore pixels outside the selection from `before_image`
            after a paint op. Use when you can't apply the mask
            in-flight (e.g. floodfill).
        _scaled_mask(mask, opacity) -> Image
            Multiply a mask by a 0..1 opacity scalar.

    Bases:
        _ShapeTool          drag-bbox shape primitive (override `_draw`)
        _SelectionToolBase  marquee/lasso/wand helpers (move-inside,
                            additive/subtractive combine, mask commit)

    Geometry / Qt:
        _shape_geom(origin, x, y, ctx) -> (x0, y0, x1, y1)
            Bounding box from drag origin -> current pointer with
            Shift-square handling.
        _Qt_DashLine() / _Qt_NoBrush()
            Lazy Qt enum getters - import inside paint_overlay so
            tools that never paint don't pay the Qt import cost.

------------------------------------------------------------------------
 6. tool.json MANIFEST  (optional)
------------------------------------------------------------------------

Place next to tool.py to override metadata without touching code:

    {
        "name":     "My Brush",
        "icon":     "✨",
        "category": "Custom Brushes",
        "class":    "BrushTool"     # used only when tool.py is absent
    }

Manifest values override class attributes. The `class` field lets a
manifest-only entry pull a class from `app.tools` (rare).

------------------------------------------------------------------------
 7. KEYBOARD SHORTCUTS
------------------------------------------------------------------------

Built-ins are registered in TOOL_SHORTCUTS at the top of
app/ui/tool_panel.py. Add an entry there keyed by your tool's `name` to
bind a shortcut. Single keys use Photoshop conventions:

    B Brush     E Eraser    G Fill      V Move      M Marquee
    L Lasso     W MagicWand T Text      I Picker    U Line
    R Blur      S CloneStamp            Ctrl+T Transform

------------------------------------------------------------------------
 8. EXAMPLE GALLERY
------------------------------------------------------------------------

The class definitions below are runnable and self-contained. Pick the
one closest to what you want, copy its body into your own tool.py, and
adjust. None of them is exported as TOOL_CLASS here, because this file
itself is not a plugin.
"""
from __future__ import annotations

# --- standard preamble (uncomment in a real tool.py) ----------------------
# import importlib.util as _iu, sys as _sys
# from pathlib import Path as _P
# _SHARED_KEY = "_layered_brushes_shared"
# if _SHARED_KEY not in _sys.modules:
#     _src = _P(__file__).resolve().parents[2] / "_shared.py"
#     _spec = _iu.spec_from_file_location(_SHARED_KEY, _src)
#     _mod = _iu.module_from_spec(_spec)
#     _sys.modules[_SHARED_KEY] = _mod
#     _spec.loader.exec_module(_mod)
# _sh = _sys.modules[_SHARED_KEY]
#
# Tool, Layer, ToolContext = _sh.Tool, _sh.Layer, _sh.ToolContext
# Image, ImageChops, ImageDraw = _sh.Image, _sh.ImageChops, _sh.ImageDraw
# _brush_mask, _stamp_color, _stamp_erase = _sh._brush_mask, _sh._stamp_color, _sh._stamp_erase
# _walk = _sh._walk
# _selection_at_layer = _sh._selection_at_layer
# _clip_layer_to_selection = _sh._clip_layer_to_selection
# _ShapeTool = _sh._ShapeTool
# _SelectionToolBase = _sh._SelectionToolBase
# _local_filter_stamp = _sh._local_filter_stamp
# _Qt_DashLine, _Qt_NoBrush = _sh._Qt_DashLine, _sh._Qt_NoBrush

# This template imports directly from `app` so it can be opened in an IDE
# without the importlib dance. Real tool.py files should use the preamble
# above instead.
from app.tools import (
    Tool,
    ToolContext,
    _brush_mask,
    _stamp_color,
    _stamp_erase,
    _walk,
    _selection_at_layer,
    _clip_layer_to_selection,
)
from app.layer import Layer
from PIL import Image, ImageChops, ImageDraw, ImageFilter


# ==========================================================================
# Example A. Round soft brush  -  the canonical "paints colour stamps"
# ==========================================================================

class ExampleBrush(Tool):
    name = "Example Brush"
    icon = "🖌"
    commit_on = "release"

    def _spacing(self) -> float:
        return max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color, mask,
                     self.ctx.brush_opacity, ctx=self.ctx)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            _stamp_color(layer, px, py, self.ctx.primary_color, mask,
                         self.ctx.brush_opacity, ctx=self.ctx)
        self._last_pt = (x, y)

    def build_ui(self, parent, ctx):
        # Inline strip with size / hardness / opacity / spacing sliders.
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField
        host = QWidget(parent)
        row = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)

        def add(label, lo, hi, value, setter, w=90):
            row.addWidget(QLabel(label))
            s = SliderField(lo, hi, value, slider_width=w)
            s.valueChanged.connect(setter)
            row.addWidget(s)

        add("Size",     1, 500, int(ctx.brush_size),
            lambda v: setattr(ctx, "brush_size", int(v)), w=100)
        add("Hardness", 0, 100, int(ctx.brush_hardness * 100),
            lambda v: setattr(ctx, "brush_hardness", v / 100.0))
        add("Opacity",  0, 100, int(ctx.brush_opacity * 100),
            lambda v: setattr(ctx, "brush_opacity", v / 100.0))
        add("Spacing",  0, 100, int(ctx.brush_spacing * 100),
            lambda v: setattr(ctx, "brush_spacing", v / 100.0))
        row.addStretch()
        return host


# ==========================================================================
# Example B. Eraser  -  same as ExampleBrush but with _stamp_erase
# ==========================================================================

class ExampleEraser(Tool):
    name = "Example Eraser"
    icon = "🩹"
    commit_on = "release"

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        _stamp_erase(layer, x, y, mask, self.ctx.brush_opacity, ctx=self.ctx)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        mask = _brush_mask(self.ctx.brush_size, self.ctx.brush_hardness)
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_erase(layer, px, py, mask, self.ctx.brush_opacity, ctx=self.ctx)
        self._last_pt = (x, y)


# ==========================================================================
# Example C. One-shot tool  -  flood fill, commit_on="press"
# ==========================================================================

class ExampleFill(Tool):
    name = "Example Fill"
    icon = "🪣"
    commit_on = "press"   # snapshot history on click, no drag needed

    def press(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        lx, ly = x - ox, y - oy
        if not (0 <= lx < layer.image.width and 0 <= ly < layer.image.height):
            return
        before = layer.image.copy()
        target = layer.image.getpixel((lx, ly))
        replacement = self.ctx.primary_color
        if target == replacement:
            return
        ImageDraw.floodfill(layer.image, (lx, ly), replacement,
                            thresh=self.ctx.fill_tolerance)
        # Floodfill ignores the selection - clip after the fact.
        _clip_layer_to_selection(layer, self.ctx, before)


# ==========================================================================
# Example D. Filter brush  -  paints an ImageFilter with brush mask
# ==========================================================================

class ExampleBlurBrush(Tool):
    name = "Example Blur"

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        f = ImageFilter.GaussianBlur(radius=max(1, self.ctx.brush_size // 4))
        from app.tools import _selection_at_layer  # already imported above
        # Use the shared _local_filter_stamp helper from _shared.py in real
        # plugins; below is the inline form for clarity.
        _stamp_filter(layer, self.ctx, x, y, f)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        f = ImageFilter.GaussianBlur(radius=max(1, self.ctx.brush_size // 4))
        spacing = max(1.0, self.ctx.brush_size * self.ctx.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_filter(layer, self.ctx, px, py, f)
        self._last_pt = (x, y)


def _stamp_filter(layer, ctx, x, y, filt):
    """Standalone copy of _shared._local_filter_stamp for documentation."""
    size = ctx.brush_size
    r = size // 2
    x0 = max(x - r, 0); y0 = max(y - r, 0)
    x1 = min(x - r + size, layer.image.width)
    y1 = min(y - r + size, layer.image.height)
    if x1 <= x0 or y1 <= y0:
        return
    region = layer.image.crop((x0, y0, x1, y1)).filter(filt)
    mask = _brush_mask(size, ctx.brush_hardness)
    sub = mask.crop((x0 - (x - r), y0 - (y - r),
                     x0 - (x - r) + (x1 - x0), y0 - (y - r) + (y1 - y0)))
    sub = sub.point(lambda v: int(v * ctx.brush_opacity))
    sel = _selection_at_layer(ctx, layer)
    if sel is not None:
        sub = ImageChops.multiply(sub, sel.crop((x0, y0, x1, y1)))
    region.putalpha(sub)
    layer.image.alpha_composite(region, dest=(x0, y0))


# ==========================================================================
# Example E. Drag-shape with handles  -  subclass _ShapeTool from _shared
# ==========================================================================
# Real tool.py:
#   _ShapeTool = _sh._ShapeTool
#   class MyShape(_ShapeTool): ...
# In this template we import the class indirectly so it documents itself.

class ExampleHexagon:  # would be: class ExampleHexagon(_ShapeTool):
    """Inscribe a hexagon in the drag bbox.

    Subclassing `_ShapeTool` gets you for free:
      - drag-out bounding box
      - 8 resize handles + move-inside
      - Shift-locks proportions
      - history snapshot on commit/cancel
      - paint_overlay drawing the bbox + handles

    You only implement `_draw(layer, bbox)`.
    """

    name = "Example Hexagon"

    def _draw(self, layer, bbox):
        import math
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        rx, ry = (x1 - x0) / 2.0, (y1 - y0) / 2.0
        pts = [
            (int(cx + rx * math.cos(math.pi * 2 * i / 6 - math.pi / 2)),
             int(cy + ry * math.sin(math.pi * 2 * i / 6 - math.pi / 2)))
            for i in range(6)
        ]
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:  # type: ignore[attr-defined]
            d.polygon(pts, fill=self.ctx.primary_color,           # type: ignore
                      outline=self.ctx.primary_color)             # type: ignore
        else:
            d.polygon(pts, outline=self.ctx.primary_color,        # type: ignore
                      width=max(1, self.ctx.brush_size))          # type: ignore


# ==========================================================================
# Example F. Selection tool  -  subclass _SelectionToolBase from _shared
# ==========================================================================

class ExampleMarquee:  # would be: class ExampleMarquee(_SelectionToolBase):
    """Drag a rectangular selection.

    `_SelectionToolBase` provides:
      - move-inside-existing-selection (no Shift/Alt) lifts the pixels
        and lets the user drag them, then re-commits the mask
      - Shift adds to the existing selection, Alt subtracts
      - `_commit_mask(mask)` writes the mask back via ctx.set_selection
      - `_canvas_size(layer)` returns canvas dimensions, padded if needed
    """
    name = "Example Marquee"
    commit_on = None  # selection tools don't snapshot the layer

    def press(self, layer, x, y):
        if self._begin_move_if_inside(layer, x, y):  # type: ignore
            self._origin = None
            return
        self._origin = (x, y)
        self._cur = (x, y)

    def move(self, layer, x, y):
        if self._move_mode:                          # type: ignore
            self._continue_move(x, y)                # type: ignore
            return
        if getattr(self, "_origin", None) is None:
            return
        self._cur = (x, y)

    def release(self, layer, x, y):
        if self._end_move():                         # type: ignore
            super().release(layer, x, y)             # type: ignore
            return
        if getattr(self, "_origin", None) is None:
            return
        ox, oy = self._origin
        x0, x1 = sorted((ox, x)); y0, y1 = sorted((oy, y))
        cw, ch = self._canvas_size(layer)            # type: ignore
        mask = Image.new("L", (cw, ch), 0)
        ImageDraw.Draw(mask).rectangle([x0, y0, x1 - 1, y1 - 1], fill=255)
        # `_combine_with_current` honours Shift (add) / Alt (subtract).
        combined = self._combine_with_current(mask, layer)   # type: ignore
        self._commit_mask(combined)                  # type: ignore
        super().release(layer, x, y)                 # type: ignore

    def paint_overlay(self, painter, canvas):
        # Marching-ants overlay during the drag.
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        if getattr(self, "_origin", None) is None:
            return
        ox, oy = self._origin
        cx, cy = self._cur
        sx0, sy0 = canvas.canvas_to_screen(ox, oy)
        sx1, sy1 = canvas.canvas_to_screen(cx, cy)
        rect = QRect(int(min(sx0, sx1)), int(min(sy0, sy1)),
                     int(abs(sx1 - sx0)), int(abs(sy1 - sy0)))
        # In a real plugin: pen = QPen(QColor(255,255,255,220), 1, _Qt_DashLine())
        pen = QPen(QColor(255, 255, 255, 220), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(rect)


# ==========================================================================
# Example G. Settings popup  -  QToolButton + QMenu + QWidgetAction
# ==========================================================================

class ExamplePopupSettingsTool(Tool):
    """A tool with many settings folds them into a dropdown menu."""
    name = "Example Popup"
    icon = "⚙"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.density = 5
        self.spread_pct = 100

    def build_ui(self, parent, ctx):
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import (
            QHBoxLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction,
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Settings")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(110)

        menu = QMenu(btn)
        host = QWidget(menu)
        row = QHBoxLayout(host)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(10)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        row.addWidget(QLabel("Density"))
        s1 = SliderField(1, 20, self.density, slider_width=160)
        s1.valueChanged.connect(lambda v: setattr(self, "density", int(v)))
        row.addWidget(s1)

        row.addWidget(QLabel("Spread %"))
        s2 = SliderField(10, 300, self.spread_pct, slider_width=160)
        s2.valueChanged.connect(lambda v: setattr(self, "spread_pct", int(v)))
        row.addWidget(s2)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(host)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn


# ==========================================================================
# Example H. Multi-press editor  -  commit_on=None, hand-rolled commit()
# ==========================================================================

class ExampleSticker(Tool):
    """Click to place a sticker; click again somewhere else to move it.
    Click off the sticker (or pick another tool) to bake it.

    Uses commit_on=None so the canvas does NOT snapshot history on every
    press/release. Instead, this tool calls `ctx.commit_action("Sticker")`
    itself when it actually wants to bake.
    """
    name = "Example Sticker"
    commit_on = None

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self._snapshot = None
        self._pos = None

    def press(self, layer, x, y):
        if self._snapshot is None:
            self._snapshot = layer.image.copy()
        layer.image = self._snapshot.copy()
        self._pos = (x, y)
        ImageDraw.Draw(layer.image).text(
            (x, y), "★", fill=self.ctx.primary_color)

    def commit(self):
        # Called on tool switch, Enter, or a programmatic flush.
        if self._snapshot is None or self._pos is None:
            return None
        self._snapshot = None
        self._pos = None
        return "Sticker"   # history label

    def cancel(self):
        # Called on Esc - restore the snapshot if we have one.
        # (commit() is called separately for normal flush.)
        ...

    def paint_overlay(self, painter, canvas):
        if self._pos is None:
            return
        from PyQt6.QtCore import QRect
        from PyQt6.QtGui import QColor, QPen
        sx, sy = canvas.canvas_to_screen(*self._pos)
        pen = QPen(QColor(0, 200, 255, 220), 1); pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawRect(QRect(int(sx) - 8, int(sy) - 8, 16, 16))


# ==========================================================================
# Example I. Picker  -  read pixels, push colour back to host via hook
# ==========================================================================

class ExamplePicker(Tool):
    name = "Example Picker"
    icon = "🎯"
    commit_on = None   # reading pixels does not modify the layer

    def __init__(self, ctx=None, on_pick=None):
        super().__init__(ctx)
        self.on_pick = on_pick   # set by host: lambda c: color_panel.set_primary(c)

    def press(self, layer, x, y):
        if 0 <= x < layer.image.width and 0 <= y < layer.image.height:
            color = layer.image.getpixel((x, y))
            if self.on_pick:
                self.on_pick(color)


# ==========================================================================
# Example J. Tool with on_select / on_deselect lifecycle work
# ==========================================================================

class ExampleStateful(Tool):
    name = "Example Stateful"

    def on_select(self, ctx: ToolContext) -> None:
        # Cache anything expensive here so press/move are cheap.
        self._cached_mask = _brush_mask(ctx.brush_size, ctx.brush_hardness)

    def on_deselect(self, ctx: ToolContext) -> None:
        self._cached_mask = None

    def press(self, layer, x, y):
        if self._cached_mask is None:
            self._cached_mask = _brush_mask(self.ctx.brush_size,
                                            self.ctx.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color,
                     self._cached_mask, self.ctx.brush_opacity, ctx=self.ctx)


# ==========================================================================
# 9. EXPORTING THE TOOL
# ==========================================================================
#
# A tool.py file MUST end with a single `TOOL_CLASS = <YourClass>` line.
# This template does NOT export anything because it is a reference, not a
# plugin. In your own tool.py:
#
#     TOOL_CLASS = MyTool
#
# That's the only contract the loader checks for. After saving your file,
# Layered's hot-reload watcher will pick the change up within ~1 second; no
# restart needed.
