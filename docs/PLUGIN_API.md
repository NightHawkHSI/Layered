<div align="center">

# 🔌 Layered Plugin API

**Extend Layered with tools, filters, and actions — drop a `.py` file and go.**

[![Plugin Docs](https://img.shields.io/badge/version-1.0-a855f7?style=flat-square&labelColor=1c1917)](.)
[![License](https://img.shields.io/github/license/NightHawkHSI/Layered?style=flat-square&labelColor=1c1917)](../LICENSE)
[![Back to README](https://img.shields.io/badge/←%20Back%20to%20README-22c55e?style=flat-square&labelColor=1c1917)](../README.md)

</div>

---

## 📖 Table of Contents

| | |
|---|---|
| [How Plugins Load](#-how-plugins-load) | [Action Plugins](#-action-plugins) |
| [Minimal Example](#-minimal-example) | [Settings](#-settings) |
| [PluginContext Reference](#-plugincontext-reference) | [Sandbox & Logging](#-sandbox--logging) |
| [Tool Plugins](#-tool-plugins) | [File Layout](#-file-layout) |
| [Filter Plugins](#-filter-plugins) | |

---

## 📂 How Plugins Load

Layered scans the top-level `Plugins/` folder at startup. Every `.py` file (or package with `__init__.py`) is imported, and any class that subclasses `Plugin` is instantiated — then `register(ctx)` is called.

A plugin can register three surfaces:

| Kind | Where it appears | Registration method |
|:---:|---|---|
| 🛠 **Tool** | Tool panel button | `ctx.register_tool(name, Tool)` |
| 🔵 **Filter** | `Filters` menu item | `ctx.register_filter(name, fn, settings=[], category=None)` |
| 🟠 **Action** | `Plugins` menu item | `ctx.register_action(name, fn, settings=[], category=None)` |

Both filters and actions accept:
- An optional `settings=` list to auto-generate a dialog before invoking the callback (values forwarded as keyword arguments)
- An optional `category=` label to group entries under a submenu

---

## ⚡ Minimal Example

```python
# Plugins/grayscale.py
from PIL import Image, ImageOps
from app.plugin_api import Plugin, PluginContext


class GrayscalePlugin(Plugin):
    name    = "Grayscale"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter("Grayscale", self.apply)

    @staticmethod
    def apply(image: Image.Image) -> Image.Image:
        return ImageOps.grayscale(image.convert("RGB")).convert("RGBA")
```

---

## 📋 PluginContext Reference

`PluginContext` is the **only object handed to a plugin**. Everything goes through it.

---

### 🔧 Core

| Attribute / Method | Type | Description |
|---|---|---|
| `layer_stack` | `LayerStack` | Direct stack access *(prefer convenience methods below)* |
| `tool_context` | `ToolContext` | Current colors, brush size, fill tolerance |
| `canvas` | — | Has `refresh()`, `width()`, `height()` |
| `logger` | `logging.Logger` | Sandboxed logger — `layered.plugin.<name>` |
| `host` | `PluginHost` | Full host capability bag |
| `plugin_name` | `str` | Used to scope persisted config |

```python
ctx.register_tool(name, Tool)
ctx.register_filter(name, fn, settings=[], category=None)
ctx.register_action(name, fn, settings=[], category=None)
```

> **Category behaviour:** `category="Color"` nests the entry under a *Filters → Color* submenu. Without a category, the plugin's folder name is used (e.g. `Plugins/Lighting/` → `"Lighting"`). Pass `category=""` to force a top-level entry. Plugins sharing the same category share a submenu.

---

### 🗂 Layers

```python
ctx.active_layer()                    # -> Optional[Layer]
ctx.active_index()                    # -> int
ctx.set_active(index)

ctx.all_layers()                      # -> list[Layer]  (snapshot)
ctx.add_layer(image=None, name=None)  # -> Layer  (appended)
ctx.remove_layer(index)               # -> Optional[Layer]
ctx.move_layer(src, dst)              # reorder

ctx.get_layer_image(index)            # -> Image | None
ctx.set_layer_image(index, image)
ctx.replace_active_layer_image(image) # convenience for active layer

ctx.composite()                       # -> Image  (flattened view)
ctx.canvas_size()                     # -> (w, h)
ctx.resize_canvas(w, h)
ctx.refresh()
```

---

### 🎯 Selection

```python
ctx.get_selection_mask()   # -> L-mode Image (255=selected, 0=not) or None
ctx.set_selection_mask(mask)  # pass None to clear
ctx.clear_selection()
```

---

### ↶ History

```python
ctx.commit("My Action Label")  # push snapshot → user can undo
ctx.undo()
ctx.redo()
```

> Always call `ctx.commit(label)` **before** making changes so undo snapshots the prior state.

---

### 📡 Events

Subscribe with `ctx.on(event, fn)` · Unsubscribe with `ctx.off(event, fn)` · Fire custom events with `ctx.emit(event, *args, **kwargs)`

| Event | Arguments | Fired when |
|---|:---:|---|
| `layer_changed` | `(active_index,)` | Active layer pixels or metadata changed |
| `layers_reordered` | `()` | Layer added, removed, or moved |
| `active_changed` | `(index,)` | Active layer index changed |
| `selection_changed` | `()` | Selection mask changed |
| `tool_changed` | `(name,)` | A tool was activated |
| `project_changed` | `(index,)` | Active project tab switched |
| `canvas_resized` | `(w, h)` | Canvas was resized |

---

### 🖼 UI

```python
ctx.register_panel(title, widget, area="left")  # area: left|right|top|bottom
ctx.status("Processing…")                        # status-bar message
ctx.progress(0.5, "Applying filter…")            # 0.0–1.0, or None to clear
```

---

### 💾 Config *(persisted via QSettings)*

```python
ctx.config_get("my_key", default=None)
ctx.config_set("my_key", value)
```

Keys are automatically scoped to the plugin's name. Values must be JSON/QVariant-friendly (`str`, `int`, `float`, `bool`, `list`, `dict`). Serialize complex objects to JSON before storing.

---

### 📋 Clipboard & Files

```python
ctx.clipboard_get_image()          # -> Image | None
ctx.clipboard_set_image(image)

ctx.ask_open_file(filters="...")   # -> Path | None
ctx.ask_save_file(filters="...")   # -> Path | None
```

---

## 🛠 Tool Plugins

Subclass `app.tools.Tool` and implement `press`, `move`, `release`. Each method receives the **layer** and **canvas-space integer pixel coordinates**.

```python
# Plugins/dot_tool.py
from app.tools import Tool
from app.plugin_api import Plugin, PluginContext


class DotTool(Tool):
    name = "Dot"

    def press(self, layer, x: int, y: int) -> None:
        layer.image.putpixel((x, y), self.ctx.primary_color)

    def move(self, layer, x: int, y: int) -> None:
        pass  # optional — called while dragging

    def release(self, layer, x: int, y: int) -> None:
        pass  # optional — called on mouse-up


class DotPlugin(Plugin):
    name = "Dot Tool"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_tool("Dot", DotTool(ctx.tool_context))
```

---

## 🔵 Filter Plugins

A filter is a callable `Image (RGBA) → Image`. Mutating the input is allowed but **discouraged** — returning a new image lets the undo system and previews do diffing.

```python
# Plugins/sepia.py
from PIL import Image
from app.plugin_api import Plugin, PluginContext, Setting
import numpy as np


class SepiaPlugin(Plugin):
    name    = "Sepia Tone"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Sepia",
            self.apply,
            settings=[
                Setting(
                    name="strength", type="float", default=1.0,
                    label="Strength", min=0.0, max=1.0, step=0.05,
                )
            ],
            category="Color",
        )

    @staticmethod
    def apply(image: Image.Image, *, strength: float = 1.0) -> Image.Image:
        arr = np.array(image.convert("RGBA"), dtype=np.float32) / 255.0
        r = arr[..., 0] * 0.393 + arr[..., 1] * 0.769 + arr[..., 2] * 0.189
        g = arr[..., 0] * 0.349 + arr[..., 1] * 0.686 + arr[..., 2] * 0.168
        b = arr[..., 0] * 0.272 + arr[..., 1] * 0.534 + arr[..., 2] * 0.131
        sepia = np.stack([r, g, b, arr[..., 3]], axis=-1).clip(0, 1)
        result = sepia * strength + arr * (1 - strength)
        return Image.fromarray((result * 255).astype(np.uint8), "RGBA")
```

Filters sharing `category="Color"` collapse into a single **Filters → Color** submenu.

---

## 🟠 Action Plugins

An action is a zero-argument callable (or accepts `**kwargs` when using `settings=`). Actions live in the **Plugins** menu and are ideal for one-shot operations that don't fit the `Image → Image` filter shape.

```python
# Plugins/utilities/flip_tool.py
from PIL import Image
from app.plugin_api import Plugin, PluginContext


class FlipPlugin(Plugin):
    name = "Flip Horizontal"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_action(
            "Flip Horizontal",
            self.flip,
            category="Utilities",
        )

    def flip(self) -> None:
        layer = self.ctx.active_layer()
        if layer is None:
            return
        self.ctx.commit("Flip Horizontal")
        self.ctx.replace_active_layer_image(
            layer.image.transpose(Image.FLIP_LEFT_RIGHT)
        )
        self.ctx.refresh()
```

---

## ⚙️ Settings

Declare a `Setting` list on any filter or action to get an auto-generated dialog. Values are forwarded as keyword arguments matching `Setting.name`.

```python
from app.plugin_api import Setting

Setting(
    name    = "strength",   # kwarg name forwarded to the callback
    type    = "float",      # int | float | bool | choice | color | string
    default = 1.0,          # initial value shown in the dialog
    label   = "Strength",   # human-readable label (falls back to name)
    min     = 0.0,          # numeric lower bound  (int / float only)
    max     = 1.0,          # numeric upper bound  (int / float only)
    step    = 0.05,         # spinbox step          (int / float only)
    choices = ["a", "b"],   # required for type="choice"
)
```

### Type Reference

| `type` | UI widget | Value passed |
|:---:|---|:---:|
| `int` | `QSpinBox` (clamp + step) | `int` |
| `float` | `QDoubleSpinBox` | `float` |
| `bool` | Checkbox | `bool` |
| `choice` | Dropdown over `choices=` | `str` |
| `color` | Color swatch + picker | `(r, g, b, a)` |
| `string` | `QLineEdit` | `str` |

> **Persistence:** Settings are remembered per-invocation only. To persist values across sessions, use `ctx.config_get` / `ctx.config_set`.

---

## 🛡 Sandbox & Logging

Every plugin call site (`register`, filter, action, shutdown) runs inside a `try/except`. On exception:

1. The error is logged at `ERROR` level on the plugin's sandboxed logger
2. A full crash report is written to `logs/errors/crash-<timestamp>.txt`
3. **The host application keeps running** — failed plugins are hidden from menus

```
logs/
├── layered.log                    # full session activity
├── plugins/
│   └── <name>.log                 # per-plugin log stream
└── errors/
    └── crash-<timestamp>.txt      # stack trace + context
```

> The full registry — including failed entries — is still accessible programmatically via `MainWindow.plugins.plugins`.

---

## 📁 File Layout

```
Plugins/
├── grayscale.py          # ✅ single-file plugin
├── invert.py             # ✅ single-file plugin
└── my_pack/              # ✅ package plugin
    ├── __init__.py       #    must define a Plugin subclass
    └── helpers.py
```

> Files beginning with `_` or `.` are **ignored** by the loader.

---

<div align="center">

[![Back to README](https://img.shields.io/badge/←%20Back%20to%20README-22c55e?style=flat-square&labelColor=1c1917)](../README.md)
[![Issues](https://img.shields.io/badge/🐞%20Report%20a%20Bug-Issues-ef4444?style=flat-square&labelColor=1c1917)](https://github.com/NightHawkHSI/Layered/issues/new?labels=bug)
[![Feature Request](https://img.shields.io/badge/💡%20Request%20Feature-Issues-3b82f6?style=flat-square&labelColor=1c1917)](https://github.com/NightHawkHSI/Layered/issues/new?labels=enhancement)

</div>
