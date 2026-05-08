import importlib.util
import math
import sys
import random
import colorsys

from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

from app.layer import Layer
from app.tools import Tool

# —————————————————————————————————————————————————————————————————————————————
# load shared builtins
# —————————————————————————————————————————————————————————————————————————————

_K = "_layered_brushes_shared"

if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[2] / "_shared.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)

_bt   = sys.modules[_K]
_walk = _bt._walk

# —————————————————————————————————————————————————————————————————————————————
# TOOL: Folded Dimension (Spectral Ribbon Tool)
# —————————————————————————————————————————————————————————————————————————————

class FoldedDimensionBrushTool(Tool):

    name = "Folded Dimension"
    icon = "☄️"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Geometry
        self.width          = 40
        self.twist_rate     = 5.0    # Speed of the 3D rotation
        self.segments       = 12     # Sharpness of folds
        
        # Visuals
        self.iridescence    = 60     # Hue shifting strength
        self.transparency   = 70     # Glassiness
        self.shard_chance   = 15     # Shedding geometric debris
        
        # Physics
        self.glow_power     = 10
        self.dimension_warp = 1.0    # Perspective distortion
        
        # Internals
        self._last_pt: tuple[float, float] | None = None
        self._angle: float = 0.0      # Current twist rotation
        self._prev_edge: list[tuple[float, float]] = []

    # —————————————————————————————————————————————————————————————————————————
    # UI
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Dimension Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(180)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("width",        "Ribbon Width",   5,  200, False),
            ("twist_rate",   "Twist Speed",    1,  200, True),
            ("segments",     "Facet Detail",   2,   50, False),
            ("iridescence",  "Spectral Shift", 0,  100, False),
            ("transparency", "Glassiness",     0,  100, False),
            ("shard_chance", "Shard Shed %",   0,  100, False),
            ("glow_power",   "Aura Glow",      0,   50, False),
            ("dimension_warp", "Warp Factor",  1,   50, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #bba;")
            return l

        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 1000, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        for i, (attr, label, lo, hi, is_float) in enumerate(SLIDERS):
            grid.addWidget(lbl(label), i+1, 0)
            val = getattr(self, attr)
            if is_float: val = int(val * 10)
            s = SliderField(lo, hi, val, slider_width=110)
            def make_h(a, f):
                return lambda v: setattr(self, a, v / 10.0 if f else int(v))
            s.valueChanged.connect(make_h(attr, is_float))
            grid.addWidget(s, i+1, 1)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(panel)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn

    # —————————————————————————————————————————————————————————————————————————
    # Logic
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        # High fidelity spacing for ribbon facets
        return max(2.0, self.width / self.segments)

    def press(self, layer, x, y):
        ox, oy = layer.offset
        self._last_pt = (x - ox, y - oy)
        self._angle = 0.0
        # Initialize the first edge of the ribbon
        self._prev_edge = self._calculate_edge(self._last_pt[0], self._last_pt[1], 0.0, 0.0)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        ox, oy = layer.offset
        cur_pt = (x - ox, y - oy)
        
        for px, py in _walk(
            (self._last_pt[0] + ox, self._last_pt[1] + oy),
            (x, y),
            self._spacing()
        ):
            self._draw_segment(layer, px - ox, py - oy)
            self._last_pt = (px - ox, py - oy)

    def _calculate_edge(self, cx, cy, stroke_angle, rotation):
        """Calculates the two 3D points representing the width-axis of the ribbon."""
        half_w = self.width / 2.0
        
        # Perpendicular angle to stroke
        perp = stroke_angle + math.pi/2
        
        # 3D Twist: Rotation around the spine
        # We simulate Z-depth by narrowing the width as it rotates
        z_factor = math.cos(rotation)
        y_offset = math.sin(rotation) * (self.width / 4.0)
        
        p1x = cx + math.cos(perp) * half_w * z_factor
        p1y = cy + math.sin(perp) * half_w * z_factor + y_offset
        
        p2x = cx - math.cos(perp) * half_w * z_factor
        p2y = cy - math.sin(perp) * half_w * z_factor - y_offset
        
        return [(p1x, p1y), (p2x, p2y)]

    def _draw_segment(self, layer: Layer, cx: float, cy: float) -> None:
        # Calculate stroke direction
        dx, dy = cx - self._last_pt[0], cy - self._last_pt[1]
        stroke_angle = math.atan2(dy, dx)
        
        # Increment 3D twist
        self._angle += (self.twist_rate / 10.0)
        
        # New edge points
        new_edge = self._calculate_edge(cx, cy, stroke_angle, self._angle)
        
        # Render Area
        pad = int(self.width + self.glow_power + 20)
        bx0 = int(cx - pad)
        by0 = int(cy - pad)
        scratch = Image.new("RGBA", (pad*2, pad*2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)

        # Map to scratch space
        p1, p2 = self._prev_edge
        p3, p4 = new_edge
        
        facet = [
            (p1[0]-bx0, p1[1]-by0), (p2[0]-bx0, p2[1]-by0),
            (p4[0]-bx0, p4[1]-by0), (p3[0]-bx0, p3[1]-by0)
        ]

        # Spectral Color calculation
        base_r, base_g, base_b = self.ctx.primary_color[:3]
        h, s, v = colorsys.rgb_to_hsv(base_r/255, base_g/255, base_b/255)
        
        # Iridescence shift based on rotation angle
        hue_shift = (self._angle % (2 * math.pi)) / (2 * math.pi)
        h = (h + hue_shift * (self.iridescence / 100.0)) % 1.0
        
        # Fake "Lighting" based on facet surface normal
        light_intensity = abs(math.cos(self._angle))
        v = max(0.2, min(1.0, v * (0.5 + light_intensity)))
        
        alpha = int(255 * self.ctx.brush_opacity * (1.0 - (self.transparency / 120.0)))
        rgb = [int(c * 255) for c in colorsys.hsv_to_rgb(h, s, v)]
        
        # 1. Draw Aura/Glow
        if self.glow_power > 0:
            glow_color = tuple(rgb) + (alpha // 8,)
            draw.polygon(facet, fill=glow_color)

        # 2. Draw Main Facet
        draw.polygon(facet, fill=tuple(rgb) + (alpha,))
        
        # 3. Draw Edge Highlight
        edge_alpha = min(255, alpha + 50)
        draw.line([facet[0], facet[3]], fill=tuple(rgb) + (edge_alpha,), width=1)
        
        # 4. Dimension Shards (Geometric Debris)
        if random.random() * 100 < self.shard_chance:
            sx, sy = facet[0]
            size = random.uniform(2, self.foliage_size if hasattr(self, 'foliage_size') else 10)
            shard_pts = []
            for _ in range(3):
                shard_pts.append((sx + random.uniform(-20, 20), sy + random.uniform(-20, 20)))
            draw.polygon(shard_pts, fill=tuple(rgb) + (alpha // 2,))

        # Post Process
        if self.glow_power > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.glow_power / 5.0))

        # Composite
        layer.image.alpha_composite(scratch, dest=(bx0, by0))
        
        # Update state
        self._prev_edge = new_edge

TOOL_CLASS = FoldedDimensionBrushTool