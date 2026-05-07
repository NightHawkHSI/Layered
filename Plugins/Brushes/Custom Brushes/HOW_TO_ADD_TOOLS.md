# Custom Brushes & Tools

Drop any folder here to add a new tool to the tool panel automatically.
No registration, no config � just drop the folder in and relaunch.

---

## Folder structure

```
Plugins/Brushes/
    <Category>/              <- becomes a split-button group in the Tools dock
        <ToolName>/
            tool.py          <- only required file � must define TOOL_CLASS
```

---

## 1. Minimal tool

The simplest possible tool: three event methods and `TOOL_CLASS`.

```python
# Plugins/Brushes/Custom Brushes/MyTool/tool.py
from app.tools import Tool
from app.layer import Layer


class MyTool(Tool):
    name      = "My Tool"   # label shown in the tool panel
    icon      = "🔧"         # optional glyph rendered before the name
    commit_on = "release"   # when history is saved: "press" | "release" | None

    def press(self, layer: Layer, x: int, y: int) -> None:
        pass   # called on mouse-down

    def move(self, layer: Layer, x: int, y: int) -> None:
        pass   # called while dragging

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)   # always call super � triggers history


TOOL_CLASS = MyTool
```

---

## 2. Shape tool (drag-to-draw + resize/move handles for free)

Subclass `_ShapeTool` and implement only `_draw()`.
You get a draggable bounding box, eight resize handles, move-inside-to-pan,
Shift-lock proportions, and history � all for free.

```python
# Plugins/Brushes/Shapes/MyShape/tool.py
import importlib.util, sys
from pathlib import Path
from PIL import ImageDraw
from app.layer import Layer

_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_ShapeTool = sys.modules[_K]._ShapeTool


class MyShapeTool(_ShapeTool):
    name = "My Shape"

    def _draw(self, layer: Layer, bbox):
        x0, y0, x1, y1 = bbox          # canvas coordinates
        d = ImageDraw.Draw(layer.image)
        if self.ctx.fill_shape:
            d.rectangle([x0, y0, x1, y1], fill=self.ctx.primary_color)
        else:
            d.rectangle([x0, y0, x1, y1],
                        outline=self.ctx.primary_color,
                        width=max(1, self.ctx.brush_size))


TOOL_CLASS = MyShapeTool
```

---

## 3. Tool with settings (sliders in the tool-settings bar)

Override `build_ui(parent, ctx)` to return a `QWidget`.
It is mounted in the tool-settings toolbar whenever your tool is active
and destroyed when another tool is selected.

Use `SliderField` for numeric values � it is a slider and spinbox kept in
sync, and it fires `valueChanged(int)` on every change.

```python
# Plugins/Brushes/Custom Brushes/MyBrush/tool.py
import importlib.util, sys
from pathlib import Path
from PIL import Image, ImageDraw
from app.layer import Layer
from app.tools import Tool

_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_walk = sys.modules[_K]._walk


class MyBrush(Tool):
    name = "My Brush"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        # Store settings as instance variables so they persist
        # while the tool is active.
        self.my_size = 10

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField

        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)

        row.addWidget(QLabel("Size"))

        # SliderField(min, max, initial, slider_width=px)
        s = SliderField(1, 100, self.my_size, slider_width=120)
        # lambda writes back to the instance so _paint() sees the new value
        s.valueChanged.connect(lambda v: setattr(self, "my_size", int(v)))
        row.addWidget(s)

        row.addStretch()   # push controls to the left
        return host

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._paint(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            return
        spacing = max(1.0, self.my_size * 0.3)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            self._paint(layer, px, py)
        self._last_pt = (x, y)

    def _paint(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        r = self.my_size // 2
        ImageDraw.Draw(layer.image).ellipse(
            [x - ox - r, y - oy - r, x - ox + r, y - oy + r],
            fill=self.ctx.primary_color,
        )


TOOL_CLASS = MyBrush
```

### Adding a popup (dropdown) instead of inline sliders

For tools with many settings, put the controls inside a `QMenu` so the
toolbar stays compact.  See `MagicWand/tool.py` for a complete example.

