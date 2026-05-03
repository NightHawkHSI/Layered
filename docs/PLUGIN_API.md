# Layered Plugin API

Layered loads plugins from the top-level `Plugins/` folder at startup.
Each `.py` file (or package with `__init__.py`) is imported, and any class
that subclasses `Plugin` is instantiated and `register(ctx)` is called.

A plugin can register three things:

| Kind   | Surface                  | Method                                                                  |
|--------|--------------------------|-------------------------------------------------------------------------|
| Tool   | Tool panel button        | `ctx.register_tool(name, Tool)`                                         |
| Filter | "Filters" menu item      | `ctx.register_filter(name, Image -> Image, settings=[], category=None)` |
| Action | "Plugins" menu item      | `ctx.register_action(name, **kwargs -> None, settings=[], category=None)` |

Filters and actions both accept an optional list of `Setting` specs
(see [Settings](#settings)) — when present, the host pops a generated
dialog before invoking the callback and forwards the chosen values as
keyword arguments. They also accept an optional `category=` label that
groups the entry under a submenu in the Filters / Plugins menu.

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

### Core

- `layer_stack: LayerStack` — direct stack access (legacy; prefer the
  convenience methods below so plugins follow the active project).
- `tool_context: ToolContext` — current colors, brush size, fill tolerance.
- `canvas` — has `refresh()`, `width()`, `height()`.
- `logger` — sandboxed `logging.Logger` (`layered.plugin.<name>`).
- `host: PluginHost` — full host capability bag (see below); convenience
  methods on the context proxy to it.
- `plugin_name: str` — name used to scope this plugin's persisted config.
- `register_tool(name, Tool)` /
  `register_filter(name, fn, settings=[], category=None)` /
  `register_action(name, fn, settings=[], category=None)`.

  Pass `category="Color"` (or any label) to nest the entry under that
  submenu in the Filters / Plugins menu. Without `category`, the entry
  sits at the top level. Two plugins that pass the same `category`
  share a submenu.

### Layers

- `active_layer() -> Optional[Layer]`, `active_index() -> int`,
  `set_active(index)`.
- `all_layers() -> list[Layer]` — snapshot list.
- `add_layer(image=None, name=None) -> Layer` — append a new layer.
- `remove_layer(index) -> Optional[Layer]`.
- `move_layer(src, dst)` — reorder.
- `get_layer_image(index) -> Image | None`,
  `set_layer_image(index, image)`.
- `replace_active_layer_image(image)` — convenience for the active layer.
- `composite() -> Image` — flattened view.
- `canvas_size() -> (w, h)`, `resize_canvas(w, h)`, `refresh()`.

### Selection

- `get_selection_mask() -> Image | None` — `L`-mode canvas-sized mask
  (255 inside, 0 outside) or `None` when nothing is selected.
- `set_selection_mask(mask)` — pass `None` to clear.
- `clear_selection()`.

### History

- `commit(label)` — push a snapshot so the user can undo your action.
- `undo()`, `redo()`.

### Events

Subscribe with `ctx.on(event, fn)` and unsubscribe with `ctx.off(event, fn)`.
Available events:

| Event                | Args              | Fired when                              |
|----------------------|-------------------|-----------------------------------------|
| `layer_changed`      | `(active_index,)` | active layer pixels/metadata changed    |
| `layers_reordered`   | `()`              | add/remove/move                         |
| `active_changed`     | `(index,)`        | active index changed                    |
| `selection_changed`  | `()`              | selection mask changed                  |
| `tool_changed`       | `(name,)`         | a tool was activated                    |
| `project_changed`    | `(index,)`        | active project tab switched             |
| `canvas_resized`     | `(w, h)`          | canvas was resized                      |

`ctx.emit(event, *args, **kwargs)` lets plugins fire custom events too.

### UI

- `register_panel(title, widget, area="left"|"right"|"top"|"bottom")` — add
  a docked Qt widget. Pass any `QWidget`.
- `status(message)` — show a status-bar message.
- `progress(value, message="")` — `value` in `[0.0, 1.0]`, or `None` to
  clear.

### Config (persisted via QSettings)

- `config_get(key, default=None)`, `config_set(key, value)`. Keys are
  scoped to this plugin's name. Values must be JSON/QVariant-friendly
  (str, int, float, bool, list, dict). For complex objects, serialize to
  JSON yourself before storing.

### Clipboard / files

- `clipboard_get_image() -> Image | None`,
  `clipboard_set_image(image)`.
- `ask_open_file(filters="...") -> Path | None`,
  `ask_save_file(filters="...") -> Path | None`.

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

```python
ctx.register_filter(
    "Sepia",
    self.apply,
    settings=[Setting(name="strength", type="float", default=1.0,
                      label="Strength", min=0.0, max=1.0, step=0.05)],
    category="Color",
)
```

Filters that share `category="Color"` collapse into a single
**Filters → Color** submenu in menu order.

## Action plugins

An action is any zero-argument callable (it may accept `**kwargs` if it
declares `settings=`). Actions live under the **Plugins** menu and
receive their settings as keyword arguments. Use them for one-shot
operations that don't fit the "Image -> Image" filter shape, such as
"flip the active layer" or "open a tool panel".

```python
ctx.register_action(
    "Flip Horizontal",
    self.flip_h,
    category="Utilities",
)
```

## Settings

Filters and actions can declare a list of `Setting` specs. Each spec
becomes one row in the auto-generated dialog the host shows before
invoking the callback. The chosen values are forwarded as keyword
arguments matching `Setting.name`.

```python
from app.plugin_api import Setting

Setting(
    name="strength",       # kwarg name passed to the callback
    type="float",          # int | float | bool | choice | color | string
    default=1.0,           # initial value
    label="Strength",      # shown in the dialog (falls back to `name`)
    min=0.0, max=1.0,      # numeric clamps (int / float)
    step=0.05,             # spinbox step (int / float)
    choices=["a", "b"],    # required for type="choice"
)
```

Type cheatsheet:

| `type`    | UI                          | Value type             |
|-----------|-----------------------------|------------------------|
| `int`     | `QSpinBox` (clamp + step)   | `int`                  |
| `float`   | `QDoubleSpinBox`            | `float`                |
| `bool`    | checkbox                    | `bool`                 |
| `choice`  | dropdown over `choices=`    | `str`                  |
| `color`   | swatch + color picker       | `(r, g, b, a)` tuple   |
| `string`  | `QLineEdit`                 | `str`                  |

Settings are remembered per-invocation only. Persist values across
sessions with `ctx.config_get` / `ctx.config_set` (see
[Config](#config-persisted-via-qsettings)).

## Sandbox + logging

Every plugin call site (`register`, filter, action, shutdown) runs inside a
try/except. On exception:

1. The error is logged at ERROR level on the plugin's sandboxed logger.
2. A full crash report (`logs/errors/crash-<timestamp>.txt`) is written.
3. The host application keeps running.

Failed plugins are **hidden** from the Filters / Plugins menus so users
only see actionable entries. Inspect the plugin log
(`logs/plugins/<name>.log`) and the crash reports under `logs/errors/`
to debug a load failure. The full registry — including failed entries —
is still available programmatically as `MainWindow.plugins.plugins`.

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
