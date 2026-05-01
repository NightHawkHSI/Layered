<p align="center">
  <a href="https://github.com/NightHawkHSI/Layered/releases/latest">
    <img src="https://img.shields.io/badge/Download-Layered-blue?style=for-the-badge&logo=github">
  </a>
</p>

<p align="center">
  <img src="https://img.shields.io/github/downloads/NightHawkHSI/Layered/total?style=for-the-badge">
  <img src="https://img.shields.io/github/stars/NightHawkHSI/Layered?style=for-the-badge">
  <img src="https://img.shields.io/github/forks/NightHawkHSI/Layered?style=for-the-badge">
  <img src="https://img.shields.io/github/issues/NightHawkHSI/Layered?style=for-the-badge">
  <img src="https://img.shields.io/github/license/NightHawkHSI/Layered?style=for-the-badge">
  <img src="https://komarev.com/ghpvc/?username=NightHawkHSI&repo=Layered&style=for-the-badge">
</p>

---

A Python-based image and asset editor inspired by Paint.NET, featuring a  
real-time canvas, a non-destructive layer system, and a plugin-driven workflow  
designed for game asset creation.

---

## Features

- **Drawing toolkit** — brush, eraser, fill, line, rectangle, ellipse, color picker  
- **Layer system** — visibility, opacity, blend modes (Normal, Multiply, Screen, Overlay, Darken, Lighten, Add, Subtract, Difference), reorder, rename, grouping support  
- **Export** — save the final composite *or* export every layer as its own PNG with transparency and a `manifest.json` (offsets, blend modes, visibility)  
- **Plugins** — drop a `.py` file in `Plugins/` to add tools, filters, or menu actions  
- **Logging + crash reports** — `logs/layered.log` tracks activity; errors go to `logs/errors/` with full details  
- **Plugin sandbox** — plugin failures are isolated so the main app keeps running  

---

## Quick Start

```bash
pip install -r requirements.txt
python main.py

## Layout

```
main.py
app/
  blending.py        # blend-mode math (NumPy)
  canvas.py          # interactive canvas widget
  export.py          # composite + per-layer export
  layer.py           # Layer + LayerStack
  logger.py          # logging + crash reporter
  main_window.py     # menus, docks, plugin wiring
  plugin_api.py      # public plugin API
  plugin_loader.py   # discovery + sandbox
  tools.py           # built-in drawing tools
  ui/                # Qt panels + console
Plugins/             # drop-in plugins
docs/PLUGIN_API.md   # plugin documentation
logs/                # generated at runtime
```
