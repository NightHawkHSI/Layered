from PIL import Image, ImageFilter
from app.plugin_api import Plugin, PluginContext

class SharpenPlugin(Plugin):
    name = "Sharpen"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter("Sharpen", self.apply)

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            return image.convert("RGBA").filter(ImageFilter.SHARPEN)
        except Exception as e:
            self.ctx.logger.error(f"Sharpen failed: {e}")
            raise