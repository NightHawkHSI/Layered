<div align="center">

# 🔌 Plugins

**Drop a `.py` file here and Layered picks it up automatically — no config needed.**

[![Plugin API Docs](https://img.shields.io/badge/📖%20Plugin%20API-Full%20Reference-a855f7?style=flat-square&labelColor=1c1917)](../docs/PLUGIN_API.md)
[![Back to README](https://img.shields.io/badge/←%20Back%20to%20README-22c55e?style=flat-square&labelColor=1c1917)](../README.md)

</div>

---

## 📂 Folder Layout

```
Plugins/
├── 📁 Brushes/        # Tool plugins — each subfolder is a Tools-dock group
│   ├── Paint/         #   Brush · Eraser · Fill · Gradient
│   ├── Draw/          #   Line · Rectangle · Ellipse
│   ├── Shapes/        #   Triangle · Star · Pentagon · Diamond · Hexagon
│   ├── Lines/         #   Arrow · Curve · Dashed Line
│   ├── Custom Brushes/#   Spray · Square Brush · Scatter  ← drag & drop new tools here
│   ├── Select/        #   Lasso · Marquee · Magic Wand · Sel Transform
│   ├── Effects/       #   Blur · Sharpen · Smudge · Clone Stamp
│   ├── Transform/     #   Move · Transform
│   ├── Text/          #   Text
│   └── Utility/       #   Picker
├── 📁 Color/          # Brightness, hue shift, palette snap, …
├── 📁 Distortion/     # Warp, wave, glitch sorter, …
├── 📁 ETC/            # Uncategorised plugins
├── 📁 Game Dev/       # Tile fix, normal map, pixel-art resize, …
├── 📁 Lighting/       # Glow, god rays, smart lighting, …
├── 📁 Stylize/        # Outline, pixelate, retro vision, …
└── 📁 Utility/        # Crop, flip, sharpen, plugin builder, …
```

> `Plugins/Brushes/` is loaded by `app.tool_loader`, the rest by
> `app.plugin_loader`. Files prefixed with `_` (e.g. `_builtin_tools.py`)
> are skipped by both loaders — use the underscore prefix for shared
> helpers that should not auto-register.
>
> **To add your own tool:** drop a `<ToolName>/tool.py` folder inside any
> group folder. See
> [`Brushes/Custom Brushes/HOW_TO_ADD_TOOLS.md`](Brushes/Custom%20Brushes/HOW_TO_ADD_TOOLS.md)
> for templates and full instructions.

---

## 🗂 Category Folders

Subfolders **without** an `__init__.py` are treated as **category buckets**, not plugin packages. Any `.py` files inside load with the folder name as their default menu category — so filters and actions group under a submenu automatically, without each plugin needing to pass `category=` explicitly.

| Scenario | Result |
|---|---|
| `Plugins/Color/sepia.py` | Appears under **Filters → Color** |
| `Plugins/Game Dev/Tilesets/tile_fix.py` | Appears under **Filters → Game Dev / Tilesets** |
| Plugin passes `category="Custom"` explicitly | Overrides the folder default |
| Folder **has** `__init__.py` | Treated as a plugin package — inherits the parent folder's category |

> Nested category folders join with ` / ` as a separator (e.g. `Game Dev/Tilesets/` → `"Game Dev / Tilesets"`).

---

## ✍️ Writing a Plugin

Every plugin file must define a class subclassing `Plugin` from `app.plugin_api` and implement `register(self, ctx)`:

```python
# Plugins/Color/my_filter.py
from PIL import Image, ImageOps
from app.plugin_api import Plugin, PluginContext


class GrayscalePlugin(Plugin):
    name    = "Grayscale"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter("Grayscale", self.apply)
        #                                  ↑ folder name "Color" becomes the category automatically

    @staticmethod
    def apply(image: Image.Image) -> Image.Image:
        return ImageOps.grayscale(image.convert("RGB")).convert("RGBA")
```

A plugin can register three surfaces:

| Kind | Where it appears | How to register |
|:---:|---|---|
| 🛠 **Tool** | Tools dock split-button | Drop a `tool.py` (with `TOOL_CLASS = MyTool`) in `Plugins/Brushes/<Group>/<ToolName>/` — no `Plugin` subclass needed |
| 🔵 **Filter** | `Filters` menu | `ctx.register_filter(name, fn, settings=[], category=None)` |
| 🟠 **Action** | `Plugins` menu | `ctx.register_action(name, fn, settings=[], category=None)` |

---

## 🛡 Sandboxing

Layered loads every file under this folder **recursively** at startup. Plugin failures are fully sandboxed:

- Exceptions are logged to `logs/layered.log`
- A crash report is written to `logs/errors/crash-<timestamp>.txt`
- **The editor keeps running** — failed plugins are hidden from menus, not fatal

---

## 📦 Single-file vs Package Plugins

```
Plugins/
├── my_filter.py          # ✅ single-file plugin — just works
└── my_pack/
    ├── __init__.py       # ✅ package plugin — define Plugin subclass here
    └── helpers.py        #    internal helpers, not loaded directly
```

> Files beginning with `_` or `.` are **ignored** by the loader.

---

<div align="center">

See [`docs/PLUGIN_API.md`](../docs/PLUGIN_API.md) for the full API surface, all `PluginContext` methods, and the `Setting` type reference.

The bundled `grayscale.py` and `invert.py` are good starting-point templates.

</div>