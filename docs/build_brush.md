# How to Build a Brush

Every brush is a folder under `Plugins/Brushes/<Category>/<ToolName>/`. The
host scans this tree at startup and after every reload tick.

```
Plugins/Brushes/
  _shared.py                    <- one-stop import for everything
  Basic/                        <- category folder (= group label in UI)
    Brush/
      tool.json                 <- manifest (required if no tool.py)
      tool.py                   <- implementation (required for custom logic)
```

## tool.json

```json
{
    "name":     "Brush",
    "id":       "brush",
    "category": "Basic",
    "icon":     "🖌"
}
```

| Field      | Required | Notes                                                       |
|------------|----------|-------------------------------------------------------------|
| `name`     | yes      | Display label — shown on the button + Tools menu.           |
| `id`       | no       | Stable internal id. Falls back to folder name slug.         |
| `category` | no       | Override parent folder name as group label.                 |
| `class`    | no       | Class name in `app.plugins.tools` if no `tool.py` (built-ins only). |
| `icon`     | no       | Glyph on the button. Overrides `Tool.icon` class attr.      |

Manifest values overwrite class attrs. Either form is enough — pick one.

## tool.py

Always start by importing `_shared`. It re-exports stdlib, PIL, PyQt6,
`Tool`/`ToolContext`/`Layer`, painting helpers, `SliderField`,
`build_brush_settings_ui`, plus lazy `np` (numpy on first access).

```python
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

Tool                    = _sh.Tool
Layer                   = _sh.Layer
_brush_mask             = _sh._brush_mask
_stamp_color            = _sh._stamp_color
_walk                   = _sh._walk
build_brush_settings_ui = _sh.build_brush_settings_ui
```

The host expects `TOOL_CLASS` at module level pointing to your subclass.

## Tool Class

```python
class BrushTool(Tool):
    name       = "Brush"   # display label
    tool_id    = "brush"   # stable id; never use name for lookups
    icon       = "🖌"       # glyph on the button (overridden by tool.json icon)
    shortcut   = "B"       # QKeySequence string ("B", "Shift+E", "Ctrl+Alt+P")
    group      = "Basic"   # category label in tool dock
    role       = ""        # semantic role: "default", "transform", "move", "text", ...
    is_default = True      # one tool per app should set this — returned to after paste
    commit_on  = "release" # "press" | "release" | None — when host calls commit()

    def __init__(self, ctx=None):
        super().__init__(ctx)
        # Each tool owns its own state — DO NOT store on ctx.
        self.brush_size     = 20
        self.brush_hardness = 0.8
        self.brush_opacity  = 1.0
        self.brush_spacing  = 0.05

TOOL_CLASS = BrushTool
```

## Class Attrs Reference

| Attr         | Type   | Purpose                                                          |
|--------------|--------|------------------------------------------------------------------|
| `name`       | `str`  | Display label.                                                   |
| `tool_id`    | `str`  | Stable id for programmatic lookup.                               |
| `icon`       | `str`  | Single-char glyph or short emoji on button.                      |
| `shortcut`   | `str`  | QKeySequence string. Empty = no shortcut.                        |
| `group`      | `str`  | Category label. Set automatically from folder name if blank.     |
| `role`       | `str`  | `"default"`, `"transform"`, `"sel_transform"`, `"move"`, `"text"`. |
| `is_default` | `bool` | Marks the fallback tool returned to after paste/commit.          |
| `commit_on`  | `str`  | `"press"`, `"release"`, or `None` (no auto-commit).              |

## Lifecycle Methods

Subclasses override only what they need. All have no-op defaults.

```python
def on_select(self, ctx):     # tool became active
def on_deselect(self, ctx):   # another tool is taking over

def press(self, layer, x, y):    # mouse down
def move(self, layer, x, y):     # mouse drag
def release(self, layer, x, y):  # mouse up

def cancel(self):                # Esc / pre-empt
def commit(self):                # Enter / auto-fire per commit_on; return action name
def paint_overlay(self, painter, canvas):   # draw guides on top of canvas

def build_ui(self, parent, ctx) -> QWidget | None:  # settings widget for toolbar
```

