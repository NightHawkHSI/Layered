from PIL import Image
import random

from app.plugin_api import Plugin, PluginContext
from app.tools import Tool


# ---------------------------
# Core Pixel Sorting Function
# ---------------------------
def pixel_sort(image: Image.Image, mode="brightness", reverse=False):
    img = image.convert("RGBA")
    pixels = list(img.getdata())

    def brightness(p):
        return (p[0] + p[1] + p[2]) // 3

    def red(p): return p[0]
    def green(p): return p[1]
    def blue(p): return p[2]

    key_map = {
        "brightness": brightness,
        "red": red,
        "green": green,
        "blue": blue
    }

    key_func = key_map.get(mode, brightness)

    # Break into random horizontal chunks for glitch effect
    width, height = img.size
    new_pixels = pixels[:]

    for y in range(height):
        row_start = y * width
        row = pixels[row_start:row_start + width]

        # Split row into random segments
        segments = []
        i = 0
        while i < len(row):
            seg_len = random.randint(10, 80)
            segment = row[i:i + seg_len]
            segment.sort(key=key_func, reverse=reverse)
            segments.extend(segment)
            i += seg_len

        new_pixels[row_start:row_start + width] = segments

    new_img = Image.new("RGBA", img.size)
    new_img.putdata(new_pixels)
    return new_img


# ---------------------------
# Filter Version
# ---------------------------
class GlitchSortPlugin(Plugin):
    name = "Glitch Sorter"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter("Glitch Sort (Brightness)", self.sort_brightness)
        ctx.register_filter("Glitch Sort (Red)", self.sort_red)
        ctx.register_action("Glitch Sort (Random Chaos)", self.random_sort)
        ctx.register_tool("Glitch Brush", GlitchBrush(ctx))

        self.ctx = ctx

    def sort_brightness(self, image: Image.Image) -> Image.Image:
        return pixel_sort(image, "brightness")

    def sort_red(self, image: Image.Image) -> Image.Image:
        return pixel_sort(image, "red")

    def random_sort(self):
        layer = self.ctx.active_layer()
        if not layer:
            self.ctx.logger.warning("No active layer.")
            return

        mode = random.choice(["brightness", "red", "green", "blue"])
        reverse = random.choice([True, False])

        self.ctx.logger.info(f"Random sort: mode={mode}, reverse={reverse}")

        new_img = pixel_sort(layer.image, mode, reverse)
        self.ctx.replace_active_layer_image(new_img)


# ---------------------------
# Tool Version (PAINT GLITCH)
# ---------------------------
class GlitchBrush(Tool):
    name = "Glitch Brush"

    def __init__(self, ctx):
        super().__init__(ctx)
        self.radius = 20

    def press(self, layer, x, y):
        self.apply_glitch(layer, x, y)

    def move(self, layer, x, y):
        self.apply_glitch(layer, x, y)

    def apply_glitch(self, layer, x, y):
        img = layer.image
        width, height = img.size

        r = self.ctx.brush_size or self.radius

        # Clamp region
        x0 = max(0, x - r)
        y0 = max(0, y - r)
        x1 = min(width, x + r)
        y1 = min(height, y + r)

        region = img.crop((x0, y0, x1, y1))

        # Random glitch settings
        mode = random.choice(["brightness", "red", "green", "blue"])
        reverse = random.choice([True, False])

        glitched = pixel_sort(region, mode, reverse)

        img.paste(glitched, (x0, y0))
        self.ctx.canvas.refresh()