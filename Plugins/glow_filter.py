from PIL import Image, ImageFilter, ImageChops
from app.plugin_api import Plugin, PluginContext

class GlowFilterPlugin(Plugin):
    name = "Glow Filter"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter("Glow / Bloom", self.apply)
        ctx.logger.info("Glow Filter registered successfully")

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            self.ctx.logger.info("Applying Glow filter")

            # Ensure RGBA
            base = image.convert("RGBA")

            # Create blurred version (the glow)
            glow = base.filter(ImageFilter.GaussianBlur(radius=8))

            # Boost brightness slightly
            glow = ImageChops.add(glow, glow)

            # Blend original + glow
            result = ImageChops.screen(base, glow)

            self.ctx.logger.info("Glow filter applied successfully")
            return result

        except Exception as e:
            self.ctx.logger.error(f"Glow filter failed: {e}")
            raise