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
# TOOL: Overgrowth (Bio-Organic Vine Brush)
# —————————————————————————————————————————————————————————————————————————————

class OvergrowthBrushTool(Tool):

    name = "Overgrowth"
    icon = "🌿"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Growth Structure
        self.reach        = 80
        self.complexity   = 2    # recursion depth
        self.tangle       = 40   # jaggedness
        
        # Foliage
        self.leaf_density = 40   # % chance to spawn a leaf
        self.flower_pct   = 10   # % of leaves that become flowers
        self.foliage_size = 6
        
        # Visuals
        self.bloom        = 3.0
        self.flow_lerp    = 4.0  # How much it follows stroke direction
        self.color_shift  = 15   # Color variation
        
        # Internals
        self._last_pt: tuple[int, int] | None = None
        self._stroke_angle: float = -math.pi / 2

    # —————————————————————————————————————————————————————————————————————————
    # UI (Grid Layout Popup)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Overgrowth Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(180)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("reach",        "Reach (px)",      20,  300, False),
            ("complexity",   "Branching",        1,    4, False),
            ("tangle",       "Tangle/Jagged",    0,  150, False),
            ("leaf_density", "Leaf Density %",   0,  100, False),
            ("foliage_size", "Foliage Size",     2,   20, False),
            ("flower_pct",   "Flower Chance %",  0,  100, False),
            ("bloom",        "Bloom/Glow",       0,   60, True),
            ("flow_lerp",    "Stroke Flow",      1,  100, True),
            ("color_shift",  "Organic Var",      0,  100, False),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 800, max(1, int(ctx.brush_size)), slider_width=110)
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

    def _spacing(self):
        return max(5.0, self.ctx.brush_size * 0.25)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stroke_angle = -math.pi / 2
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        
        if (dx*dx + dy*dy) > 1:
            target_angle = math.atan2(dy, dx)
            lerp = self.flow_lerp / 10.0
            self._stroke_angle += (target_angle - self._stroke_angle) * min(1.0, lerp)
            
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        alpha = int(255 * self.ctx.brush_opacity)
        r, g, b = self.ctx.primary_color[:3]

        # Padding for growth
        pad = int(self.reach + self.foliage_size + self.bloom + 20)
        full_dim = pad * 2
        bx0, by0 = (cx - ox - pad), (cy - oy - pad)
        
        scratch = Image.new("RGBA", (full_dim, full_dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        
        scx, scy = pad, pad
        num_vines = max(1, self.ctx.brush_size // 15)

        for _ in range(num_vines):
            # Spread roots slightly
            root_x = scx + random.uniform(-5, 5)
            root_y = scy + random.uniform(-5, 5)
            angle = self._stroke_angle + random.uniform(-0.5, 0.5)
            
            self._draw_vine(
                draw,
                root_x, root_y,
                angle,
                self.reach,
                alpha,
                (r, g, b),
                0
            )

        if self.bloom > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.bloom))

        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

    def _draw_vine(self, draw, x, y, angle, length, alpha, color, depth):
        if length < 5 or alpha < 10 or depth > self.complexity:
            return

        steps = max(4, int(length / 5))
        seg_len = length / steps
        tangle_rad = (self.tangle / 100.0) * 0.7
        
        px, py = x, y
        cur_angle = angle

        for i in range(steps):
            t = i / steps
            cur_angle += random.uniform(-tangle_rad, tangle_rad)
            nx = px + math.cos(cur_angle) * seg_len
            ny = py + math.sin(cur_angle) * seg_len
            
            # Organic Tapering
            width = max(1, int((self.ctx.brush_size / 8.0) * (1.0 - t * 0.7) - depth))
            seg_alpha = int(alpha * (1.0 - t * 0.3))
            
            # Color jitter for the vine
            cv = self.color_shift
            v_col = tuple(max(0, min(255, c + random.randint(-cv, cv))) for c in color) + (seg_alpha,)
            
            # Draw Vine Segment
            draw.line([(px, py), (nx, ny)], fill=v_col, width=width)
            
            # Leaf / Flower logic
            if random.random() * 100 < self.leaf_density:
                self._draw_foliage(draw, nx, ny, cur_angle + math.pi/2 * random.choice([-1, 1]), color, seg_alpha)

            # Branching
            if depth < self.complexity and random.random() < 0.15:
                fork_angle = cur_angle + random.uniform(0.5, 1.2) * random.choice([-1, 1])
                self._draw_vine(draw, nx, ny, fork_angle, length * 0.6, int(seg_alpha * 0.7), color, depth + 1)

            px, py = nx, ny

    def _draw_foliage(self, draw, x, y, angle, base_color, alpha):
        size = self.foliage_size * random.uniform(0.6, 1.2)
        
        if random.random() * 100 < self.flower_pct:
            # Draw a Flower (Bud)
            h, s, v = colorsys.rgb_to_hsv(base_color[0]/255, base_color[1]/255, base_color[2]/255)
            f_col = tuple(int(c * 255) for c in colorsys.hsv_to_rgb((h + 0.5) % 1.0, s, 1.0)) + (alpha,)
            draw.ellipse([x-size/2, y-size/2, x+size/2, y+size/2], fill=f_col)
        else:
            # Draw a Leaf (Pointed Polygon)
            # Slightly greener/yellow shift
            cv = self.color_shift
            l_col = (
                max(0, min(255, base_color[0] + random.randint(-cv, cv))),
                max(0, min(255, base_color[1] + 20 + cv)), # Shift green
                max(0, min(255, base_color[2] + random.randint(-cv, cv))),
                alpha
            )
            
            # 3-point leaf
            tip_x = x + math.cos(angle) * size * 2
            tip_y = y + math.sin(angle) * size * 2
            side_angle = angle + math.pi/2
            s1x = x + math.cos(side_angle) * size * 0.5
            s1y = y + math.sin(side_angle) * size * 0.5
            s2x = x - math.cos(side_angle) * size * 0.5
            s2y = y - math.sin(side_angle) * size * 0.5
            
            draw.polygon([(s1x, s1y), (tip_x, tip_y), (s2x, s2y)], fill=l_col)

TOOL_CLASS = OvergrowthBrushTool