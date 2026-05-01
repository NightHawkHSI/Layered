"""Color replace — swap pixels matching a target color (within tolerance) for a new one."""
import numpy as np
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


class ColorReplacePlugin(Plugin):
    name = "Color Replace"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Color Replace",
            self.apply,
            settings=[
                Setting(name="target", type="color", default=(255, 0, 0, 255), label="Target color"),
                Setting(name="replacement", type="color", default=(0, 0, 255, 255), label="Replacement"),
                Setting(name="tolerance", type="int", default=24, min=0, max=255, step=1, label="Tolerance"),
                Setting(name="match_alpha", type="bool", default=False, label="Match alpha too"),
            ],
        )
        ctx.logger.info("Color Replace registered")

    def apply(self, image: Image.Image, *,
              target=(255, 0, 0, 255), replacement=(0, 0, 255, 255),
              tolerance: int = 24, match_alpha: bool = False) -> Image.Image:
        img = image.convert("RGBA")
        arr = np.asarray(img, dtype=np.int16).copy()
        tgt = np.array(target, dtype=np.int16)
        if match_alpha:
            diff = np.abs(arr - tgt).max(axis=-1)
        else:
            diff = np.abs(arr[..., :3] - tgt[:3]).max(axis=-1)
        mask = diff <= max(0, int(tolerance))
        rep = np.array(replacement, dtype=np.uint8)
        arr[mask] = rep
        return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), mode="RGBA")
