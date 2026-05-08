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
# TOOL: Neural Circuit (Cybernetic Trace Brush)
# —————————————————————————————————————————————————————————————————————————————

class NeuralCircuitBrushTool(Tool):

    name = "Neural Circuit"
    icon = "🔌"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Tech Parameters
        self.complexity     = 3      # Number of bus lines
        self.trace_length   = 100    # How far the signal travels
        self.snap_angle     = 45     # 45 or 90 degree logic
        
        # Component Density
        self.node_chance    = 60     # Chance of solder pads
        self.chip_chance    = 15     # Chance of IC blocks
        
        # Visuals
        self.line_width     = 2
        self.glow_radius    = 4
        self.pulse_intensity = 0.8
        
        # Internals
        self._last_pt: tuple[int, int] | None = None
        self._stroke_angle: float = 0.0

    # —————————————————————————————————————————————————————————————————————————
    # UI
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Circuit Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(180)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("complexity",   "Bus Count",       1,    8, False),
            ("trace_length", "Trace Reach",    20,  400, False),
            ("snap_angle",   "Angle Snap",     45,   90, False), # 45 or 90
            ("node_chance",  "Pad Density %",   0,  100, False),
            ("chip_chance",  "Silicon Logic %", 0,   50, False),
            ("line_width",   "Trace Width",     1,   10, False),
            ("glow_radius",  "Digital Bloom",   0,   30, False),
            ("pulse_intensity", "Data Pulse",   1,   20, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #aaa;")
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
        return max(15.0, self.trace_length * 0.4)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        
        if (dx*dx + dy*dy) > 1:
            # Tech-style angle snapping
            raw_angle = math.atan2(dy, dx)
            snap = math.radians(self.snap_angle)
            self._stroke_angle = round(raw_angle / snap) * snap
            
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        alpha = int(255 * self.ctx.brush_opacity)
        r, g, b = self.ctx.primary_color[:3]

        pad = int(self.trace_length + self.glow_radius + 40)
        full_dim = pad * 2
        bx0, by0 = (cx - ox - pad), (cy - oy - pad)
        
        # Scratch layers
        scratch = Image.new("RGBA", (full_dim, full_dim), (0, 0, 0, 0))
        glow_layer = Image.new("RGBA", (full_dim, full_dim), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        g_draw = ImageDraw.Draw(glow_layer)
        
        scx, scy = pad, pad

        # Trace Bus logic
        bus_gap = self.line_width * 3
        for i in range(self.complexity):
            offset = (i - (self.complexity - 1) / 2) * bus_gap
            
            # Start position offset perpendicular to stroke
            sx = scx + math.cos(self._stroke_angle + math.pi/2) * offset
            sy = scy + math.sin(self._stroke_angle + math.pi/2) * offset
            
            self._draw_trace(draw, g_draw, sx, sy, self._stroke_angle, self.trace_length, (r, g, b, alpha))

        if self.glow_radius > 0:
            glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(self.glow_radius))
            # Boost glow saturation
            scratch.alpha_composite(glow_layer)

        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

    def _draw_trace(self, draw, g_draw, x, y, angle, length, color):
        segs = random.randint(2, 4)
        seg_len = length / segs
        
        px, py = x, y
        cur_angle = angle
        
        # Neon Pulse color
        pulse_col = (255, 255, 255, int(color[3] * self.pulse_intensity))

        for i in range(segs):
            # Manhattan/Manifold routing: only turn at set increments
            turn_chance = random.random()
            if turn_chance < 0.4:
                cur_angle += math.radians(self.snap_angle) * random.choice([-1, 1])
            elif turn_chance < 0.1: # Sharp reversal
                cur_angle += math.radians(180)
            
            nx = px + math.cos(cur_angle) * seg_len
            ny = py + math.sin(cur_angle) * seg_len
            
            # Draw primary trace
            draw.line([(px, py), (nx, ny)], fill=color, width=self.line_width)
            # Draw digital pulse glow
            g_draw.line([(px, py), (nx, ny)], fill=color[:3] + (color[3]//2,), width=self.line_width + 4)
            draw.line([(px, py), (nx, ny)], fill=pulse_col, width=max(1, self.line_width // 2))

            # Nodes (Pads)
            if random.random() * 100 < self.node_chance:
                ns = self.line_width * 2
                if random.random() > 0.5:
                    draw.rectangle([nx-ns, ny-ns, nx+ns, ny+ns], fill=color) # Solder Pad
                else:
                    draw.ellipse([nx-ns, ny-ns, nx+ns, ny+ns], outline=color, width=1) # Via

            # Logic Chips
            if i > 0 and random.random() * 100 < self.chip_chance:
                cw, ch = random.randint(10, 30), random.randint(10, 30)
                draw.rectangle([nx-cw/2, ny-ch/2, nx+cw/2, ny+ch/2], fill=color[:3] + (color[3]//4,))
                draw.rectangle([nx-cw/2, ny-ch/2, nx+cw/2, ny+ch/2], outline=color, width=1)
                # Pin details
                for p in range(0, cw, 4):
                    draw.line([nx-cw/2 + p, ny-ch/2, nx-cw/2 + p, ny-ch/2-2], fill=color)
                    draw.line([nx-cw/2 + p, ny+ch/2, nx-cw/2 + p, ny+ch/2+2], fill=color)

            px, py = nx, ny

TOOL_CLASS = NeuralCircuitBrushTool