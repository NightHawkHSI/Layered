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
├── 📁 Color/          # Brightness, hue shift, palette snap, …
├── 📁 Distortion/     # Warp, wave, glitch sorter, …
├── 📁 ETC/            # Uncategorised plugins
├── 📁 Game Dev/       # Tile fix, normal map, pixel-art resize, …
├── 📁 Lighting/       # Glow, god rays, smart lighting, …
├── 📁 Stylize/        # Outline, pixelate, retro vision, …
└── 📁 Utility/        # Crop, flip, sharpen, plugin builder, …
```

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

| Kind | Where it appears | Method |
|:---:|---|---|
| 🛠 **Tool** | Tool panel | `ctx.register_tool(name, Tool)` |
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

<<<<<<< HEAD
</div>
=======
</div>
>>>>>>> b80716b47cf90514ef7c1938532375535527321b
