"""Dynamic plugin loader.

Scans the top-level `Plugins/` folder for `*.py` files (or packages with
`__init__.py`) and instantiates any `Plugin` subclass found. Each plugin call
runs inside a try/except so plugin failures are isolated from the host app
and routed to the crash log via the sandboxed plugin logger.

Plugins can declare per-action settings; the loader stores them on the
registry so the host can pop a configuration dialog before invoking.
"""
from __future__ import annotations

import importlib.util
import inspect
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Callable, Optional

from PIL import Image

from app.app_ui.logger import get_logger, get_plugin_logger, write_crash_report
from app.core.layer import LayerStack

from .plugin_api import (
    CanvasLike,
    Plugin,
    PluginAction,
    PluginContext,
    PluginFilter,
    PluginHost,
    Setting,
)
from .tools import Tool, ToolContext

log = get_logger("plugins")


@dataclass
class FilterEntry:
    fn: PluginFilter
    settings: list[Setting] = field(default_factory=list)
    category: Optional[str] = None  # submenu label; None = top-level


@dataclass
class ActionEntry:
    fn: PluginAction
    settings: list[Setting] = field(default_factory=list)
    category: Optional[str] = None  # submenu label; None = top-level


@dataclass
class LoadedPlugin:
    name: str
    module_path: Path
    plugin: Optional[Plugin] = None
    tools: dict[str, Tool] = field(default_factory=dict)
    filters: dict[str, FilterEntry] = field(default_factory=dict)
    actions: dict[str, ActionEntry] = field(default_factory=dict)
    error: Optional[str] = None


class PluginRegistry:
    def __init__(self):
        self.plugins: list[LoadedPlugin] = []
        self.tools: dict[str, Tool] = {}
        self.filters: dict[str, FilterEntry] = {}
        self.actions: dict[str, ActionEntry] = {}


