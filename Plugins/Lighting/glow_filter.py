"""Glow / bloom filter."""
from PIL import Image, ImageChops, ImageFilter

from app.plugin_api import Plugin, PluginContext, Setting


class GlowFilterPlugin(Plugin):
    name = "Glow Filter"
    version = "1.1.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Glow / Bloom",
            self.apply,
            settings=[
                Setting(name="radius", type="int", default=8, min=1, max=128, step=1, label="Radius"),
                Setting(name="intensity", type="float", default=1.0, min=0.0, max=4.0, step=0.1, label="Intensity"),
                Setting(name="mode", type="choice", default="screen",
                        choices=["screen", "add", "lighten"], label="Blend mode"),
            ],
            category="Effects",
        )
        ctx.logger.info("Glow Filter registered")

    def apply(self, image: Image.Image, *,
              radius: int = 8, intensity: float = 1.0, mode: str = "screen") -> Image.Image:
        base = image.convert("RGBA")
        glow = base.filter(ImageFilter.GaussianBlur(radius=max(1, int(radius))))
        if intensity != 1.0:
            r, g, b, a = glow.split()
            r = r.point(lambda v: min(255, int(v * intensity)))
            g = g.point(lambda v: min(255, int(v * intensity)))
            b = b.point(lambda v: min(255, int(v * intensity)))
            glow = Image.merge("RGBA", (r, g, b, a))
        if mode == "add":
            result = ImageChops.add(base, glow)
        elif mode == "lighten":
            result = ImageChops.lighter(base, glow)
        else:
            result = ImageChops.screen(base, glow)
        # Preserve original alpha so glow stays inside opaque pixels.
        result.putalpha(base.split()[3])
        return result
