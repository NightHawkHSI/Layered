from PIL import Image, ImageDraw
import random

from app.plugin_api import Plugin, PluginContext, Setting
from app.tools import Tool


# ---------------------------
# Generate Seamless Pattern
# ---------------------------
def generate_pattern(size=128, complexity=50, seed=0):
    random.seed(seed)

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    for _ in range(complexity):
        x1 = random.randint(0, size)
        y1 = random.randint(0, size)
        x2 = x1 + random.randint(-20, 20)
        y2 = y1 + random.randint(-20, 20)

        color = (
            random.randint(50, 255),
            random.randint(50, 255),
            random.randint(50, 255),
            255,
        )

        draw.line((x1, y1, x2, y2), fill=color, width=random.randint(1, 3))

    return img


# ---------------------------
# Tile Preview (3x3 grid)
# ---------------------------
def tile_preview(image):
    w, h = image.size
    preview = Image.new("RGBA", (w * 3, h * 3))

    for y in range(3):
        for x in range(3):
            preview.paste(image, (x * w, y * h))

    return preview


# ---------------------------
# Symmetry Brush Tool
# ---------------------------
class SymmetryBrush(Tool):
    name = "Symmetry Brush"

    def __init__(self, ctx):
        super().__init__(ctx)

    def press(self, layer, x, y):
        self.paint(layer, x, y)

    def move(self, layer, x, y):
        self.paint(layer, x, y)

    def paint(self, layer, x, y):
        img = layer.image
        pixels = img.load()

        w, h = img.size
        r = self.ctx.brush_size or 5
        color = self.ctx.primary_color

        points = [
            (x, y),
            (w - x, y),
            (x, h - y),
            (w - x, h - y),
        ]

        for px, py in points:
            for iy in range(-r, r):
                for ix in range(-r, r):
                    tx = int(px + ix)
                    ty = int(py + iy)

                    if 0 <= tx < w and 0 <= ty < h:
                        pixels[tx, ty] = color

        self.ctx.canvas.refresh()


# ---------------------------
# Plugin
# ---------------------------
class InfinitePatternLab(Plugin):
    name = "Infinite Pattern Lab"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx

        settings = [
            Setting("size", "int", 128, "Tile Size", 32, 512),
            Setting("complexity", "int", 50, "Detail Amount", 1, 200),
            Setting("seed", "int", 0, "Random Seed", 0, 99999),
        ]

        ctx.register_action("Generate Pattern", self.generate, settings=settings)
        ctx.register_action("Create Tile Preview", self.preview)
        ctx.register_action("Export Seamless Texture", self.export_texture)
        ctx.register_tool("Symmetry Brush", SymmetryBrush(ctx.tool_context))

    # ---------------------------
    # Generate new pattern
    # ---------------------------
    def generate(self, size=128, complexity=50, seed=0):
        self.ctx.config_set("last_size", size)
        self.ctx.config_set("last_complexity", complexity)
        self.ctx.config_set("last_seed", seed)

        img = generate_pattern(size, complexity, seed)

        self.ctx.add_layer(img, name="Pattern")
        self.ctx.commit("Generate Pattern")

        self.ctx.status("Pattern generated")

    # ---------------------------
    # Preview tiling
    # ---------------------------
    def preview(self):
        layer = self.ctx.active_layer()
        if not layer:
            return

        preview = tile_preview(layer.image)

        self.ctx.add_layer(preview, name="Tile Preview")
        self.ctx.commit("Tile Preview")

    # ---------------------------
    # Export seamless texture
    # ---------------------------
    def export_texture(self):
        layer = self.ctx.active_layer()
        if not layer:
            return

        path = self.ctx.ask_save_file("PNG Files (*.png)")
        if not path:
            return

        layer.image.save(path)
        self.ctx.status(f"Saved texture to {path}")