def _safe_call(plugin_logger, what: str, fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        plugin_logger.error("%s failed: %s", what, e)
        try:
            write_crash_report(*sys.exc_info())
        except Exception:
            pass
        plugin_logger.debug("Traceback:\n%s", traceback.format_exc())
        return None


def _wrap_filter(plugin_logger, fn: PluginFilter) -> PluginFilter:
    def safe(img: Image.Image, **kwargs) -> Image.Image:
        result = _safe_call(plugin_logger, "filter", fn, img, **kwargs)
        if result is None:
            return img
        return result
    return safe


def _wrap_action(plugin_logger, fn: PluginAction) -> PluginAction:
    def safe(**kwargs) -> None:
        _safe_call(plugin_logger, "action", fn, **kwargs)
    return safe


def discover_plugin_files(plugins_dir: Path) -> list[tuple[Path, Optional[str]]]:
    """Return (path, folder_category) tuples for every plugin under
    `plugins_dir`. A subfolder without `__init__.py` is treated as a
    category bucket — its `.py` files are discovered with the folder
    name as their default category. Nested category folders join with
    " / " (e.g. "Game Dev / Tilesets").
    """
    if not plugins_dir.exists():
        return []
    out: list[tuple[Path, Optional[str]]] = []

    def _scan(d: Path, category: Optional[str]) -> None:
        for entry in sorted(d.iterdir()):
            if entry.name.startswith(("_", ".")):
                continue
            if entry.is_file() and entry.suffix == ".py":
                out.append((entry, category))
            elif entry.is_dir():
                init = entry / "__init__.py"
                if init.exists():
                    # Plugin package — keep current category (don't recurse
                    # into its internals).
                    out.append((init, category))
                else:
                    sub = entry.name if category is None else f"{category} / {entry.name}"
                    _scan(entry, sub)

    _scan(plugins_dir, None)
    return out


def _load_module(path: Path) -> ModuleType:
    mod_name = f"layered_plugin_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build spec for {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


def load_plugins(
    plugins_dir: Path,
    layer_stack: LayerStack,
    tool_context: ToolContext,
    canvas: CanvasLike,
    host: Optional[PluginHost] = None,
    on_progress: Optional[Callable[[int, int, str], None]] = None,
) -> PluginRegistry:
    registry = PluginRegistry()
    files = discover_plugin_files(plugins_dir)
    log.info("Discovered %d plugin file(s) in %s", len(files), plugins_dir)
    total = len(files)

    for idx, (path, folder_category) in enumerate(files):
        if on_progress is not None:
            try:
                on_progress(idx, total, path.stem)
            except Exception:
                pass
        loaded = LoadedPlugin(name=path.stem, module_path=path)
        plugin_logger = get_plugin_logger(path.stem)
        try:
            module = _load_module(path)
        except Exception as e:
            loaded.error = f"import: {e}"
            plugin_logger.error("Import failed: %s", e)
            write_crash_report(*sys.exc_info())
            registry.plugins.append(loaded)
            continue

        plugin_classes = [
            cls for _, cls in inspect.getmembers(module, inspect.isclass)
            if issubclass(cls, Plugin) and cls is not Plugin
        ]

        if not plugin_classes:
            # tool.py files expose TOOL_CLASS, not Plugin — handled by
            # tool_loader, so skip silently without polluting the log.
            if hasattr(module, "TOOL_CLASS"):
                registry.plugins.append(loaded)
                continue
            loaded.error = "no Plugin subclass found"
            plugin_logger.warning(loaded.error)
            registry.plugins.append(loaded)
            continue

        for cls in plugin_classes:
            try:
                instance = cls()
            except Exception as e:
                plugin_logger.error("Constructor failed: %s", e)
                write_crash_report(*sys.exc_info())
                continue

            loaded.plugin = instance
            loaded.name = getattr(instance, "name", path.stem)

            def _register_tool(name: str, tool: Tool, _l=loaded, _pl=plugin_logger) -> None:
                if not isinstance(tool, Tool):
                    _pl.error("register_tool: %s is not a Tool", name)
                    return
                _l.tools[name] = tool
                registry.tools[name] = tool
                _pl.info("Registered tool %s", name)

            def _register_filter(name: str, fn: PluginFilter, settings: Optional[list[Setting]] = None,
                                 category: Optional[str] = None,
                                 _l=loaded, _pl=plugin_logger, _fc=folder_category) -> None:
                wrapped = _wrap_filter(_pl, fn)
                cat = category if category is not None else _fc
                entry = FilterEntry(fn=wrapped, settings=list(settings or []), category=cat)
                _l.filters[name] = entry
                registry.filters[name] = entry
                _pl.info("Registered filter %s%s%s", name,
                         f" in {cat!r}" if cat else "",
                         " with settings" if entry.settings else "")

            def _register_action(name: str, fn: PluginAction, settings: Optional[list[Setting]] = None,
                                 category: Optional[str] = None,
                                 _l=loaded, _pl=plugin_logger, _fc=folder_category) -> None:
                wrapped = _wrap_action(_pl, fn)
                cat = category if category is not None else _fc
                entry = ActionEntry(fn=wrapped, settings=list(settings or []), category=cat)
                _l.actions[name] = entry
                registry.actions[name] = entry
                _pl.info("Registered action %s%s%s", name,
                         f" in {cat!r}" if cat else "",
                         " with settings" if entry.settings else "")

            ctx = PluginContext(
                layer_stack=layer_stack,
                tool_context=tool_context,
                canvas=canvas,
                logger=plugin_logger,
                host=host,  # type: ignore[arg-type]
                plugin_name=loaded.name,
                register_tool=_register_tool,
                register_filter=_register_filter,
                register_action=_register_action,
            )

            _safe_call(plugin_logger, "register", instance.register, ctx)

        registry.plugins.append(loaded)

    log.info(
        "Loaded %d plugin(s); %d tool(s), %d filter(s), %d action(s)",
        len([p for p in registry.plugins if p.plugin is not None]),
        len(registry.tools),
        len(registry.filters),
        len(registry.actions),
    )
    return registry


def shutdown_plugins(registry: PluginRegistry) -> None:
    for loaded in registry.plugins:
        if loaded.plugin is None:
            continue
        plugin_logger = get_plugin_logger(loaded.name)
        _safe_call(plugin_logger, "shutdown", loaded.plugin.shutdown)


PLUGIN_MODULE_PREFIX = "layered_plugin_"
BRUSH_TOOL_MODULE_PREFIX = "_layered_tool_"


def purge_plugin_modules() -> int:
    """Drop all plugin-namespaced entries from sys.modules so the next
    load re-executes their source. Returns the number of entries removed.
    Covers both regular plugin modules (layered_plugin_*) and brush-tool
    modules (_layered_tool_*) so hot-reload picks up changed tool.py files.
    Submodules of plugin packages share the prefix and are dropped too.
    """
    stale = [
        k for k in sys.modules
        if k.startswith(PLUGIN_MODULE_PREFIX)
        or k.startswith(BRUSH_TOOL_MODULE_PREFIX)
    ]
    for k in stale:
        sys.modules.pop(k, None)
    return len(stale)


def snapshot_plugin_files(plugins_dir: Path) -> dict[str, tuple[float, int]]:
    """Return {path: (mtime, size)} for every .py under `plugins_dir`.
    Used to detect changes between watcher ticks. Recursive so package
    internals (helpers.py inside a plugin package) trigger reloads too.
    """
    snap: dict[str, tuple[float, int]] = {}
    if not plugins_dir.exists():
        return snap
    for p in plugins_dir.rglob("*.py"):
        try:
            st = p.stat()
        except OSError:
            continue
        snap[str(p)] = (st.st_mtime, st.st_size)
    return snap
