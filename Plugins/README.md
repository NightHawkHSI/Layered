# Plugins

Drop a `.py` file (or a package directory with `__init__.py`) in here. Each
plugin file should define a class that subclasses `Plugin` from
`app.plugin_api` and implements `register(self, ctx)`.

The host loads every file in this folder at startup. Plugin failures are
sandboxed: an exception inside a plugin is logged to `logs/layered.log` and a
crash report is written to `logs/errors/`, but the editor stays alive.

See `docs/PLUGIN_API.md` for the full API surface and the bundled
`grayscale.py` and `invert.py` examples.