```python
def build_ui(self, parent, ctx):
    from PyQt6.QtWidgets import (
        QHBoxLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
    )
    from app.ui.slider_field import SliderField

    btn = QToolButton(parent)
    btn.setText("Settings")
    btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    btn.setFixedWidth(90)

    menu  = QMenu(btn)
    host  = QWidget(menu)
    row   = QHBoxLayout(host)
    row.setContentsMargins(8, 6, 8, 6)
    row.addWidget(QLabel("My Value"))

    s = SliderField(1, 100, self.my_value, slider_width=160)
    s.valueChanged.connect(lambda v: setattr(self, "my_value", int(v)))
    row.addWidget(s)

    wa = QWidgetAction(menu)
    wa.setDefaultWidget(host)
    menu.addAction(wa)
    btn.setMenu(menu)
    return btn
```

---

## Tool icons

Every tool button shows an icon glyph before its name so users can scan
the panel by shape, not by reading. Two ways to give a tool an icon:

**1. Class attribute (recommended for code-based tools)**

```python
class MyBrush(Tool):
    name = "My Brush"
    icon = "✨"   # any unicode glyph or emoji
```

**2. `tool.json` manifest (recommended for non-code drop-ins)**

Place a `tool.json` next to your `tool.py`:

```json
{
    "name":     "My Brush",
    "icon":     "✨",
    "category": "Custom Brushes"
}
```

The manifest icon overrides the class attribute, so a user can re-skin
a shipped tool by editing its `tool.json` without touching Python.
If neither is set, the built-in `TOOL_ICONS` table in
`app/ui/tool_panel.py` is checked, then the button falls back to
text-only.

---

## Keyboard shortcuts

The built-in tools register Photoshop-style single-key shortcuts
(B Brush, E Eraser, G Fill, V Move, M Marquee, L Lasso, W Magic Wand,
T Text, I Picker, U Line, Shift+U Rectangle, Alt+U Ellipse, R Blur,
Shift+R Sharpen, Alt+R Smudge, S Clone Stamp, Ctrl+T Transform,
Ctrl+Shift+T Sel Transform). Hovering a tool button shows the active
shortcut in the tooltip.

Shortcuts are defined in `TOOL_SHORTCUTS` at the top of
`app/ui/tool_panel.py`. Custom tools are not auto-bound — if you want
one, add an entry there keyed by your `name`.

---

## Quick-reference: ToolContext fields

| Field | Type | Description |
|---|---|---|
| `self.ctx.primary_color` | `tuple[int,int,int,int]` | Current foreground colour (R, G, B, A) |
| `self.ctx.secondary_color` | `tuple[int,int,int,int]` | Current background colour |
| `self.ctx.brush_size` | `int` | Brush size in pixels |
| `self.ctx.brush_opacity` | `float` | 0.0 to 1.0 |
| `self.ctx.brush_hardness` | `float` | 0.0 (soft) to 1.0 (hard) |
| `self.ctx.brush_spacing` | `float` | Stamp spacing as a fraction of brush size |
| `self.ctx.fill_shape` | `bool` | True when Fill Shape toggle is on |
| `self.ctx.fill_tolerance` | `int` | Fill / magic-wand tolerance 0-255 |
| `self.ctx.shift_held` | `bool` | True while Shift is held |
| `self.ctx.ctrl_held` | `bool` | True while Ctrl is held |
| `self.ctx.alt_held` | `bool` | True while Alt is held |

---

## Helper utilities (from `_builtin_tools.py`)

Load them once at the top of your file using the same `_K` pattern shown
above, then access via `sys.modules[_K]`.

| Name | Signature | What it does |
|---|---|---|
| `_walk` | `(p0, p1, spacing) -> list[tuple]` | Interpolates evenly-spaced stamp positions between two points |
| `_ShapeTool` | base class | Drag-to-draw with resize/move handles |
| `_clip_layer_to_selection` | `(layer, ctx, snapshot)` | Restricts a paint operation to the active selection |
| `_brush_mask` | `(size, hardness) -> Image` | Circular alpha mask for soft-brush stamping |

```python
# Example: using _walk in your own brush
_walk = sys.modules["_layered_builtin_tools"]._walk

def move(self, layer, x, y):
    for px, py in _walk(self._last_pt, (x, y), spacing=self.ctx.brush_size * 0.25):
        self._stamp(layer, px, py)
    self._last_pt = (x, y)
```

