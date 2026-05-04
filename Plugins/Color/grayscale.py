"""Grayscale filter — example image filter plugin with settings."""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps

from app.plugin_api import Plugin, PluginContext, Setting


class GrayscalePlugin(Plugin):
    name = "Grayscale"
    version = "1.1.0"
    author = "Layered"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Grayscale",
            self.apply,
            settings=[
                Setting(
                    name="method",
                    type="choice",
                    default="Luminance",
                    label="Method",
                    choices=["Luminance", "Average", "Lightness"],
                ),
                Setting(
                    name="strength",
                    type="float",
                    default=1.0,
                    label="Strength",
                    min=0.0, max=1.0, step=0.05,
                ),
            ],
            category="Color",
        )
        ctx.logger.info("Grayscale plugin registered")

    @staticmethod
    def apply(image: Image.Image, *, method: str = "Luminance", strength: float = 1.0) -> Image.Image:
        rgba = image.convert("RGBA")
        rgb = rgba.convert("RGB")

        if method == "Average":
            arr = np.asarray(rgb, dtype=np.uint16)
            gray_arr = (arr.sum(axis=-1) // 3).astype(np.uint8)
            gray = Image.fromarray(gray_arr, mode="L").convert("RGB")
        elif method == "Lightness":
            arr = np.asarray(rgb, dtype=np.uint16)
            gray_arr = ((arr.max(axis=-1) + arr.min(axis=-1)) // 2).astype(np.uint8)
            gray = Image.fromarray(gray_arr, mode="L").convert("RGB")
        else:
            gray = ImageOps.grayscale(rgb).convert("RGB")

        if strength < 0.999:
            gray = Image.blend(rgb, gray, max(0.0, min(1.0, strength)))
        out = gray.convert("RGBA")
        out.putalpha(rgba.split()[3])
        return out
