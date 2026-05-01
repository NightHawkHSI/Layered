from PIL import Image
from app.plugin_api import Plugin, PluginContext

class TileFixPlugin(Plugin):
    name = "Make Tileable"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_action("Make Tileable (Offset Preview)", self.apply)

    def apply(self) -> None:
        try:
            self.ctx.logger.info("Running Tileable offset preview")

            layer = self.ctx.active_layer()
            if not layer:
                self.ctx.logger.warning("No active layer")
                return

            img = layer.image
            w, h = img.size

            # Offset image to reveal seams
            offset = Image.new("RGBA", (w, h))
            offset.paste(img, (-w // 2, -h // 2))
            offset.paste(img, (w // 2, -h // 2))
            offset.paste(img, (-w // 2, h // 2))
            offset.paste(img, (w // 2, h // 2))

            self.ctx.replace_active_layer_image(offset)

            self.ctx.logger.info("Offset applied - fix seams manually now")

        except Exception as e:
            self.ctx.logger.error(f"Tile fix failed: {e}")
            raise