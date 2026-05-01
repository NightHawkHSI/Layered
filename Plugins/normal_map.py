import numpy as np
from PIL import Image
from app.plugin_api import Plugin, PluginContext

class NormalMapPlugin(Plugin):
    name = "Normal Map Generator"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx
        ctx.register_filter("Generate Normal Map", self.apply)

    def apply(self, image: Image.Image) -> Image.Image:
        try:
            self.ctx.logger.info("Generating normal map")

            gray = image.convert("L")
            arr = np.array(gray).astype("float32")

            # Sobel-like gradient
            dx = np.roll(arr, -1, axis=1) - np.roll(arr, 1, axis=1)
            dy = np.roll(arr, -1, axis=0) - np.roll(arr, 1, axis=0)

            dz = np.ones_like(arr) * 255

            normal = np.stack((dx, dy, dz), axis=2)

            # Normalize
            norm = np.linalg.norm(normal, axis=2, keepdims=True)
            normal = normal / (norm + 1e-8)

            # Convert to RGB
            normal = ((normal + 1) / 2 * 255).astype("uint8")

            result = Image.fromarray(normal, mode="RGB").convert("RGBA")

            self.ctx.logger.info("Normal map created")
            return result

        except Exception as e:
            self.ctx.logger.error(f"Normal map failed: {e}")
            raise