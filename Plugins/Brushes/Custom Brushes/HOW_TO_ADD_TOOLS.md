# Custom Brushes & Tools

Layered tools and brushes are pure plugins.

Drop a folder into `Plugins/Brushes/` and the app automatically loads it
into the Tool panel — no registration, no imports in core, no config files,
and no hardcoded tool lists.

Each top-level folder becomes its own split-button group in the Tool panel
(Paint, Shapes, Select, Effects, Custom Brushes, etc.), and every tool inside
that folder automatically appears in the dropdown for that group.

Tools hot-reload automatically while Layered is running, so most changes are
picked up within ~1 second without restarting the app.

---

# Folder Structure

```text
Plugins/
└── Brushes/
    ├── Paint/                    <- becomes a Tool-panel group
    │   ├── Brush/
    │   │   ├── tool.py          <- REQUIRED
    │   │   └── tool.json        <- OPTIONAL
    │   │
    │   └── Eraser/
    │       └── tool.py
    │
    ├── Shapes/
    │   ├── Rectangle/
    │   ├── Ellipse/
    │   └── Polygon/
    │
    └── Custom Brushes/
        └── MyBrush/
            ├── tool.py
            └── tool.json
```

---

# Required Files

## `tool.py` (required)

Every plugin folder must contain a `tool.py` file that exports:

```python
TOOL_CLASS = MyTool
```

The loader only checks for this variable.

---

## `tool.json` (optional)

Use `tool.json` to override metadata without editing Python.

```json
{
    "name":     "My Brush",
    "icon":     "✨",
    "category": "Custom Brushes"
}
```

Manifest values override class attributes.

---

# Minimal Tool

The smallest possible working tool.

```python
# Plugins/Brushes/Custom Brushes/MyTool/tool.py

from app.tools import Tool
from app.layer import Layer


class MyTool(Tool):
    name      = "My Tool"
    icon      = "🔧"
    commit_on = "release"

    def press(self, layer: Layer, x: int, y: int) -> None:
        pass

    def move(self, layer: Layer, x: int, y: int) -> None:
        pass

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)


TOOL_CLASS = MyTool
```

---

# The `Tool` Base Class

All tools inherit from `app.tools.Tool`.

## Class Attributes

| Attribute | Type | Description |
|---|---|---|
| `name` | `str` | Display name shown in the Tool panel |
| `group` | `str` | Auto-set from the parent folder name |
| `icon` | `str` | Emoji or glyph shown before the tool name |
| `role` | `str` | Semantic tool type (`transform`, `move`, `text`, etc.) |
| `is_default` | `bool` | If True, becomes the startup tool |
| `commit_on` | `str \| None` | `"press"`, `"release"`, or `None` |

---

## Lifecycle Hooks

```python
on_select(ctx)
on_deselect(ctx)
```

Called whenever the tool becomes active or inactive.

Useful for caching expensive resources.

---

## Pointer Events

You can use either API style.

### Modern API

```python
on_mouse_down(ctx, x, y)
on_mouse_drag(ctx, x, y)
on_mouse_up(ctx, x, y)
```

### Legacy API (most built-ins use this)

```python
press(layer, x, y)
move(layer, x, y)
release(layer, x, y)
```

If overriding `release()`, always call:

```python
super().release(layer, x, y)
```

otherwise history snapshots will not fire correctly.

---

# `commit_on`

Controls when Layered records undo history.

| Value | Behavior |
|---|---|
| `"press"` | Snapshot immediately on mouse-down |
| `"release"` | Snapshot on mouse-up (most common) |
| `None` | Tool manually controls commits |

Example:

```python
class FillTool(Tool):
    commit_on = "press"
```

Useful for flood fill, picker, or one-shot operations.

---

# Tool Settings UI

Tools can inject custom controls into the tool-settings strip.

Override:

```python
build_ui(parent, ctx)
```

Return a `QWidget`.

The widget is mounted while the tool is active and destroyed when another
tool is selected.

---

# Inline Settings Example

```python
def build_ui(self, parent, ctx):
    from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
    from app.ui.slider_field import SliderField

    host = QWidget(parent)

    row = QHBoxLayout(host)
    row.setContentsMargins(4, 0, 4, 0)

    row.addWidget(QLabel("Size"))

    slider = SliderField(1, 100, 20)

    slider.valueChanged.connect(
        lambda v: setattr(self, "size", int(v))
    )

    row.addWidget(slider)
    row.addStretch()

    return host
```

---

# Popup Settings Menu

