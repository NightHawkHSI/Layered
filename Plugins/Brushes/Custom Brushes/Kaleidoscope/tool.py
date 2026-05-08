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
# TOOL: Kaleidoscope / Mandala Brush
# —————————————————————————————————————————————————————————————————————————————

class KaleidoscopeBrushTool(Tool):

    name = "Kaleidoscope"
    icon = "❋"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Symmetry
        self.axes        = 8
        self.mirror      = 1
        
        # Line Properties
        self.line_width  = 4
        self.softness    = 0.5
        self.glow_radius = 0
        
        # Dynamic Effects
        self.hue_shift   = 0     # Cycles color during stroke
        
        # Internals
        self._center: tuple[float, float] = (0.0, 0.0)
        self._last_pt: tuple[float, float] | None = None
        self._hue_offset: float = 0.0

    # —————————————————————————————————————————————————————————————————————————
    # UI (Grid Layout Popup)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Kaleidoscope Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(180)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            # attr, label, lo, hi, is_float
            ("axes",        "Symmetry Axes", 2,   36, False),
            ("mirror",      "Mirror (0/1)",  0,    1, False),
            ("line_width",  "Line Width",    1,   50, False),
            ("glow_radius", "Glow Power",    0,   20, False),
            ("softness",    "Edge Softness", 0,   50, True),
            ("hue_shift",   "Rainbow Flow",  0,  100, False),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #ccc;")
            return l

        grid.addWidget(lbl("Brush Opacity"), 0, 0)
        s_opac = SliderField(1, 100, max(1, int(ctx.brush_opacity * 100)), slider_width=110)
        s_opac.valueChanged.connect(lambda v: setattr(ctx, "brush_opacity", v / 100.0))
        grid.addWidget(s_opac, 0, 1)

        for i, (attr, label, lo, hi, is_float) in enumerate(SLIDERS):
            grid.addWidget(lbl(label), i + 1, 0)
            val = getattr(self, attr)
            if is_float: val = int(val * 10)
            s = SliderField(lo, hi, val, slider_width=110)
            def make_h(a, f):
                return lambda v: setattr(self, a, v / 10.0 if f else int(v))
            s.valueChanged.connect(make_h(attr, is_float))
            grid.addWidget(s, i + 1, 1)

        wa = QWidgetAction(menu)
        wa.setDefaultWidget(panel)
        menu.addAction(wa)
        btn.setMenu(menu)
        return btn

    # —————————————————————————————————————————————————————————————————————————
    # Symmetry Math
    # —————————————————————————————————————————————————————————————————————————

    def _get_symmetric_points(self, x: float, y: float):
        """Returns a list of all symmetric coordinates for a given point."""
        cx, cy = self._center
        pts = []
        
        for i in range(self.axes):
            angle = (2 * math.pi * i) / self.axes
            cos_a = math.cos(angle)
            sin_a = math.sin(angle)
            
            # Rotate
            dx, dy = x - cx, y - cy
            rx = cx + dx * cos_a - dy * sin_a
            ry = cy + dx * sin_a + dy * cos_a
            pts.append((rx, ry))
            
            if self.mirror:
                # Reflect across the bisector of the wedge
                mid_angle = angle + math.pi / self.axes
                ma = mid_angle
                # Axis vector
                ax_x, ax_y = math.cos(ma), math.sin(ma)
                # Reflection
                dot = (rx - cx) * ax_x + (ry - cy) * ax_y
                mx = cx + 2 * dot * ax_x - (rx - cx)
                my = cy + 2 * dot * ax_y - (ry - cy)
                pts.append((mx, my))
                
        return pts

    # —————————————————————————————————————————————————————————————————————————
    # Stroke Logic
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        return max(1.5, self.line_width * 0.2)

    def press(self, layer: Layer, x: int, y: int) -> None:
        ox, oy = layer.offset
        self._center = (x - ox, y - oy)
        self._last_pt = (x - ox, y - oy)
        self._hue_offset = 0.0
        self._stamp_segment(layer, self._last_pt, self._last_pt)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None: return
        ox, oy = layer.offset
        cur_pt = (x - ox, y - oy)
        
        # Standard walk for smooth lines
        spacing = self._spacing()
        for px, py in _walk(
            (self._last_pt[0] + ox, self._last_pt[1] + oy),
            (x, y),
            spacing
        ):
            lx, ly = px - ox, py - oy
            self._stamp_segment(layer, self._last_pt, (lx, ly))
            self._last_pt = (lx, ly)
            
            # Progress hue
            if self.hue_shift > 0:
                self._hue_offset = (self._hue_offset + self.hue_shift / 500.0) % 1.0

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp_segment(self, layer: Layer, p0: tuple[float, float], p1: tuple[float, float]) -> None:
        W, H = layer.image.width, layer.image.height
        alpha = int(255 * self.ctx.brush_opacity)
        
        # Calculate color with Hue Shift
        r, g, b = self.ctx.primary_color[:3]
        if self.hue_shift > 0:
            h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
            r, g, b = [int(c * 255) for c in colorsys.hsv_to_rgb((h + self._hue_offset) % 1.0, s, v)]

        # Get all symmetric lines
        points0 = self._get_symmetric_points(*p0)
        points1 = self._get_symmetric_points(*p1)
        
        # Bounding box for cluster
        all_x = [p[0] for p in points0 + points1]
        all_y = [p[1] for p in points0 + points1]
        
        pad = self.line_width + self.glow_radius + 5
        bx0, by0 = max(0, min(all_x) - pad), max(0, min(all_y) - pad)
        bx1, by1 = min(W, max(all_x) + pad), min(H, max(all_y) + pad)
        
        bw, bh = int(bx1 - bx0), int(by1 - by0)
        if bw <= 0 or bh <= 0: return

        # Scratch drawing
        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        
        for i in range(len(points0)):
            lp0 = (points0[i][0] - bx0, points0[i][1] - by0)
            lp1 = (points1[i][0] - bx0, points1[i][1] - by0)
            
            # Draw glow line if applicable
            if self.glow_radius > 0:
                draw.line([lp0, lp1], fill=(r, g, b, alpha // 3), width=self.line_width + self.glow_radius)
            
            # Draw core line
            draw.line([lp0, lp1], fill=(r, g, b, alpha), width=self.line_width)

        # Apply softness/blur
        total_blur = self.softness
        if self.glow_radius > 0:
            total_blur += (self.glow_radius / 4.0)
            
        if total_blur > 0.1:
            scratch = scratch.filter(ImageFilter.GaussianBlur(total_blur))

        # Composite
        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

TOOL_CLASS = KaleidoscopeBrushTool