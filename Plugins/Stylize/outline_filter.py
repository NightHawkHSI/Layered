from PIL import Image, ImageFilter
from app.plugin_api import Plugin, PluginContext, Setting


class OutlineFilterPlugin(Plugin):
    name = "Outline (Configurable)"
    version = "2.1.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Outline (Configurable)",
            self.apply,
            settings=[
                Setting(name="color", type="color", default=(255, 255, 255, 255), label="Color"),
                Setting(name="thickness", type="int", default=5, min=1, max=64, step=1, label="Thickness"),
                Setting(name="opacity", type="float", default=1.0, min=0.0, max=1.0, step=0.05, label="Opacity"),
                Setting(name="softness", type="int", default=0, min=0, max=32, step=1, label="Softness (blur)"),
                Setting(
                    name="placement",
                    type="choice",
                    default="behind",
                    choices=["behind", "in_front"],
                    label="Placement",
                ),
            ],
            category="Effects",
        )
        ctx.logger.info("Configurable Outline plugin loaded")

    def apply(
        self,
        image: Image.Image,
        color=(255, 255, 255, 255),
        thickness: int = 5,
        opacity: float = 1.0,
        softness: int = 0,
        placement: str = "behind",
    ) -> Image.Image:
        self.ctx.logger.info("Applying outline t=%s color=%s", thickness, color)

        base = image.convert("RGBA")
        thickness = max(1, int(thickness))
        opacity = max(0.0, min(1.0, float(opacity)))
        softness = max(0, int(softness))

        alpha = base.split()[3]
        outline_alpha = alpha
        for _ in range(thickness):
            outline_alpha = outline_alpha.filter(ImageFilter.MaxFilter(3))

        if softness > 0:
            outline_alpha = outline_alpha.filter(ImageFilter.GaussianBlur(radius=softness))

        if isinstance(color, (list, tuple)):
            if len(color) == 3:
                r, g, b = color
                a = 255
            else:
                r, g, b, a = color[:4]
        else:
            r, g, b, a = 255, 255, 255, 255

        color_alpha_scale = (a / 255.0) * opacity
        final_alpha = outline_alpha.point(lambda p: int(p * color_alpha_scale))

        outline_layer = Image.new("RGBA", base.size, (int(r), int(g), int(b), 0))
        outline_layer.putalpha(final_alpha)

        if placement == "in_front":
            return Image.alpha_composite(base, outline_layer)
        return Image.alpha_composite(outline_layer, base)
