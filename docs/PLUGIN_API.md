# Layered Plugin API

Layered loads plugins from the top-level `Plugins/` folder at startup.
Each `.py` file (or package with `__init__.py`) is imported, and any class
that subclasses `Plugin` is instantiated and `register(ctx)` is called.

A plugin can register three things:

| Kind   | Surface                | Method                      |
|--------|------------------------|-----------------------------|
| Tool   | Tool panel button      | `ctx.register_tool(name, Tool)` |
| Filter | "Filters" menu item    | `ctx.register_filter(name, Image -> Image)` |
| Action | "Plugins" menu item    | `ctx.register_action(name, () -> None)` |

## Minimal plugin

```python
from PIL import Image, ImageOps
from app.plugin_api import Plugin, PluginContext

class GrayscalePlugin(Plugin):
    name = "Grayscale"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter("Grayscale", self.apply)

    @staticmethod
    def apply(image: Image.Image) -> Image.Image:
        return ImageOps.grayscale(image.convert("RGB")).convert("RGBA")
```

## PluginContext

`PluginContext` is the only object handed to a plugin. It exposes:

- `layer_stack: LayerStack` — read/modify layers directly if needed.
- `tool_context: ToolContext` — current colors, brush size, fill tolerance.
- `canvas` — has `refresh()`, `width()`, `height()`. Call `refresh()` after
  mutating layer pixels so the view repaints.
- `logger` — sandboxed `logging.Logger` (`layered.plugin.<name>`). Use this
  instead of `print` so output reaches the in-app console and log files.
- `active_layer() -> Optional[Layer]` — currently selected layer.
- `replace_active_layer_image(Image)` — convenience: swap the active layer's
  pixels and refresh the canvas.
- `register_tool(name, Tool)` / `register_filter(name, fn)` /
  `register_action(name, fn)` — covered above.

## Tool plugins

Subclass `app.tools.Tool` and implement `press`, `move`, `release`. Each
takes the layer and canvas-space integer pixel coords:

```python
from app.tools import Tool
from app.plugin_api import Plugin, PluginContext

class DotTool(Tool):
    name = "Dot"
    def press(self, layer, x, y):
        layer.image.putpixel((x, y), self.ctx.primary_color)

class DotPlugin(Plugin):
    name = "Dot tool"
    def register(self, ctx: PluginContext) -> None:
        ctx.register_tool("Dot", DotTool(ctx.tool_context))
```

## Filter plugins

A filter is a callable that takes a Pillow `Image` (RGBA) and returns a new
Pillow `Image`. Mutating the input is allowed but discouraged — return a new
image so undo systems and previews can do diffing later.

## Sandbox + logging

Every plugin call site (`register`, filter, action, shutdown) runs inside a
try/except. On exception:

1. The error is logged at ERROR level on the plugin's sandboxed logger.
2. A full crash report (`logs/errors/crash-<timestamp>.txt`) is written.
3. The host application keeps running.

Failed plugins still appear in the **Plugins** menu marked with their error
message, so you can see at a glance which plugin misbehaved.

## File layout

```
Plugins/
  grayscale.py             # single-file plugin
  invert.py
  my_pack/                 # package plugin
    __init__.py            # must define a Plugin subclass
    helpers.py
```

Files starting with `_` or `.` are ignored.
