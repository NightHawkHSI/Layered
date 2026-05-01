"""Tileable preview / seam-blend filter."""
from PIL import Image, ImageFilter

from app.plugin_api import Plugin, PluginContext, Setting


class TileFixPlugin(Plugin):
    name = "Make Tileable"
    version = "1.1.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter(
            "Make Tileable",
            self.apply,
            settings=[
                Setting(name="mode", type="choice", default="offset",
                        choices=["offset", "blend_seams"], label="Mode"),
                Setting(name="blend_radius", type="int", default=24, min=2, max=256, step=2,
                        label="Seam blend radius"),
            ],
        )

    def apply(self, image: Image.Image, *, mode: str = "offset",
              blend_radius: int = 24) -> Image.Image:
        img = image.convert("RGBA")
        w, h = img.size
        if mode == "offset":
            return self._offset(img, w, h)
        return self._blend_seams(img, w, h, max(2, int(blend_radius)))

    def _offset(self, img: Image.Image, w: int, h: int) -> Image.Image:
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.paste(img, (-w // 2, -h // 2))
        out.paste(img, (w // 2, -h // 2))
        out.paste(img, (-w // 2, h // 2))
        out.paste(img, (w // 2, h // 2))
        return out

    def _blend_seams(self, img: Image.Image, w: int, h: int, r: int) -> Image.Image:
        # Build a tiled 3x3 super-image and crop the centre after blurring the seams.
        super_img = Image.new("RGBA", (w * 3, h * 3))
        for ix in range(3):
            for iy in range(3):
                super_img.paste(img, (ix * w, iy * h))
        blurred = super_img.filter(ImageFilter.GaussianBlur(radius=r))
        mask = Image.new("L", (w * 3, h * 3), 0)
        # Paint blend bands along the seams (vertical + horizontal).
        from PIL import ImageDraw
        d = ImageDraw.Draw(mask)
        for x in (w, 2 * w):
            d.rectangle([x - r, 0, x + r, h * 3], fill=255)
        for y in (h, 2 * h):
            d.rectangle([0, y - r, w * 3, y + r], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(radius=r // 2))
        out = Image.composite(blurred, super_img, mask)
        return out.crop((w, h, w * 2, h * 2))
