"""Drop shadow filter — adds a soft offset shadow under opaque pixels."""
from PIL import Image, ImageFilter

from app.plugin_api import Plugin, PluginContext, Setting


class DropShadowPlugin(Plugin):
    name = "Drop Shadow"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Drop Shadow",
            self.apply,
            settings=[
                Setting(name="offset_x", type="int", default=6, min=-128, max=128, step=1, label="Offset X"),
                Setting(name="offset_y", type="int", default=6, min=-128, max=128, step=1, label="Offset Y"),
                Setting(name="blur", type="int", default=8, min=0, max=128, step=1, label="Blur radius"),
                Setting(name="opacity", type="float", default=0.6, min=0.0, max=1.0, step=0.05, label="Opacity"),
                Setting(name="color", type="color", default=(0, 0, 0, 255), label="Shadow color"),
            ],
        )
        ctx.logger.info("Drop Shadow registered")

    def apply(self, image: Image.Image, *,
              offset_x: int = 6, offset_y: int = 6, blur: int = 8,
              opacity: float = 0.6, color=(0, 0, 0, 255)) -> Image.Image:
        base = image.convert("RGBA")
        w, h = base.size
        alpha = base.split()[3]
        # Pad enough room for offset + blur so shadow doesn't clip out.
        pad = max(abs(offset_x), abs(offset_y)) + max(0, blur) * 2
        canvas_w, canvas_h = w + pad * 2, h + pad * 2
        shadow_rgb = Image.new("RGBA", (canvas_w, canvas_h), (color[0], color[1], color[2], 0))
        shadow_alpha = Image.new("L", (canvas_w, canvas_h), 0)
        shadow_alpha.paste(alpha, (pad + offset_x, pad + offset_y))
        if blur > 0:
            shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(radius=blur))
        opa = max(0.0, min(1.0, opacity))
        shadow_alpha = shadow_alpha.point(lambda v: int(v * opa))
        shadow_rgb.putalpha(shadow_alpha)

        out = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        out.alpha_composite(shadow_rgb)
        out.alpha_composite(base, dest=(pad, pad))
        # Crop back to original size keeping the original anchor — that means
        # any shadow that fell outside the source bounds is dropped, matching
        # Paint.NET-style "shadow under image" behaviour.
        return out.crop((pad, pad, pad + w, pad + h))
