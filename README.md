<div align="center">
<img src="https://img.shields.io/badge/Layered-Image%20Editor-blue?style=for-the-badge&logo=layers&logoColor=white" alt="Layered">
<br/><br/>
A Python-based image and asset editor — real-time canvas, non-destructive layers, plugin-driven.
<br/>
<a href="https://github.com/NightHawkHSI/Layered/releases/latest">
  <img src="https://img.shields.io/badge/⬇ Download-Latest%20Release-2ea44f?style=for-the-badge" alt="Download">
</a>
<br/><br/>
<img src="https://img.shields.io/github/downloads/NightHawkHSI/Layered/total?style=flat-square&label=Downloads&color=blue">
<img src="https://img.shields.io/github/stars/NightHawkHSI/Layered?style=flat-square&label=Stars&color=yellow">
<img src="https://img.shields.io/github/forks/NightHawkHSI/Layered?style=flat-square&label=Forks&color=orange">
<img src="https://img.shields.io/github/issues/NightHawkHSI/Layered?style=flat-square&label=Issues&color=red">
<img src="https://img.shields.io/github/license/NightHawkHSI/Layered?style=flat-square&label=License&color=green">
<img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square&logo=python&logoColor=white">
</div>

What is Layered?
Layered is an open-source image and game asset editor built in Python, inspired by Paint.NET. It gives you a familiar non-destructive workflow — draw, stack layers, blend, export — without leaving your Python toolchain.
It's built for game asset creation: export every layer as its own PNG with a manifest.json carrying offsets and blend data, so your game engine can reassemble them at runtime.

Features
🎨 Drawing Toolkit
Brush, eraser, fill, line, rectangle, ellipse, and colour picker — everything you need to paint assets from scratch.
🗂 Layer System

Toggle visibility and adjust opacity per layer
9 blend modes — Normal, Multiply, Screen, Overlay, Darken, Lighten, Add, Subtract, Difference
Reorder, rename, and group layers
Fully non-destructive — original data is never modified

📦 Export

Save the final flattened composite as a single image
Export every layer individually as PNG with transparency
Generates a manifest.json with offsets, blend modes, and visibility state for each layer

🔌 Plugin System
Drop a .py file into the Plugins/ folder to add new tools, filters, or menu actions. Plugins run in an isolated sandbox — if one crashes, the rest of the app keeps running.
📋 Logging & Crash Reports

logs/layered.log tracks all activity
Errors are captured to logs/errors/ with full stack traces and context


Quick Start
bash# 1. Clone the repo
git clone https://github.com/NightHawkHSI/Layered.git
cd Layered

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run
python main.py

Requirements: Python 3.9+, pip


Project Structure
Layered/
├── main.py
├── requirements.txt
├── app/
│   ├── blending.py        # Blend-mode math (NumPy)
│   ├── canvas.py          # Interactive canvas widget
│   ├── export.py          # Composite + per-layer export
│   ├── layer.py           # Layer + LayerStack classes
│   ├── logger.py          # Logging + crash reporter
│   ├── main_window.py     # Menus, docks, plugin wiring
│   ├── plugin_api.py      # Public plugin API surface
│   ├── plugin_loader.py   # Plugin discovery + sandbox
│   ├── tools.py           # Built-in drawing tools
│   └── ui/                # Qt panels + console
├── Plugins/               # Drop your plugins here
├── docs/
│   └── PLUGIN_API.md      # Plugin documentation
└── logs/                  # Generated at runtime

Writing a Plugin
Drop a .py file in Plugins/ and implement the register hook:
python# Plugins/my_filter.py
from app.plugin_api import PluginAPI

def register(api: PluginAPI):
    api.add_menu_action(
        menu="Filters",
        label="Invert Colours",
        callback=lambda: api.apply_to_active_layer(invert)
    )

def invert(layer_data):
    return 255 - layer_data
See docs/PLUGIN_API.md for the full API reference.

Blend Modes Reference
ModeEffectNormalStandard alpha compositingMultiplyDarkens — good for shadowsScreenLightens — good for glowsOverlayContrast boostDarkenKeeps darker pixelLightenKeeps lighter pixelAddBrightens additivelySubtractDarkens subtractivelyDifferenceHighlights where layers differ

Contributing

Fork the repo and create a branch: git checkout -b feature/my-thing
Make your changes and add tests if applicable
Open a pull request with a clear description of what you changed and why

Bug reports and feature requests go in Issues.

Roadmap

 Selection tools (marquee, lasso, magic wand)
 Text tool with font support
 Animation timeline for sprite sheets
 More blend modes (Hue, Saturation, Color, Luminosity)
 Theme support (light / dark)
 Plugin marketplace / registry


<div align="center">
Made with Python · <a href="https://github.com/NightHawkHSI/Layered/blob/main/LICENSE">License</a> · <a href="https://github.com/NightHawkHSI/Layered/issues">Issues</a> · <a href="docs/PLUGIN_API.md">Plugin Docs</a>
</div>
