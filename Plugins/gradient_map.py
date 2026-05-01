"""Gradient map — remap luminance to a 2-color gradient. Great for stylising sprites."""
import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


class GradientMapPlugin(Plugin):
    name = "Gradient Map"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Gradient Map",
            self.apply,
            settings=[
                Setting(name="dark", type="color", default=(20, 20, 60, 255), label="Dark color"),
                Setting(name="light", type="color", default=(255, 220, 120, 255), label="Light color"),
                Setting(name="preserve_alpha", type="bool", default=True, label="Preserve alpha"),
            ],
        )
        ctx.logger.info("Gradient Map registered")

    def apply(self, image: Image.Image, *,
              dark=(20, 20, 60, 255), light=(255, 220, 120, 255),
              preserve_alpha: bool = True) -> Image.Image:
        img = image.convert("RGBA")
        arr = np.asarray(img, dtype=np.float32)
        # ITU-R BT.601 luma.
        lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]) / 255.0
        d = np.array(dark, dtype=np.float32)
        l = np.array(light, dtype=np.float32)
        out = d[None, None, :] * (1.0 - lum)[..., None] + l[None, None, :] * lum[..., None]
        if preserve_alpha:
            out[..., 3] = arr[..., 3]
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")
