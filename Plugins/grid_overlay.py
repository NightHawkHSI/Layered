from app.plugin_api import Plugin, PluginContext

class GridOverlayPlugin(Plugin):
    name = "Grid Overlay"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_action("Toggle Grid Overlay (Stub)", self.toggle)

        self.enabled = False

    def toggle(self):
        try:
            self.enabled = not self.enabled
            self.ctx.logger.info(f"Grid overlay: {self.enabled}")

            # Hook point:
            # Your canvas renderer should read this state and draw grid lines.

            self.ctx.canvas.refresh()

        except Exception as e:
            self.ctx.logger.error(f"Grid toggle failed: {e}")
            raise