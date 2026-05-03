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
from typing import Callable, Optional

from PIL import Image

from .logger import get_logger, get_plugin_logger, write_crash_report
from .plugin_api import Plugin, PluginAction, PluginContext, PluginFilter, PluginHost, Setting
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
    plugin: Plugin
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


def discover_plugin_files(plugins_dir: Path) -> list[Path]:
    if not plugins_dir.exists():
        return []
    files: list[Path] = []
    for entry in sorted(plugins_dir.iterdir()):
        if entry.name.startswith(("_", ".")):
            continue
        if entry.is_file() and entry.suffix == ".py":
            files.append(entry)
        elif entry.is_dir() and (entry / "__init__.py").exists():
            files.append(entry / "__init__.py")
    return files


def _load_module(path: Path):
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
    layer_stack,
    tool_context: ToolContext,
    canvas,
    host: Optional[PluginHost] = None,
) -> PluginRegistry:
    registry = PluginRegistry()
    files = discover_plugin_files(plugins_dir)
    log.info("Discovered %d plugin file(s) in %s", len(files), plugins_dir)

    for path in files:
        loaded = LoadedPlugin(name=path.stem, module_path=path, plugin=None)  # type: ignore
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

            def _register_tool(name: str, tool: Tool, _l=loaded, _pl=plugin_logger):
                if not isinstance(tool, Tool):
                    _pl.error("register_tool: %s is not a Tool", name)
                    return
                _l.tools[name] = tool
                registry.tools[name] = tool
                _pl.info("Registered tool %s", name)

            def _register_filter(name: str, fn: PluginFilter, settings: Optional[list[Setting]] = None,
                                 category: Optional[str] = None,
                                 _l=loaded, _pl=plugin_logger):
                wrapped = _wrap_filter(_pl, fn)
                entry = FilterEntry(fn=wrapped, settings=list(settings or []), category=category)
                _l.filters[name] = entry
                registry.filters[name] = entry
                _pl.info("Registered filter %s%s%s", name,
                         f" in {category!r}" if category else "",
                         " with settings" if entry.settings else "")

            def _register_action(name: str, fn: PluginAction, settings: Optional[list[Setting]] = None,
                                 category: Optional[str] = None,
                                 _l=loaded, _pl=plugin_logger):
                wrapped = _wrap_action(_pl, fn)
                entry = ActionEntry(fn=wrapped, settings=list(settings or []), category=category)
                _l.actions[name] = entry
                registry.actions[name] = entry
                _pl.info("Registered action %s%s%s", name,
                         f" in {category!r}" if category else "",
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


def purge_plugin_modules() -> int:
    """Drop all plugin-namespaced entries from sys.modules so the next
    load re-executes their source. Returns the number of entries removed.
    Submodules of plugin packages share the prefix and are dropped too.
    """
    stale = [k for k in sys.modules if k.startswith(PLUGIN_MODULE_PREFIX)]
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
