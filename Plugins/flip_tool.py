from app.plugin_api import Plugin, PluginContext
from PIL import Image

class FlipToolPlugin(Plugin):
    name = "Flip Tools"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_action("Flip Horizontal", self.flip_h, category="Utilities")
        ctx.register_action("Flip Vertical", self.flip_v, category="Utilities")

    def flip_h(self):
        self._flip(Image.FLIP_LEFT_RIGHT)

    def flip_v(self):
        self._flip(Image.FLIP_TOP_BOTTOM)

    def _flip(self, mode):
        try:
            layer = self.ctx.active_layer()
            if not layer:
                return

            flipped = layer.image.transpose(mode)
            self.ctx.replace_active_layer_image(flipped)

        except Exception as e:
            self.ctx.logger.error(f"Flip failed: {e}")
            raise