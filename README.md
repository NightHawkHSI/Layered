# Layered

A Python image and asset editor inspired by Paint.NET. Paint, edit, and
construct layered assets with a real-time canvas, a robust layer system, and
a per-layer export pipeline aimed at game development.

## Features

- **Drawing toolkit** — brush, eraser, fill, line, rectangle, ellipse, color
  picker.
- **Layer system** — visibility, opacity, blend modes (Normal, Multiply,
  Screen, Overlay, Darken, Lighten, Add, Subtract, Difference), reorder,
  rename, group hint.
- **Export** — save the final composite, *or* export every layer as its own
  PNG with preserved transparency and a `manifest.json` describing offsets,
  blend modes, and visibility.
- **Plugins** — drop a `.py` file in `Plugins/` to add tools, filters, or
  menu actions. See `docs/PLUGIN_API.md`.
- **Logging + crash reports** — `logs/layered.log` rolls user actions and
  plugin activity; unhandled exceptions land in `logs/errors/`. An in-app
  console (View dock) mirrors logs in real time.
- **Plugin sandbox** — plugin failures are isolated; the host keeps running
  and the failure is recorded in detail.

## Quick start

```
pip install -r requirements.txt
python main.py
```

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
