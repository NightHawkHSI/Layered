"""Public plugin API.

Plugins subclass `Plugin` and are loaded from the top-level `Plugins/` folder.
The `register()` method is called once at load time with a `PluginContext`
that exposes the editor's canvas, layer stack, tool registry, menus, and a
sandboxed logger.

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
from typing import Any, Callable, Optional, Protocol

from PIL import Image

from .layer import Layer, LayerStack
from .tools import Tool, ToolContext


PluginAction = Callable[..., None]
PluginFilter = Callable[..., Image.Image]


@dataclass
class Setting:
    """One configurable parameter on a filter or action."""
    name: str                                  # kwarg name passed to callback
    type: str                                  # "int" | "float" | "bool" | "choice" | "color" | "string"
    default: Any = None
    label: str = ""                            # shown in dialog; falls back to name
    min: Optional[float] = None
    max: Optional[float] = None
    step: Optional[float] = None
    choices: Optional[list[str]] = None        # for type="choice"


class CanvasLike(Protocol):
    def refresh(self) -> None: ...
    def width(self) -> int: ...
    def height(self) -> int: ...


@dataclass
class PluginContext:
    """Handed to each plugin at registration time."""
    layer_stack: LayerStack
    tool_context: ToolContext
    canvas: CanvasLike
    logger: object  # logging.Logger; typed loosely to keep plugin API tiny.

    register_tool: Callable[[str, Tool], None] = field(repr=False)
    register_filter: Callable[..., None] = field(repr=False)
    register_action: Callable[..., None] = field(repr=False)

    def active_layer(self) -> Optional[Layer]:
        return self.layer_stack.active

    def replace_active_layer_image(self, image: Image.Image) -> None:
        layer = self.layer_stack.active
        if layer is None:
            return
        layer.replace_image(image)
        self.canvas.refresh()


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
