from PIL import Image, ImageFilter, ImageChops
from app.plugin_api import Plugin, PluginContext

class OutlineFilterPlugin(Plugin):
    name = "Outline (Configurable)"
    version = "2.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx

        # Register filter
        ctx.register_filter("Outline (Configurable)", self.apply)

        # Default settings (you can later expose this in UI)
        self.settings = {
            "color": (255, 255, 255, 255),  # RGBA
            "thickness": 5,                # outline size
            "opacity": 1.0,                # 0.0 - 1.0
            "softness": 0,                 # blur amount
        }

        ctx.logger.info("Configurable Outline plugin loaded")

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            self.ctx.logger.info("Applying configurable outline")

            base = image.convert("RGBA")

            color = self.settings["color"]
            thickness = int(self.settings["thickness"])
            opacity = float(self.settings["opacity"])
            softness = int(self.settings["softness"])

            # Extract alpha channel
            alpha = base.split()[3]

            # Expand alpha for outline thickness
            outline = alpha
            for _ in range(thickness):
                outline = outline.filter(ImageFilter.MaxFilter(3))

            # Optional softness (blur)
            if softness > 0:
                outline = outline.filter(ImageFilter.GaussianBlur(radius=softness))

            # Build colored outline layer
            r, g, b, a = color
            outline_img = Image.new("RGBA", base.size, (r, g, b, 0))

            # Apply alpha + opacity
            final_alpha = outline.point(lambda p: int(p * opacity))
            outline_img.putalpha(final_alpha)

            # Composite: outline first, then original on top
            result = Image.alpha_composite(outline_img, base)

            self.ctx.logger.info(
                f"Outline applied (thickness={thickness}, color={color})"
            )

            return result

        except Exception as e:
            self.ctx.logger.error(f"Outline failed: {e}")
            raise