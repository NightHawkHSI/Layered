<div align="center">

<br/>

<img src="Icon.png" width="110" alt="Layered logo"/>

<br/>

# LAYERED

### Modern Python image & game-asset editor

*Real-time canvas · Non-destructive layers · Plugin-powered workflow*

<br/>

[![Release](https://img.shields.io/github/v/release/NightHawkHSI/Layered?style=for-the-badge&label=Latest%20Release&color=22c55e&labelColor=0d1117)](https://github.com/NightHawkHSI/Layered/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3b82f6?style=for-the-badge&logo=python&logoColor=white&labelColor=0d1117)](https://python.org)
[![PyQt6](https://img.shields.io/badge/PyQt6-Qt%20Framework-41cd52?style=for-the-badge&logo=qt&logoColor=white&labelColor=0d1117)](https://pypi.org/project/PyQt6/)
[![License](https://img.shields.io/github/license/NightHawkHSI/Layered?style=for-the-badge&labelColor=0d1117&color=a855f7)](LICENSE)

<br/>

[![Download](https://img.shields.io/badge/⬇%20%20Download%20Now-Latest%20Release-22c55e?style=for-the-badge&labelColor=166534)](https://github.com/NightHawkHSI/Layered/releases/latest)
[![Bug Report](https://img.shields.io/badge/🐞%20%20Report%20a%20Bug-Open%20Issue-ef4444?style=for-the-badge&labelColor=7f1d1d)](https://github.com/NightHawkHSI/Layered/issues/new?labels=bug)
[![Feature Request](https://img.shields.io/badge/💡%20%20Request%20Feature-Open%20Issue-3b82f6?style=for-the-badge&labelColor=1e3a5f)](https://github.com/NightHawkHSI/Layered/issues/new?labels=enhancement)
[![Plugin Docs](https://img.shields.io/badge/🔌%20%20Plugin%20API-Read%20Docs-a855f7?style=for-the-badge&labelColor=3b0764)](docs/PLUGIN_API.md)
[![Brush Docs](https://img.shields.io/badge/🖌%20%20Build%20a%20Brush-Read%20Guide-f59e0b?style=for-the-badge&labelColor=78350f)](docs/build_brush.md)

<br/>

![Stars](https://img.shields.io/github/stars/NightHawkHSI/Layered?style=flat-square&label=⭐%20Stars&color=facc15&labelColor=1c1917)
![Forks](https://img.shields.io/github/forks/NightHawkHSI/Layered?style=flat-square&label=🍴%20Forks&color=fb923c&labelColor=1c1917)
![Downloads](https://img.shields.io/github/downloads/NightHawkHSI/Layered/total?style=flat-square&label=📦%20Downloads&color=60a5fa&labelColor=1c1917)
![Issues](https://img.shields.io/github/issues/NightHawkHSI/Layered?style=flat-square&label=🔴%20Issues&color=f87171&labelColor=1c1917)
![Last Commit](https://img.shields.io/github/last-commit/NightHawkHSI/Layered?style=flat-square&label=🕐%20Last%20Commit&labelColor=1c1917)
![Repo Size](https://img.shields.io/github/repo-size/NightHawkHSI/Layered?style=flat-square&label=💾%20Size&labelColor=1c1917)
[![Views](https://komarev.com/ghpvc/?username=NightHawkHSI&repo=Layered&style=flat-square&label=👁%20Views&color=34d399&labelColor=1c1917)](https://github.com/NightHawkHSI/Layered)

</div>

<br/>

![Preview](https://i.imgur.com/UUjaV8f.png)

<br/>

---

## 📖 Table of Contents

| | |
|---|---|
| [🖼 What is Layered?](#-what-is-layered) | [🧩 Blend Modes](#-blend-modes) |
| [✨ Features](#-features) | [🪵 Logging & Crash Reports](#-logging--crash-reports) |
| [🚀 Quick Start](#-quick-start) | [📦 Building a Standalone EXE](#-building-a-standalone-exe) |
| [🔌 Bundled Plugins](#-bundled-plugins) | [🤝 Contributing](#-contributing) |
| [🗂 Project Structure](#-project-structure) | [📄 License](#-license) |
| [✍️ Writing a Plugin](#️-writing-a-plugin) | [🖌 Brush Presets & Custom Tools](#-brush-presets--custom-tools) |

---

## 🖼 What is Layered?

**Layered** is an open-source image and game-asset editor built in Python with PyQt6, inspired by Paint.NET. It delivers a familiar non-destructive workflow — draw, stack layers, blend, export — without ever leaving your Python toolchain.

> **Built for game developers.** Export every layer as its own PNG alongside a `manifest.json` carrying offsets, blend modes, and visibility — so your engine can reassemble the scene at runtime.

---

## ✨ Features

<details open>
<summary><b>🎨 Drawing Toolkit</b></summary>
<br/>

Brush · Eraser · Fill Bucket · Line · Rectangle · Ellipse · Color Picker · Text

Paint assets from scratch or retouch imports with a full suite of drawing primitives.

</details>

<details open>
<summary><b>🗂 Non-Destructive Layers</b></summary>
<br/>

- Per-layer **opacity** and **visibility** toggle
- **12 blend modes** — Normal, Multiply, Screen, Overlay, Soft Light, Darken, Lighten, Add, Subtract, Difference, Color, Saturation
- Reorder, rename, duplicate, and group layers
- Original pixel data is **never** destroyed — every operation is fully reversible

</details>

<details open>
<summary><b>↶ Full Undo / History</b></summary>
<br/>

Every brush stroke, filter, and layer operation is tracked. Browse the history panel and jump to any prior state instantly.

</details>

<details open>
<summary><b>📦 Export Formats</b></summary>
<br/>

| Format | Description |
|---|---|
| **PNG / JPEG / WEBP** | Flattened composite export |
| **Per-layer PNG + `manifest.json`** | Offsets, blend modes, visibility, opacity — game-engine ready |
| **Multi-tab Projects** | Work on several files simultaneously |

</details>

<details open>
<summary><b>🔌 Plugin System</b></summary>
<br/>

Drop a `.py` file into `Plugins/` and it's live. Plugins can register **tools, filters, or menu actions**, declare typed settings (auto-generated dialog), and run fully sandboxed — a crashing plugin gets logged and isolated while the editor keeps running.

</details>

<details open>
<summary><b>📋 Logging & Diagnostics</b></summary>
<br/>

- `logs/layered.log` — full session activity
- `logs/errors/` — per-crash reports with stack trace + context
- In-app **Console** panel mirrors log output live

</details>

---

## 🚀 Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/NightHawkHSI/Layered.git
cd Layered

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch
python main.py
```

**Requirements:** Python `3.9+` · `PyQt6 >= 6.6` · `Pillow >= 10.0` · `numpy >= 1.26`

> 💡 **No Python?** Grab the prebuilt Windows binary from the [Releases page](https://github.com/NightHawkHSI/Layered/releases/latest) — no setup needed.

---

## 🔌 Bundled Plugins

Layered ships with **17+ working plugins** in `Plugins/` — ready to use or read as templates.

| Plugin | Type | Description |
|---|:---:|---|
| `grayscale` | 🔵 Filter | Desaturate to grayscale |
| `invert` | 🔵 Filter | Invert RGB / per-channel |
| `brightness_contrast` | 🔵 Filter | Brightness + contrast sliders |
| `sharpen` | 🔵 Filter | Unsharp mask sharpening |
| `posterize` | 🔵 Filter | Reduce color levels |
| `gradient_map` | 🔵 Filter | Remap luminance to a gradient |
| `color_replace` | 🔵 Filter | Swap one color for another |
| `outline_filter` | 🔵 Filter | Edge outline effect |
| `glow_filter` | 🔵 Filter | Soft outer glow |
| `drop_shadow` | 🔵 Filter | Drop shadow with offset & blur |
| `normal_map` | 🔵 Filter | Generate normal map from height |
| `background_remove` | 🔵 Filter | Knock out flat / chroma background |
| `tile_fix` | 🔵 Filter | Make textures seamless |
| `pixel_art_resize` | 🔵 Filter | Nearest-neighbor upscale |
| `crop_tool` | 🟠 Action | Crop canvas to selection |
| `flip_tool` | 🟠 Action | Flip horizontal / vertical |
| `grid_overlay` | 🟠 Action | Toggle grid overlay |

---

## 🗂 Project Structure

```
Layered/
├── 📄 main.py                    # Entry point
├── 📄 requirements.txt
├── 📄 build.bat                  # PyInstaller one-file build (Windows)
├── 🖼 Icon.png / Icon.ico
│
├── 📁 app/
│   ├── main_window.py            # Menus, docks, plugin wiring
│   ├── 📁 core/                  # Domain model
│   │   ├── layer.py              #   Layer + LayerStack
│   │   ├── project.py            #   .layered project document
│   │   ├── history.py            #   Undo / redo stack
│   │   ├── blending.py           #   Blend-mode math (NumPy / numba)
│   │   ├── image_ops.py          #   Pixel ops (fill, transforms, etc.)
│   │   └── adjustments.py        #   Adjustment-layer math
│   ├── 📁 render/                # Compositing surfaces
│   │   ├── canvas.py             #   Interactive canvas widget
│   │   ├── gpu_renderer.py       #   moderngl GPU compositor (opt-in)
│   │   └── tile_renderer.py      #   Tiled CPU compositor
│   ├── 📁 io/                    # Persistence
│   │   ├── export.py             #   Composite + per-layer export
│   │   ├── project_io.py         #   .layered file save / load
│   │   ├── session.py            #   Multi-document session state
│   │   └── brush_loader.py       #   Brush-preset discovery from Brushes/
│   ├── 📁 plugins/               # Plugin system
│   │   ├── plugin_api.py         #   Public plugin API
│   │   ├── plugin_loader.py      #   Plugin discovery + sandbox
│   │   ├── tool_loader.py        #   Tool discovery from Plugins/Brushes/
│   │   └── tools.py              #   Tool base class + ToolContext + helpers
│   ├── 📁 app_ui/                # App-shell support
│   │   ├── theme.py              #   Dark / light theme engine
│   │   ├── preferences.py        #   User preferences (prefs.json)
│   │   └── logger.py             #   Logging + crash reporter
│   ├── 📁 controllers/           # History / paste / selection controllers
│   └── 📁 ui/                    # Qt panels (layers, tools, color, history,
│                                 #   text, console, project tabs, dialogs)
│
├── 📁 Plugins/                   # ← Drop your plugins here
│   ├── Brushes/                  #   Tool plugins, grouped by folder
│   │   ├── _shared.py            #   One-stop import for every brush
│   │   └── <Category>/<Tool>/    #   Each tool is a folder
│   │       ├── tool.py           #   Required — defines TOOL_CLASS = MyTool
│   │       └── tool.json         #   Optional — display name, id, icon, category override
│   └── *.py                      #   Filter / action plugins (flat .py files)
│
├── 📁 Brushes/                   # ← Brush presets (size/hardness/opacity/...)
├── 📁 docs/
│   ├── PLUGIN_API.md             # Full plugin API reference
│   └── build_brush.md            # How to build a brush (folder layout, lifecycle, helpers)
└── 📁 logs/                      # Generated at runtime
```

---

## ✍️ Writing a Plugin

Drop a `.py` file in `Plugins/` and subclass `Plugin` — that's it.

```python
# Plugins/my_filter.py
from PIL import Image, ImageOps
from app.plugins.plugin_api import Plugin, PluginContext


class GrayscalePlugin(Plugin):
    name    = "Grayscale"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter("Grayscale", self.apply)

    @staticmethod
    def apply(image: Image.Image) -> Image.Image:
        return ImageOps.grayscale(image.convert("RGB")).convert("RGBA")
```

### Registration Surfaces

| Kind | Where it appears | Method |
|---|---|---|
| **Tool** | Toolbox panel | `ctx.register_tool(name, Tool)` |
| **Filter** | `Filters` menu | `ctx.register_filter(name, fn, settings=...)` |
| **Action** | `Plugins` menu | `ctx.register_action(name, fn, settings=...)` |

Filters and actions accept typed `Setting` specs — `int`, `float`, `bool`, `choice`, `color`, `string` — and the host auto-generates the settings dialog, passing values as keyword arguments.

📘 See [`docs/PLUGIN_API.md`](docs/PLUGIN_API.md) for the full API surface and `invert.py` for a complete settings example.

---

## 🖌 Brush Presets & Custom Tools

Tools and brush presets live in two separate trees:

| Folder | Drives | Layout |
|---|---|---|
| `Plugins/Brushes/` | The **Tools dock** — every group folder becomes a split-button with its sub-tools in a dropdown | `<Group>/<Tool>/tool.py` |
| `Brushes/` | The **brush preset picker** — preset JSON files per category | `<Category>/<preset>.json` |

### Adding a brush preset

```json
// Brushes/Inking/04_marker.json
{ "name": "Marker", "icon": "🖊", "size": 20, "hardness": 0.95, "opacity": 1.0, "spacing": 0.05 }
```

### Adding a custom tool

Every brush is a folder under `Plugins/Brushes/<Category>/<ToolName>/` with a
`tool.py` (and optional `tool.json`). Each `Tool` subclass declares its own
`icon`, `shortcut`, and `build_ui()` — settings render in the per-tool
settings toolbar at the top of the window.

```python
# Plugins/Brushes/Basic/Brush/tool.py
import importlib.util as _iu, sys as _sys
from pathlib import Path as _P
_KEY = "_layered_brushes_shared"
if _KEY not in _sys.modules:
    _spec = _iu.spec_from_file_location(_KEY, _P(__file__).resolve().parents[2] / "_shared.py")
    _mod = _iu.module_from_spec(_spec); _sys.modules[_KEY] = _mod; _spec.loader.exec_module(_mod)
_sh = _sys.modules[_KEY]

Tool = _sh.Tool; Layer = _sh.Layer
build_brush_settings_ui = _sh.build_brush_settings_ui


class BrushTool(Tool):
    name, tool_id = "Brush", "brush"
    icon, shortcut = "🖌", "B"
    is_default = True

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.brush_size, self.brush_hardness, self.brush_opacity = 20, 0.8, 1.0

    def build_ui(self, parent, ctx):
        return build_brush_settings_ui(self, parent,
            fields=("size", "hardness", "opacity"))

    def press(self, layer, x, y):   ...
    def move(self, layer, x, y):    ...
    def release(self, layer, x, y): self._last_pt = None


TOOL_CLASS = BrushTool
```

`Plugins/Brushes/_shared.py` re-exports stdlib, PIL, PyQt6, painting helpers,
`SliderField`, `build_brush_settings_ui`, and the `Tool`/`Layer`/`ToolPhase`
bases — one import covers every brush.

📘 Full guide with class-attr reference, lifecycle methods, painting helpers,
and shape/selection bases: [`docs/build_brush.md`](docs/build_brush.md).

---

## 🧩 Blend Modes

| Mode | Effect | Best For |
|---|---|---|
| **Normal** | Standard alpha compositing | Everything |
| **Multiply** | Darkens — multiplies values | Shadows, tinting |
| **Screen** | Lightens — inverts multiply | Glows, highlights |
| **Overlay** | Contrast boost (multiply + screen) | Detail enhancement |
| **Soft Light** | Gentle dodge / burn driven by the top layer | Subtle shading |
| **Darken** | Keeps the darker pixel | Soft shadows |
| **Lighten** | Keeps the lighter pixel | Soft highlights |
| **Add** | Brightens additively (linear dodge) | Bloom, fire, neon |
| **Subtract** | Darkens subtractively | Dark burn effects |
| **Difference** | Highlights where layers differ | Masking, debug |
| **Color** | Hue + saturation of top, luma of base | Recoloring, tinting |
| **Saturation** | Saturation of top, hue + luma of base | Vibrance tweaks |

> All modes operate on **premultiplied RGBA** via NumPy in `app/core/blending.py` (numba-accelerated when available).

---

## 🪵 Logging & Crash Reports

| Location | Contents |
|---|---|
| `logs/layered.log` | Full session activity, INFO+ |
| `logs/errors/<timestamp>.txt` | Stack trace + context per crash |
| In-app **Console** panel | Live mirror of the log stream |

Plugins get their own sandboxed logger (`layered.plugin.<name>`) — use `ctx.logger` instead of `print` so output lands in both the log file and the console panel.

---

## 📦 Building a Standalone EXE

Windows one-file build via PyInstaller:

```bash
build.bat
```

Output drops in `GitHub/Release/`. The bundled `Plugins/`, `Brushes/`, and `Icon.ico` folders are picked up automatically.

---

## 🤝 Contributing

1. **Fork** the repo and create a branch: `git checkout -b feature/my-thing`
2. **Make changes** — keep functions small, prefer Pillow / NumPy over hand-rolled loops
3. **Test** — run the app and verify nothing regressed
4. **Open a PR** with a clear description of *what* changed and *why*

Bug reports and feature requests live in [Issues](https://github.com/NightHawkHSI/Layered/issues). All contributions are welcome!

---

## 📄 License

Distributed under the terms described in [LICENSE](LICENSE).

---

<div align="center">

<br/>

**Built with Python · Powered by PyQt6 & Pillow**

<br/>

[![Plugin API](https://img.shields.io/badge/🔌%20Plugin%20API-Docs-a855f7?style=flat-square&labelColor=1c1917)](docs/PLUGIN_API.md)
[![Build a Brush](https://img.shields.io/badge/🖌%20Build%20a%20Brush-Guide-f59e0b?style=flat-square&labelColor=1c1917)](docs/build_brush.md)
[![Issues](https://img.shields.io/badge/🐞%20Issues-Tracker-ef4444?style=flat-square&labelColor=1c1917)](https://github.com/NightHawkHSI/Layered/issues)
[![Releases](https://img.shields.io/badge/📦%20Releases-Changelog-22c55e?style=flat-square&labelColor=1c1917)](https://github.com/NightHawkHSI/Layered/releases)

<br/>

*If Layered saved you time, consider leaving a ⭐ — it helps others find the project!*

</div>
