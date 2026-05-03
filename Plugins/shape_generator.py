"""
shape_generator.py — Procedural Shape Overlay Filter for Layered
"""

from __future__ import annotations

import math
import random
from PIL import Image, ImageDraw

from app.plugin_api import Plugin, Setting


class ShapeGeneratorPlugin(Plugin):
    name = "Shape Generator"
    version = "1.5.0"

    # ----------------------------
    # Math Helpers
    # ----------------------------

    def _rotate_points(self, points, cx, cy, angle_deg):
        rad = math.radians(angle_deg)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        return [
            (cx + px * cos_a - py * sin_a, cy + px * sin_a + py * cos_a)
            for px, py in points
        ]

    def _get_shape_points(self, shape, bbox, rotation):
        """Returns the points for a polygon or the bbox for an ellipse."""
        x0, y0, x1, y1 = bbox
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        size = (x1 - x0) / 2

        if shape == "square":
            pts = [(-size, -size), (size, -size), (size, size), (-size, size)]
            return self._rotate_points(pts, cx, cy, rotation)
        elif shape == "triangle":
            pts = [(0, -size), (-size, size), (size, size)]
            return self._rotate_points(pts, cx, cy, rotation)
        return bbox # For circle

    # ----------------------------
    # Filter function
    # ----------------------------

    def apply(
        self,
        img: Image.Image,
        *,
        shape: str = "square",
        placement: str = "center",
        count: int = 2,
        size: int = 150,
        orbit_radius: int = 0,
        rotation: float = 0.0,
        rotation_step: float = 45.0,
        random_rotation: bool = False,
        fill_color=(0, 0, 0, 255),
        outline_color=(255, 255, 255, 255),
        outline_width: int = 2,
        global_opacity: float = 1.0,
        match_fill_outline: bool = False,
        seed: int = 0,
    ) -> Image.Image:

        base = img.convert("RGBA")
        w, h = base.size
        cx, cy = w / 2, h / 2

        rng = random.Random(seed)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay, "RGBA")

        # Color and Opacity processing
        def apply_opacity(color_tuple, opacity):
            r, g, b = color_tuple[:3]
            a = color_tuple[3] if len(color_tuple) > 3 else 255
            return (r, g, b, int(a * opacity))

        final_fill = apply_opacity(fill_color, global_opacity)
        final_outline = final_fill if match_fill_outline else apply_opacity(outline_color, global_opacity)

        # Pass 1: Pre-calculate all shape geometries
        # We do this so randomness is consistent between fill pass and outline pass
        shapes_to_draw = []
        for i in range(count):
            if placement == "random":
                x = rng.randint(0, w)
                y = rng.randint(0, h)
                s = rng.randint(int(size * 0.5), int(size * 1.5))
                rot = rotation + (i * rotation_step)
                if random_rotation:
                    rot += rng.uniform(0, 360)
            else:
                orbit_angle = (360 / count) * i
                rad = math.radians(rotation + orbit_angle)
                x = cx + (orbit_radius * math.cos(rad))
                y = cy + (orbit_radius * math.sin(rad))
                s = size
                rot = rotation + (i * rotation_step)
                if random_rotation:
                    rot += rng.uniform(0, 360)

            bbox = (x - s, y - s, x + s, y + s)
            geo = self._get_shape_points(shape, bbox, rot)
            shapes_to_draw.append(geo)

        # Pass 2: Draw all FILLS first
        if final_fill[3] > 0: # Only draw if not fully transparent
            for geo in shapes_to_draw:
                if shape == "circle":
                    draw.ellipse(geo, fill=final_fill, outline=None)
                else:
                    draw.polygon(geo, fill=final_fill, outline=None)

        # Pass 3: Draw all OUTLINES last (so they are on top of all fills)
        if outline_width > 0:
            for geo in shapes_to_draw:
                if shape == "circle":
                    draw.ellipse(geo, fill=None, outline=final_outline, width=outline_width)
                else:
                    # draw.polygon doesn't always handle thick outlines perfectly, 
                    # so we draw a line loop for better results with width
                    draw.polygon(geo, fill=None, outline=final_outline, width=outline_width)

        return Image.alpha_composite(base, overlay)

    # ----------------------------
    # Register
    # ----------------------------

    def register(self, ctx) -> None:
        ctx.register_filter(
            "Shape Generator",
            self.apply,
            category="Generators",
            settings=[
                Setting(
                    name="shape",
                    type="choice",
                    default="square",
                    label="Shape",
                    choices=["circle", "square", "triangle"],
                ),
                Setting(
                    name="placement",
                    type="choice",
                    default="center",
                    label="Placement Mode",
                    choices=["center", "random"],
                ),
                Setting(
                    name="count",
                    type="int",
                    default=2,
                    label="Count (Stacks)",
                    min=1,
                    max=100,
                    step=1,
                ),
                Setting(
                    name="size",
                    type="int",
                    default=150,
                    label="Size",
                    min=5,
                    max=1000,
                    step=5,
                ),
                Setting(
                    name="orbit_radius",
                    type="int",
                    default=0,
                    label="Orbit Radius",
                    min=0,
                    max=1000,
                    step=5,
                ),
                Setting(
                    name="rotation",
                    type="float",
                    default=0.0,
                    label="Base Rotation",
                    min=0.0,
                    max=360.0,
                    step=1.0,
                ),
                Setting(
                    name="rotation_step",
                    type="float",
                    default=45.0,
                    label="Rotation Step (Star Effect)",
                    min=0.0,
                    max=180.0,
                    step=0.5,
                ),
                Setting(
                    name="global_opacity",
                    type="float",
                    default=1.0,
                    label="Global Opacity",
                    min=0.0,
                    max=1.0,
                    step=0.01,
                ),
                Setting(
                    name="fill_color",
                    type="color",
                    default=(0, 0, 0, 255),
                    label="Fill Color",
                ),
                Setting(
                    name="outline_color",
                    type="color",
                    default=(255, 255, 255, 255),
                    label="Outline Color",
                ),
                Setting(
                    name="outline_width",
                    type="int",
                    default=2,
                    label="Outline Width",
                    min=0,
                    max=50,
                    step=1,
                ),
                Setting(
                    name="match_fill_outline",
                    type="bool",
                    default=False,
                    label="Match Fill & Outline",
                ),
                Setting(
                    name="seed",
                    type="int",
                    default=0,
                    label="Seed",
                    min=0,
                    max=999999,
                    step=1,
                ),
            ],
        )