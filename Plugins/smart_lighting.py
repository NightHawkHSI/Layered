from PIL import Image, ImageFilter
import math

from app.plugin_api import Plugin, PluginContext, Setting
from app.tools import Tool


# ---------------------------
# Core Lighting Function
# ---------------------------
def apply_lighting(image, angle=45, strength=1.0, softness=1.0):
    img = image.convert("RGBA")
    width, height = img.size

    dx = math.cos(math.radians(angle))
    dy = math.sin(math.radians(angle))

    pixels = img.load()

    new_img = Image.new("RGBA", img.size)
    new_pixels = new_img.load()

    for y in range(height):
        for x in range(width):
            r, g, b, a = pixels[x, y]

            # Sample offset pixel (fake light direction)
            sx = int(min(width - 1, max(0, x + dx * softness)))
            sy = int(min(height - 1, max(0, y + dy * softness)))

            sr, sg, sb, _ = pixels[sx, sy]

            brightness = ((sr + sg + sb) / 3) / 255.0
            shade = (brightness - 0.5) * strength * 255

            nr = int(max(0, min(255, r + shade)))
            ng = int(max(0, min(255, g + shade)))
            nb = int(max(0, min(255, b + shade)))

            new_pixels[x, y] = (nr, ng, nb, a)

    return new_img


# ---------------------------
# Tool (Paint Lighting)
# ---------------------------
class LightBrush(Tool):
    name = "Light Brush"

    def __init__(self, ctx):
        super().__init__(ctx)

    def press(self, layer, x, y):
        self.paint(layer, x, y)

    def move(self, layer, x, y):
        self.paint(layer, x, y)

    def paint(self, layer, x, y):
        img = layer.image
        pixels = img.load()

        r = self.ctx.brush_size or 10
        strength = 25

        for iy in range(-r, r):
            for ix in range(-r, r):
                px = x + ix
                py = y + iy

                if 0 <= px < img.width and 0 <= py < img.height:
                    dist = (ix * ix + iy * iy) ** 0.5
                    if dist < r:
                        falloff = 1 - (dist / r)

                        cr, cg, cb, ca = pixels[px, py]

                        # brighten (light)
                        cr = min(255, int(cr + strength * falloff))
                        cg = min(255, int(cg + strength * falloff))
                        cb = min(255, int(cb + strength * falloff))

                        pixels[px, py] = (cr, cg, cb, ca)

        self.ctx.canvas.refresh()


# ---------------------------
# Plugin
# ---------------------------
class SmartLightingPlugin(Plugin):
    name = "Smart Lighting"
    version = "1.0.0"
    author = "You"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx

        settings = [
            Setting("angle", "int", 45, "Light Angle", 0, 360),
            Setting("strength", "float", 1.0, "Strength", 0.1, 5.0),
            Setting("softness", "float", 1.0, "Softness", 0.5, 10.0),
        ]

        ctx.register_filter("Apply Smart Lighting", self.apply_filter, settings=settings)
        ctx.register_action("Bake Lighting to New Layer", self.bake_lighting, settings=settings)
        ctx.register_tool("Light Brush", LightBrush(ctx.tool_context))

    # ---------------------------
    # Filter
    # ---------------------------
    def apply_filter(self, image, angle=45, strength=1.0, softness=1.0):
        result = apply_lighting(image, angle, strength, softness)

        mask = self.ctx.get_selection_mask()
        if mask:
            base = image.copy()
            base.paste(result, (0, 0), mask)
            return base

        return result

    # ---------------------------
    # Action (non-destructive workflow)
    # ---------------------------
    def bake_lighting(self, angle=45, strength=1.0, softness=1.0):
        layer = self.ctx.active_layer()
        if not layer:
            self.ctx.logger.warning("No active layer")
            return

        self.ctx.status("Baking lighting...")

        new_img = apply_lighting(layer.image, angle, strength, softness)

        self.ctx.add_layer(new_img, name="Lighting")
        self.ctx.commit("Bake Lighting")

        self.ctx.status("Lighting added as new layer")

    # ---------------------------
    # Optional: React to canvas resize
    # ---------------------------
    def on_resize(self, w, h):
        self.ctx.logger.info(f"Canvas resized to {w}x{h}")

    def shutdown(self):
        self.ctx.logger.info("Smart Lighting plugin shutdown")