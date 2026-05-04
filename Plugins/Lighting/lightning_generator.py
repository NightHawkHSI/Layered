from PIL import Image, ImageDraw, ImageFilter
from app.plugin_api import Plugin, PluginContext, Setting
import random


class LightningGeneratorPlugin(Plugin):
    name = "Lightning Generator"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        self.ctx = ctx

        ctx.register_filter(
            "Lightning",
            self.apply_lightning,
            settings=[
                Setting("jitter", "float", 80.0, "Jitter", 10.0, 200.0, 1.0),
                Setting("segments", "int", 6, "Segments", 2, 12, 1),
                Setting("thickness", "int", 2, "Thickness", 1, 10, 1),
                Setting("glow", "int", 10, "Glow Blur", 0, 30, 1),
                Setting("branch_chance", "float", 0.25, "Branch Chance", 0.0, 1.0, 0.05),
            ],
            category="VFX"
        )

        ctx.register_action("Test Lightning Plugin", self.ping)

    def ping(self):
        self.ctx.status("⚡ Lightning System Online")

    # ----------------------------
    # Lightning generation logic
    # ----------------------------

    def _make_bolt(self, w, h, jitter, segments):
        points = [(w // 2, 0)]

        for i in range(1, segments):
            x = w // 2 + random.randint(-int(jitter), int(jitter))
            y = int((h / segments) * i)
            points.append((x, y))

        points.append((w // 2, h))
        return points

    def _add_branches(self, draw, points, chance):
        for i in range(1, len(points) - 2):
            if random.random() < chance:
                x, y = points[i]

                bx = x + random.randint(-40, 40)
                by = y + random.randint(20, 80)

                draw.line([(x, y), (bx, by)], fill=(255, 255, 255, 180), width=1)

    # ----------------------------
    # Main effect
    # ----------------------------

    def apply_lightning(
        self,
        img: Image.Image,
        *,
        jitter=80.0,
        segments=6,
        thickness=2,
        glow=10,
        branch_chance=0.25
    ) -> Image.Image:

        w, h = img.size

        base = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)

        points = self._make_bolt(w, h, jitter, segments)

        # main bolt
        draw.line(points, fill=(255, 255, 255, 255), width=thickness)

        # branches
        self._add_branches(draw, points, branch_chance)

        # glow layer
        glow_layer = base.filter(ImageFilter.GaussianBlur(glow))

        # composite
        out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        out.alpha_composite(glow_layer)
        out.alpha_composite(base)

        return out