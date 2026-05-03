from PIL import Image, ImageEnhance
from app.plugin_api import Plugin, PluginContext

class BrightnessContrastPlugin(Plugin):
    name = "Brightness / Contrast"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter("Brightness / Contrast", self.apply, category="Color")

        self.settings = {
            "brightness": 1.0,  # 0.0 - 2.0
            "contrast": 1.0,    # 0.0 - 2.0
        }

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            img = image.convert("RGBA")

            b = ImageEnhance.Brightness(img)
            img = b.enhance(self.settings["brightness"])

            c = ImageEnhance.Contrast(img)
            img = c.enhance(self.settings["contrast"])

            return img

        except Exception as e:
            self.ctx.logger.error(f"Brightness/Contrast failed: {e}")
            raise