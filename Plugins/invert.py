"""Color inversion — example filter plugin with settings + an action."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageChops

from app.plugin_api import Plugin, PluginContext, Setting


class InvertPlugin(Plugin):
    name = "Invert"
    version = "1.1.0"
    author = "Layered"

    def __init__(self):
        self._ctx: PluginContext | None = None

    def register(self, ctx: PluginContext) -> None:
        self._ctx = ctx
        ctx.register_filter(
            "Invert",
            self.apply,
            settings=[
                Setting(
                    name="channels",
                    type="choice",
                    default="RGB",
                    label="Channels",
                    choices=["RGB", "Red", "Green", "Blue", "Alpha"],
                ),
                Setting(
                    name="preserve_alpha",
                    type="bool",
                    default=True,
                    label="Preserve alpha",
                ),
            ],
        )
        ctx.register_action("Invert (action)", self._action_invert)
        ctx.logger.info("Invert plugin registered")

    @staticmethod
    def apply(image: Image.Image, *, channels: str = "RGB", preserve_alpha: bool = True) -> Image.Image:
        rgba = image.convert("RGBA")
        r, g, b, a = rgba.split()

        if channels == "RGB":
            r = ImageChops.invert(r)
            g = ImageChops.invert(g)
            b = ImageChops.invert(b)
        elif channels == "Red":
            r = ImageChops.invert(r)
        elif channels == "Green":
            g = ImageChops.invert(g)
        elif channels == "Blue":
            b = ImageChops.invert(b)
        elif channels == "Alpha":
            if not preserve_alpha:
                a = ImageChops.invert(a)
            else:
                # User asked to invert alpha but also preserve alpha — make it explicit.
                a = ImageChops.invert(a)
                preserve_alpha = False

        out_a = a if preserve_alpha else a
        return Image.merge("RGBA", (r, g, b, out_a))

    def _action_invert(self) -> None:
        if self._ctx is None:
            return
        layer = self._ctx.active_layer()
        if layer is None:
            return
        self._ctx.replace_active_layer_image(self.apply(layer.image))
