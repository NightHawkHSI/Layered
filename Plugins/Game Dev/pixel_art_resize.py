"""Pixel-art resize — nearest-neighbor scale that preserves crisp pixel edges."""
from PIL import Image

from app.plugin_api import Plugin, PluginContext, Setting


class PixelArtResizePlugin(Plugin):
    name = "Pixel Art Resize"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Pixel Art Resize",
            self.apply,
            settings=[
                Setting(name="scale", type="int", default=2, min=1, max=16, step=1, label="Scale (×)"),
                Setting(name="mode", type="choice", default="upscale",
                        choices=["upscale", "downscale"], label="Direction"),
            ],
            category="Generators",
        )
        ctx.logger.info("Pixel Art Resize registered")

    def apply(self, image: Image.Image, *, scale: int = 2, mode: str = "upscale") -> Image.Image:
        img = image.convert("RGBA")
        s = max(1, int(scale))
        w, h = img.size
        if mode == "downscale":
            new = (max(1, w // s), max(1, h // s))
        else:
            new = (w * s, h * s)
        return img.resize(new, Image.Resampling.NEAREST)
