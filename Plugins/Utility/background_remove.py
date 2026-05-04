from PIL import Image
from app.plugin_api import Plugin, PluginContext

class SimpleBackgroundRemovePlugin(Plugin):
    name = "Simple Background Remove"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter("Remove Background (Basic)", self.apply, category="Generators")

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            img = image.convert("RGBA")
            datas = img.getdata()

            new_data = []
            for item in datas:
                r, g, b, a = item

                # simple white background removal
                if r > 240 and g > 240 and b > 240:
                    new_data.append((255, 255, 255, 0))
                else:
                    new_data.append(item)

            img.putdata(new_data)
            return img

        except Exception as e:
            self.ctx.logger.error(f"Background removal failed: {e}")
            raise