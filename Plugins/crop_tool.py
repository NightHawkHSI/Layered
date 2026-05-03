from PIL import Image
from app.plugin_api import Plugin, PluginContext

class CropToolPlugin(Plugin):
    name = "Crop Tool"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_action("Crop to Center (Demo)", self.crop_center, category="Utilities")

    def crop_center(self):
        try:
            layer = self.ctx.active_layer()
            if not layer:
                self.ctx.logger.warning("No active layer")
                return

            img = layer.image
            w, h = img.size

            # simple center crop (you can later tie this to selection system)
            crop_box = (
                w // 4,
                h // 4,
                w * 3 // 4,
                h * 3 // 4
            )

            cropped = img.crop(crop_box)
            self.ctx.replace_active_layer_image(cropped)

        except Exception as e:
            self.ctx.logger.error(f"Crop failed: {e}")
            raise