For large tools with many settings, use a dropdown menu instead of inline
sliders so the toolbar stays compact.

```python
def build_ui(self, parent, ctx):
    from PyQt6.QtWidgets import (
        QWidget,
        QHBoxLayout,
        QLabel,
        QMenu,
        QWidgetAction,
        QToolButton,
    )

    from app.ui.slider_field import SliderField

    btn = QToolButton(parent)
    btn.setText("Settings")

    btn.setPopupMode(
        QToolButton.ToolButtonPopupMode.InstantPopup
    )

    menu = QMenu(btn)

    host = QWidget(menu)

    row = QHBoxLayout(host)
    row.addWidget(QLabel("Density"))

    s = SliderField(1, 100, 50)

    s.valueChanged.connect(
        lambda v: setattr(self, "density", int(v))
    )

    row.addWidget(s)

    action = QWidgetAction(menu)
    action.setDefaultWidget(host)

    menu.addAction(action)

    btn.setMenu(menu)

    return btn
```

---

# Shared Helpers (`Plugins/Brushes/_shared.py`)

Most built-in tools load shared helpers from `_shared.py`.

Since `Plugins/Brushes/` is not a Python package, tools load it with
`importlib`.

---

# Standard Shared-Import Preamble

```python
import importlib.util as _iu
import sys as _sys

from pathlib import Path as _P

_SHARED_KEY = "_layered_brushes_shared"

if _SHARED_KEY not in _sys.modules:
    _src = _P(__file__).resolve().parents[2] / "_shared.py"

    _spec = _iu.spec_from_file_location(
        _SHARED_KEY,
        _src
    )

    _mod = _iu.module_from_spec(_spec)

    _sys.modules[_SHARED_KEY] = _mod

    _spec.loader.exec_module(_mod)

_sh = _sys.modules[_SHARED_KEY]
```

Then access helpers:

```python
_walk = _sh._walk
_brush_mask = _sh._brush_mask
_stamp_color = _sh._stamp_color
```

---

# Shared Helper Functions

| Helper | Description |
|---|---|
| `_walk(p0, p1, spacing)` | Generates evenly-spaced stroke points |
| `_brush_mask(size, hardness)` | Cached soft brush alpha mask |
| `_stamp_color(...)` | Paints a coloured brush stamp |
| `_stamp_erase(...)` | Erases alpha using a brush mask |
| `_selection_at_layer(...)` | Returns selection mask in layer space |
| `_clip_layer_to_selection(...)` | Restores pixels outside selection |
| `_local_filter_stamp(...)` | Applies PIL filters with brush masking |

---

# Brush Example

A standard soft round paint brush.

```python
from app.tools import (
    Tool,
    _brush_mask,
    _stamp_color,
    _walk,
)

from app.layer import Layer


class ExampleBrush(Tool):
    name = "Example Brush"
    icon = "🖌"

    commit_on = "release"

    def _spacing(self):
        return max(
            1.0,
            self.ctx.brush_size * self.ctx.brush_spacing
        )

    def press(self, layer: Layer, x: int, y: int):
        self._last_pt = (x, y)

        mask = _brush_mask(
            self.ctx.brush_size,
            self.ctx.brush_hardness
        )

        _stamp_color(
            layer,
            x,
            y,
            self.ctx.primary_color,
            mask,
            self.ctx.brush_opacity,
            ctx=self.ctx,
        )

    def move(self, layer: Layer, x: int, y: int):
        if self._last_pt is None:
            return

        mask = _brush_mask(
            self.ctx.brush_size,
            self.ctx.brush_hardness
        )

        for px, py in _walk(
            self._last_pt,
            (x, y),
            self._spacing()
        ):
            _stamp_color(
                layer,
                px,
                py,
                self.ctx.primary_color,
                mask,
                self.ctx.brush_opacity,
                ctx=self.ctx,
            )

        self._last_pt = (x, y)


TOOL_CLASS = ExampleBrush
```

---

# Shape Tools

Subclass `_ShapeTool` to get:

- Drag-to-create bounding boxes
- 8 resize handles
- Move-inside dragging
- Shift-lock proportions
- Overlay rendering
- History handling
- Commit/cancel behavior

You only implement:

```python
_draw(layer, bbox)
```

---

# Shape Tool Example

