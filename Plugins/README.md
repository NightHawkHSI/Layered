# Plugins

Drop a `.py` file (or a package directory with `__init__.py`) in here. Each
plugin file should define a class that subclasses `Plugin` from
`app.plugin_api` and implements `register(self, ctx)`.

## Category folders

Subfolders without an `__init__.py` are treated as **category buckets**, not
plugin packages. Their `.py` files load with the folder name as the default
menu category, so filters and actions group under a submenu without each
plugin having to pass `category=` explicitly.

Current layout:

```
Plugins/
├── Color/        # brightness, hue shift, palette snap, …
├── Distortion/   # warp, wave, glitch sorter, …
├── ETC/          # uncategorised
├── Game Dev/     # tile fix, normal map, pixel-art resize, …
├── Lighting/     # glow, god rays, smart lighting, …
├── Stylize/      # outline, pixelate, retro vision, …
└── Utility/      # crop, flip, sharpen, plugin builder, …
```

A plugin that passes `category="..."` in its `register_filter` /
`register_action` call overrides the folder default. Nested category
folders join with " / " (e.g. `Game Dev/Tilesets/foo.py` → `Game Dev /
Tilesets`). Folders containing `__init__.py` are still treated as plugin
packages and inherit the parent folder's category instead of becoming
one themselves.

## Sandboxing

The host loads every file under this folder (recursively) at startup.
Plugin failures are sandboxed: an exception inside a plugin is logged to
`logs/layered.log` and a crash report is written to `logs/errors/`, but
the editor stays alive.

See `docs/PLUGIN_API.md` for the full API surface and the bundled
`grayscale.py` and `invert.py` examples.
