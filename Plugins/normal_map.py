"""Normal-map generator (height-from-alpha-or-luminance)."""
import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


class NormalMapPlugin(Plugin):
    name = "Normal Map Generator"
    version = "1.1.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Generate Normal Map",
            self.apply,
            settings=[
                Setting(name="strength", type="float", default=1.0, min=0.1, max=10.0, step=0.1,
                        label="Strength"),
                Setting(name="invert_x", type="bool", default=False, label="Invert X"),
                Setting(name="invert_y", type="bool", default=False, label="Invert Y"),
                Setting(name="source", type="choice", default="luminance",
                        choices=["luminance", "alpha"], label="Height source"),
            ],
            category="Generators",
        )

    def apply(self, image: Image.Image, *,
              strength: float = 1.0, invert_x: bool = False, invert_y: bool = False,
              source: str = "luminance") -> Image.Image:
        rgba = image.convert("RGBA")
        if source == "alpha":
            arr = np.asarray(rgba.split()[3], dtype=np.float32)
        else:
            arr = np.asarray(rgba.convert("L"), dtype=np.float32)
        dx = (np.roll(arr, -1, axis=1) - np.roll(arr, 1, axis=1)) * strength
        dy = (np.roll(arr, -1, axis=0) - np.roll(arr, 1, axis=0)) * strength
        if invert_x:
            dx = -dx
        if invert_y:
            dy = -dy
        dz = np.full_like(arr, 255.0)
        normal = np.stack((dx, dy, dz), axis=2)
        norm = np.linalg.norm(normal, axis=2, keepdims=True)
        normal = normal / (norm + 1e-8)
        rgb = ((normal + 1.0) * 0.5 * 255.0).astype(np.uint8)
        out = Image.fromarray(rgb, mode="RGB").convert("RGBA")
        out.putalpha(rgba.split()[3])
        return out
