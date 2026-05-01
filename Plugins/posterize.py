"""Posterize — quantize each channel to N levels for a flat-shaded look."""
import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


class PosterizePlugin(Plugin):
    name = "Posterize"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Posterize",
            self.apply,
            settings=[
                Setting(name="levels", type="int", default=4, min=2, max=32, step=1, label="Levels per channel"),
                Setting(name="include_alpha", type="bool", default=False, label="Quantize alpha"),
            ],
        )
        ctx.logger.info("Posterize registered")

    def apply(self, image: Image.Image, *, levels: int = 4, include_alpha: bool = False) -> Image.Image:
        img = image.convert("RGBA")
        arr = np.asarray(img, dtype=np.float32)
        n = max(2, int(levels))
        step = 255.0 / (n - 1)
        rgb = np.round(arr[..., :3] / step) * step
        out = arr.copy()
        out[..., :3] = rgb
        if include_alpha:
            out[..., 3] = np.round(arr[..., 3] / step) * step
        return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGBA")
