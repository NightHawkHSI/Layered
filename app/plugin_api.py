"""Public plugin API.

Plugins subclass `Plugin` and are loaded from the top-level `Plugins/` folder.
The `register()` method is called once at load time with a `PluginContext`
that exposes the editor's canvas, layer stack, tool registry, menus, history,
selection, events, panels, config, clipboard, and a sandboxed logger.

Plugin types:
  * Tool plugins      — register a `Tool` subclass to appear in the toolbox.
  * Effect/Filter     — register a callable that takes a Pillow Image plus
                        keyword settings and returns a new Pillow Image;
                        appears under the Filters menu.
  * Action            — arbitrary callable bound to a menu item; receives
                        keyword settings.

Settings: each filter or action can declare a list of `Setting` specs. When
the user clicks a filter / action in the menus, the host pops a generic
settings dialog built from those specs and passes the values as keyword
arguments to the callback. Plugins with no settings are invoked directly.

Failures inside any plugin call are caught by the loader and routed to the
crash log so the host application stays alive.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from PIL import Image

from .layer import Layer, LayerStack
from .tools import Tool, ToolContext


PluginAction = Callable[..., None]
PluginFilter = Callable[..., Image.Image]

# Event names a plugin can subscribe to via ctx.on(event, fn).
EVENT_LAYER_CHANGED = "layer_changed"        # active layer pixels/metadata changed
EVENT_LAYERS_REORDERED = "layers_reordered"  # add/remove/move
EVENT_ACTIVE_CHANGED = "active_changed"      # active_index changed
EVENT_SELECTION_CHANGED = "selection_changed"
EVENT_TOOL_CHANGED = "tool_changed"
EVENT_PROJECT_CHANGED = "project_changed"    # active project switched/added/closed
EVENT_CANVAS_RESIZED = "canvas_resized"


@dataclass
class Setting:
    """One configurable parameter on a filter or action."""
    name: str
    type: str           # "int" | "float" | "bool" | "choice" | "color" | "string" | "text"
    default: Any = None
    label: str = ""
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[list[str]] = None
    # --- text/code editor hints (used by the settings dialog for type="text") ---
    rows: int = 5                 # visible line count; dialog will size the widget to match
    monospace: bool = False       # if True, renders with a fixed-width font (code editing)


class CanvasLike(Protocol):
    def refresh(self) -> None: ...
    def width(self) -> int: ...
    def height(self) -> int: ...


class PluginHost(Protocol):
    """Host capabilities exposed to plugins via PluginContext.

    The main window implements this. Plugins should not depend on the
    concrete class — use only methods declared here.
    """
    # canvas / layers
    def canvas_size(self) -> tuple[int, int]: ...
    def resize_canvas(self, width: int, height: int) -> None: ...
    def layers(self) -> list[Layer]: ...
    def active_layer(self) -> Optional[Layer]: ...
    def active_index(self) -> int: ...
    def set_active(self, index: int) -> None: ...
    def add_layer(self, image: Optional[Image.Image] = None, name: Optional[str] = None) -> Layer: ...
    def remove_layer(self, index: int) -> Optional[Layer]: ...
    def move_layer(self, src: int, dst: int) -> None: ...
    def get_layer_image(self, index: int) -> Optional[Image.Image]: ...
    def set_layer_image(self, index: int, image: Image.Image) -> None: ...
    def composite(self) -> Image.Image: ...
    def canvas_refresh(self) -> None: ...

    # selection
    def get_selection_mask(self) -> Optional[Image.Image]: ...
    def set_selection_mask(self, mask: Optional[Image.Image]) -> None: ...

    # history
    def commit_history(self, label: str) -> None: ...
    def undo(self) -> None: ...
    def redo(self) -> None: ...

    # events
    def on_event(self, event: str, fn: Callable[..., None]) -> None: ...
    def off_event(self, event: str, fn: Callable[..., None]) -> None: ...
    def emit_event(self, event: str, *args: Any, **kwargs: Any) -> None: ...

    # ui
    def register_panel(self, title: str, widget: Any, area: str = "right") -> None: ...
    def status(self, message: str) -> None: ...
    def progress(self, value: Optional[float], message: str = "") -> None: ...

    # config (per-plugin key/value, persisted)
    def config_get(self, plugin_name: str, key: str, default: Any = None) -> Any: ...
    def config_set(self, plugin_name: str, key: str, value: Any) -> None: ...

    # clipboard / files
    def clipboard_get_image(self) -> Optional[Image.Image]: ...
    def clipboard_set_image(self, image: Image.Image) -> None: ...
    def ask_open_file(self, filters: str = "All Files (*.*)") -> Optional[Path]: ...
    def ask_save_file(self, filters: str = "All Files (*.*)") -> Optional[Path]: ...


@dataclass
class PluginContext:
    """Handed to each plugin at registration time.

    Direct attributes (`layer_stack`, `tool_context`, `canvas`) are kept for
    backwards compatibility. New plugins should prefer the convenience
    methods, which proxy to the host so they stay correct across project
    switches.
    """
    layer_stack: LayerStack
    tool_context: ToolContext
    canvas: CanvasLike
    logger: object
    host: PluginHost = field(repr=False)
    plugin_name: str = ""

    register_tool: Callable[[str, Tool], None] = field(repr=False, default=None)  # type: ignore
    register_filter: Callable[..., None] = field(repr=False, default=None)  # type: ignore
    register_action: Callable[..., None] = field(repr=False, default=None)  # type: ignore

    # --- layers ---
    def active_layer(self) -> Optional[Layer]:
        return self.host.active_layer()

    def active_index(self) -> int:
        return self.host.active_index()

    def set_active(self, index: int) -> None:
        self.host.set_active(index)

    def all_layers(self) -> list[Layer]:
        return self.host.layers()

    def add_layer(self, image: Optional[Image.Image] = None, name: Optional[str] = None) -> Layer:
        return self.host.add_layer(image, name)

    def remove_layer(self, index: int) -> Optional[Layer]:
        return self.host.remove_layer(index)

    def move_layer(self, src: int, dst: int) -> None:
        self.host.move_layer(src, dst)

    def get_layer_image(self, index: int) -> Optional[Image.Image]:
        return self.host.get_layer_image(index)

    def set_layer_image(self, index: int, image: Image.Image) -> None:
        self.host.set_layer_image(index, image)

    def replace_active_layer_image(self, image: Image.Image) -> None:
        layer = self.host.active_layer()
        if layer is None:
            return
        layer.replace_image(image)
        self.host.canvas_refresh()

    def composite(self) -> Image.Image:
        return self.host.composite()

    def canvas_size(self) -> tuple[int, int]:
        return self.host.canvas_size()

    def resize_canvas(self, width: int, height: int) -> None:
        self.host.resize_canvas(width, height)

    def refresh(self) -> None:
        self.host.canvas_refresh()

    # --- selection ---
    def get_selection_mask(self) -> Optional[Image.Image]:
        return self.host.get_selection_mask()

    def set_selection_mask(self, mask: Optional[Image.Image]) -> None:
        self.host.set_selection_mask(mask)

    def clear_selection(self) -> None:
        self.host.set_selection_mask(None)

    # --- history ---
    def commit(self, label: str) -> None:
        self.host.commit_history(label)

    def undo(self) -> None:
        self.host.undo()

    def redo(self) -> None:
        self.host.redo()

    # --- events ---
    def on(self, event: str, fn: Callable[..., None]) -> None:
        self.host.on_event(event, fn)

    def off(self, event: str, fn: Callable[..., None]) -> None:
        self.host.off_event(event, fn)

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        self.host.emit_event(event, *args, **kwargs)

    # --- ui ---
    def register_panel(self, title: str, widget: Any, area: str = "right") -> None:
        self.host.register_panel(title, widget, area)

    def status(self, message: str) -> None:
        self.host.status(message)

    def progress(self, value: Optional[float], message: str = "") -> None:
        self.host.progress(value, message)

    # --- config ---
    def config_get(self, key: str, default: Any = None) -> Any:
        return self.host.config_get(self.plugin_name, key, default)

    def config_set(self, key: str, value: Any) -> None:
        self.host.config_set(self.plugin_name, key, value)

    # --- clipboard / files ---
    def clipboard_get_image(self) -> Optional[Image.Image]:
        return self.host.clipboard_get_image()

    def clipboard_set_image(self, image: Image.Image) -> None:
        self.host.clipboard_set_image(image)

    def ask_open_file(self, filters: str = "All Files (*.*)") -> Optional[Path]:
        return self.host.ask_open_file(filters)

    def ask_save_file(self, filters: str = "All Files (*.*)") -> Optional[Path]:
        return self.host.ask_save_file(filters)


class Plugin:
    """Base class for plugins. Subclass and implement `register`."""

    name: str = "Unnamed Plugin"
    version: str = "0.0.0"
    author: str = ""

    def register(self, ctx: PluginContext) -> None:
        raise NotImplementedError

    def shutdown(self) -> None:
        """Optional cleanup hook called when the application exits."""
        return None