`x, y` are layer-local integer canvas coords. `layer.image` is a PIL
`RGBA` Image you mutate in place.

## Settings Widget

Brush settings live in the **per-tool settings toolbar** (top of the
window), NOT in the tool dock. Return a widget from `build_ui()` and
the host parents it to the toolbar each time the tool activates.

Use `build_brush_settings_ui` for the standard sliders:

```python
def build_ui(self, parent, ctx):
    return build_brush_settings_ui(
        self, parent,
        fields=("size", "hardness", "opacity", "spacing"),
    )
```

Available field keys: `size`, `hardness`, `opacity`, `spacing`,
`tolerance`, `fill_shape`. The helper reads/writes the matching
`brush_*` / `tolerance` / `fill_shape` attrs on `self`.

For custom UI, build a `QWidget` with `SliderField` / `QSpinBox` /
`QCheckBox` etc. — all re-exported from `_shared`.

## Painting Helpers

```python
mask = _brush_mask(size, hardness)         # PIL "L" image, soft falloff
_stamp_color(layer, x, y, color, mask, opacity, ctx=self.ctx)
_stamp_erase(layer, x, y, mask, opacity, ctx=self.ctx)
for px, py in _walk(p0, p1, spacing):       # interpolate stroke spacing
    ...
_local_filter_stamp(layer, ctx, x, y, ImageFilter.GaussianBlur(2))
```

Selection-aware: every helper respects the active selection mask via
`ctx`. No need to clip yourself.

## Bases for Common Patterns

`_shared.py` exports two base classes that handle the hard parts:

- **`_ShapeTool`** — interactive bbox with Move/Scale/Rotate handles and
  per-frame redraw. Override only `_draw(layer, bbox, angle)`. Used by
  Rectangle, Ellipse, Star, etc.

- **`_SelectionToolBase`** — drag-move support for Marquee / Lasso /
  Magic Wand. Lifts pixels into a floating buffer and restores on cancel.
  Subclasses call `_begin_move_if_inside`, `_continue_move`, `_end_move`,
  `_combine_with_current`, `_commit_mask`.

## Minimal Example

```python
class BrushTool(Tool):
    name, tool_id, icon, shortcut = "Brush", "brush", "🖌", "B"
    is_default = True

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size, self.brush_hardness, self.brush_opacity = 20, 0.8, 1.0
        self.brush_spacing = 0.05

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent,
            fields=("size", "hardness", "opacity", "spacing"))

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        mask = _brush_mask(self.brush_size, self.brush_hardness)
        _stamp_color(layer, x, y, self.ctx.primary_color, mask,
                     self.brush_opacity, ctx=self.ctx)

    def move(self, layer, x, y):
        if self._last_pt is None:
            self._last_pt = (x, y); return
        mask = _brush_mask(self.brush_size, self.brush_hardness)
        spacing = max(1.0, self.brush_size * self.brush_spacing)
        for px, py in _walk(self._last_pt, (x, y), spacing):
            _stamp_color(layer, px, py, self.ctx.primary_color, mask,
                         self.brush_opacity, ctx=self.ctx)
        self._last_pt = (x, y)

    def release(self, layer, x, y):
        self._last_pt = None

TOOL_CLASS = BrushTool
```

## Reload

Edit `tool.py` while the app is running — the file watcher
(`_plugin_watch_timer`) detects mtime changes and reloads automatically.
No restart needed. Adding/removing brushes also picks up live.

## Don'ts

- Don't store brush state on `ctx`. `ctx` is shared across tools.
- Don't hard-code lookups by `name` or `icon` — use `tool_id`.
- Don't construct QWidgets at module top. Construct in `build_ui()`.
- Don't import numpy eagerly. Use `np = _sh.np` only inside methods that
  need it — keeps cold-start fast.
- Don't call `self.canvas.update()` or other host methods from tight
  paint loops — the host repaints after each event automatically.
