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
# TOOL: Advanced Fur & Hair Brush
# —————————————————————————————————————————————————————————————————————————————

class FurBrushTool(Tool):

    name = "Fur"
    icon = "🦔"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Base strand properties
        self.strand_count = 15
        self.length       = 50
        self.spread_deg   = 45
        self.curl         = 12
        self.taper        = 80
        
        # Realism & Dynamics
        self.roughness    = 20
        self.root_jitter  = 5
        self.softness     = 0.5
        self.color_var    = 10
        self.flow_lerp    = 3.0  # How fast hair turns (stored as tenths)

        # Internals
        self._stroke_angle: float = -math.pi / 2
        self._last_pt: tuple[int, int] | None = None

    # —————————————————————————————————————————————————————————————————————————
    # UI (Grid Layout Popup)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Fur Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(150)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("strand_count", "Strands",      1,   60, False),
            ("length",       "Length",       4,  300, False),
            ("spread_deg",   "Spread °",     1,  360, False),
            ("curl",         "Curl/Wave",    0,   60, False),
            ("taper",        "Tip Taper %",  0,  100, False),
            ("roughness",    "Roughness",    0,  100, False),
            ("root_jitter",  "Root Scatter", 0,   50, False),
            ("color_var",    "Color Var",    0,   100, False),
            ("flow_lerp",    "Flow Speed",   1,  100, True),
            ("softness",     "Softness",     0,   50, True),
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
    # Stroke Lifecycle
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        return max(1.5, self.ctx.brush_size * self.ctx.brush_spacing * 0.3)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stroke_angle = -math.pi / 2
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None: return
        lx, ly = self._last_pt
        dx, dy = x - lx, y - ly
        
        if (dx*dx + dy*dy) > 1:
            target_angle = math.atan2(dy, dx)
            # Smoothly transition angle for grooming effect
            lerp_factor = self.flow_lerp / 10.0
            self._stroke_angle += (target_angle - self._stroke_angle) * min(1.0, lerp_factor)

        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Rendering
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        W, H = layer.image.width, layer.image.height
        alpha = int(255 * self.ctx.brush_opacity)
        r, g, b = self.ctx.primary_color[:3]

        # Shadow & Highlight prep
        dr, dg, db = [int(c * 0.4) for c in (r, g, b)] # Shadow color
        
        # Bounding box
        pad = int(self.length + self.curl + 10)
        bx0, by0 = max(0, cx - ox - pad), max(0, cy - oy - pad)
        bx1, by1 = min(W, cx - ox + pad), min(H, cy - oy + pad)
        bw, bh = bx1 - bx0, by1 - by0
        if bw <= 0 or bh <= 0: return

        scratch = Image.new("RGBA", (int(bw), int(bh)), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)

        rx, ry = cx - ox - bx0, cy - oy - by0
        half_spread = math.radians(self.spread_deg) / 2.0
        
        # Draw strands
        for _ in range(max(1, self.strand_count)):
            # Initial jittered root
            j_rx = rx + random.uniform(-self.root_jitter, self.root_jitter)
            j_ry = ry + random.uniform(-self.root_jitter, self.root_jitter)
            
            angle = self._stroke_angle + random.uniform(-half_spread, half_spread)
            strand_len = self.length * random.uniform(0.6, 1.1)
            
            # Strand specific variations
            curl_amp = self.curl * random.uniform(0.5, 1.2)
            curl_freq = random.uniform(0.5, 2.0)
            curl_phase = random.uniform(0, 6.28)
            
            # Color Variation
            cv = self.color_var
            sr, sg, sb = [max(0, min(255, c + random.randint(-cv, cv))) for c in (r, g, b)]

            steps = max(5, int(strand_len / 2))
            px, py = j_rx, j_ry

            for step in range(steps):
                t = step / steps
                next_t = (step + 1) / steps
                
                # Sine Wave Curl logic
                def get_pos(time):
                    dist = time * strand_len
                    # Add roughness jitter
                    rough = 0
                    if self.roughness > 0:
                        rough = (random.random() - 0.5) * (self.roughness / 5.0)
                    
                    off = math.sin(curl_freq * time * math.pi + curl_phase) * curl_amp + rough
                    
                    # Calculate position along angle + perpendicular offset
                    tx = j_rx + math.cos(angle) * dist + math.cos(angle + math.pi/2) * off
                    ty = j_ry + math.sin(angle) * dist + math.sin(angle + math.pi/2) * off
                    return tx, ty

                nx, ny = get_pos(next_t)
                
                # Tapering thickness
                width = max(1, int((self.ctx.brush_size / 10.0) * (1.0 - t * 0.8)))
                
                # Alpha fade at tip
                fade = 1.0 - (self.taper / 100.0) * t
                seg_a = int(alpha * max(0.0, fade))
                
                if seg_a < 2: break

                # Shadow pass (Root-bias)
                if t < 0.4:
                    draw.line([(px, py), (nx, ny)], fill=(dr, dg, db, int(seg_a * (1.0-t))), width=width+1)

                # Main hair color
                draw.line([(px, py), (nx, ny)], fill=(sr, sg, sb, seg_a), width=width)
                
                # Specular Highlight (Middle bias)
                if 0.3 < t < 0.7:
                    draw.line([(px, py), (nx, ny)], fill=(255, 255, 255, int(seg_a * 0.3)), width=max(1, width-1))

                px, py = nx, ny

        # Filtering
        if self.softness > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.softness))

        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

TOOL_CLASS = FurBrushTool