```python
from PIL import ImageDraw

_ShapeTool = _sh._ShapeTool


class RectangleTool(_ShapeTool):
    name = "Rectangle"

    def _draw(self, layer, bbox):
        d = ImageDraw.Draw(layer.image)

        if self.ctx.fill_shape:
            d.rectangle(
                bbox,
                fill=self.ctx.primary_color
            )
        else:
            d.rectangle(
                bbox,
                outline=self.ctx.primary_color,
                width=max(1, self.ctx.brush_size)
            )


TOOL_CLASS = RectangleTool
```

---

# Selection Tools

Subclass `_SelectionToolBase` for:

- Marquee selections
- Lasso selections
- Magic wand selections
- Additive/subtractive masks
- Move-inside-selection logic
- Selection commits

Features built in automatically:

- Shift = add
- Alt = subtract
- Move existing selection
- Mask combining
- Selection overlays

---

# Overlay Rendering

Use:

```python
paint_overlay(painter, canvas)
```

to draw temporary visuals above the canvas.

Examples:

- marching ants
- transform boxes
- resize handles
- preview geometry
- guides

Do not modify layer pixels here.

---

# Manual Commit Tools

Tools using:

```python
commit_on = None
```

must manually manage history snapshots.

Useful for:

- transform tools
- text tools
- multi-step editors
- sticker placement
- procedural previews

Implement:

```python
commit()
```

and optionally:

```python
cancel()
```

---

# Tool Icons

Every tool button can display an icon glyph.

## Class Attribute

```python
class MyBrush(Tool):
    name = "My Brush"
    icon = "✨"
```

---

## `tool.json`

```json
{
    "name": "My Brush",
    "icon": "✨"
}
```

Manifest values override Python attributes.

---

# Keyboard Shortcuts

Built-in shortcuts use Photoshop-style bindings.

| Key | Tool |
|---|---|
| `B` | Brush |
| `E` | Eraser |
| `G` | Fill |
| `V` | Move |
| `M` | Marquee |
| `L` | Lasso |
| `W` | Magic Wand |
| `T` | Text |
| `I` | Picker |
| `U` | Shape tools |
| `R` | Blur |
| `S` | Clone Stamp |

Custom tools are not auto-bound.

Add shortcuts in:

```text
app/ui/tool_panel.py
```

inside:

```python
TOOL_SHORTCUTS
```

---

# `ToolContext` Reference

Available through:

```python
self.ctx
```

---

## Colors

| Field | Type |
|---|---|
| `primary_color` | `(r, g, b, a)` |
| `secondary_color` | `(r, g, b, a)` |

---

## Brush Settings

| Field | Type |
|---|---|
| `brush_size` | `int` |
| `brush_hardness` | `float` |
| `brush_opacity` | `float` |
| `brush_spacing` | `float` |

---

## Shape / Fill

| Field | Type |
|---|---|
| `fill_shape` | `bool` |
| `fill_tolerance` | `int` |

---

## Keyboard Modifiers

| Field | Type |
|---|---|
| `shift_held` | `bool` |
| `ctrl_held` | `bool` |
| `alt_held` | `bool` |

---

## Canvas / Selection

| Field | Description |
|---|---|
| `active_layer` | Currently active layer |
| `get_selection()` | Returns current selection |
| `set_selection(sel)` | Sets selection |
| `commit_action(label)` | Pushes history snapshot |
| `get_canvas_size()` | Returns canvas size |

---

# Hot Reloading

Layered watches the `Plugins/Brushes/` folder for changes.

When you:

- edit `tool.py`
- change `tool.json`
- add/remove tool folders

the app reloads tools automatically.

Most changes appear within ~1 second.

---

# Exporting Your Tool

Every plugin must end with:

```python
TOOL_CLASS = MyTool
```

Example:

```python
class StarBrush(Tool):
    name = "Star Brush"

    ...

TOOL_CLASS = StarBrush
```

That is the only required contract for the loader.

---

# Recommended Plugin Categories

```text
Paint
Effects
Shapes
Select
Lines
Text
Procedural
Particles
Custom Brushes
Utility
Experimental
```

You can create any category name you want.

The folder name becomes the Tool-panel group automatically.

---

# Tips

- Store persistent settings on the tool instance, not `ctx`
- Use `_walk()` for smooth strokes
- Use `_brush_mask()` for soft brushes
- Use popup menus for large setting panels
- Use `_ShapeTool` instead of rewriting drag-box logic
- Use `_SelectionToolBase` for selection workflows
- Call `super().release()` when overriding release
- Use `paint_overlay()` for previews instead of modifying the layer live
- Prefer shared helpers over duplicating brush logic
- Keep plugins self-contained so users can drag/drop them easily