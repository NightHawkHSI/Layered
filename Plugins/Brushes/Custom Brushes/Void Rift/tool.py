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
# TOOL: Void Rift (Quantum Geometry Synthesis)
# —————————————————————————————————————————————————————————————————————————————

class VoidRiftBrushTool(Tool):

    name = "Void Rift"
    icon = "🧿"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Quantum Mesh Parameters
        self.reach        = 120    # Max distance to connect vertices
        self.entropy      = 30     # Chaos/Jitter in vertex placement
        self.density      = 5      # Vertices per stamp
        
        # Dimensional Visuals
        self.void_depth   = 60     # Dark matter intensity
        self.plasma_core  = 80     # Brightness of the rift center
        self.shard_decay  = 40     # How fast the mesh dissolves
        
        # Physics
        self.event_horizon = 5.0   # Glow/Bloom radius
        self.warp_factor   = 1.5   # Perspective distortion
        
        # Internals
        self._vertices: list[tuple[float, float, float]] = [] # x, y, age
        self._last_pt: tuple[int, int] | None = None

    # —————————————————————————————————————————————————————————————————————————
    # UI
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Void Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(180)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            ("reach",        "Event Horizon",   20,  500, False),
            ("density",      "Matter Flux",      1,   20, False),
            ("entropy",      "Entropy/Chaos",    0,  200, False),
            ("void_depth",   "Obsidian %",       0,  100, False),
            ("plasma_core",  "Plasma %",         0,  100, False),
            ("shard_decay",  "Decay Rate",       1,  100, False),
            ("event_horizon","Quantum Glow",     0,   50, True),
            ("warp_factor",  "Dimensional Warp", 1,   50, True),
        ]

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size: 11px; color: #889;")
            return l

        grid.addWidget(lbl("Rift Aperture"), 0, 0)
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

    def _spacing(self):
        return max(8.0, self.ctx.brush_size * 0.15)

    def press(self, layer, x, y):
        self._vertices.clear()
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    # —————————————————————————————————————————————————————————————————————————
    # Quantum Synthesis Engine
    # —————————————————————————————————————————————————————————————————————————

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        W, H = layer.image.width, layer.image.height
        
        # Update and decay existing vertices
        decay = self.shard_decay / 100.0
        self._vertices = [(vx, vy, va - decay) for vx, vy, va in self._vertices if va > 0]

        # Generate new Quantum Singularities
        for _ in range(self.density):
            angle = random.uniform(0, 2 * math.pi)
            dist = random.uniform(0, self.ctx.brush_size / 2.0)
            ent = (self.entropy / 10.0)
            vx = cx - ox + dist * math.cos(angle) + random.uniform(-ent, ent)
            vy = cy - oy + dist * math.sin(angle) + random.uniform(-ent, ent)
            self._vertices.append((vx, vy, 1.0)) # (x, y, age)

        # Bounding Box
        pad = int(self.reach + self.event_horizon + 20)
        bx0, by0 = max(0, cx - ox - pad), max(0, cy - oy - pad)
        bx1, by1 = min(W, cx - ox + pad), min(H, cy - oy + pad)
        bw, bh = int(bx1 - bx0), int(by1 - by0)
        if bw <= 0 or bh <= 0: return

        scratch = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)

        # Color Prep
        r, g, b = self.ctx.primary_color[:3]
        alpha = int(255 * self.ctx.brush_opacity)

        # TRIANGULATION MESH
        # We look for connections within the "Reach" distance
        for i, (v1x, v1y, v1a) in enumerate(self._vertices):
            connections = 0
            for j in range(i + 1, len(self._vertices)):
                v2x, v2y, v2a = self._vertices[j]
                
                dist = math.hypot(v1x - v2x, v1y - v2y)
                if dist < self.reach:
                    # Find a third vertex for a triangle
                    for k in range(j + 1, len(self._vertices)):
                        v3x, v3y, v3a = self._vertices[k]
                        if math.hypot(v1x - v3x, v1y - v3y) < self.reach:
                            
                            # Calculate Triangle Shading (Distance to cursor)
                            avg_x = (v1x + v2x + v3x) / 3.0
                            avg_y = (v1y + v2y + v3y) / 3.0
                            dist_to_cursor = math.hypot(avg_x - (cx - ox), avg_y - (cy - oy))
                            
                            # Shading Logic
                            t_alpha = int(alpha * v1a * v2a * v3a)
                            if t_alpha < 5: continue
                            
                            # Mix Obsidian (Dark) and Plasma (Light)
                            mix = max(0, min(1, dist_to_cursor / self.reach))
                            
                            # Obsidian Pass
                            darken = (self.void_depth / 100.0) * mix
                            tr = int(r * (1.0 - darken))
                            tg = int(g * (1.0 - darken))
                            tb = int(b * (1.0 - darken))
                            
                            # Plasma Pass (Center is bright)
                            brighten = (self.plasma_core / 100.0) * (1.0 - mix)
                            tr = min(255, int(tr + 255 * brighten))
                            tg = min(255, int(tg + 255 * brighten))
                            tb = min(255, int(tb + 255 * brighten))

                            poly = [
                                (v1x - bx0, v1y - by0),
                                (v2x - bx0, v2y - by0),
                                (v3x - bx0, v3y - by0)
                            ]
                            
                            draw.polygon(poly, fill=(tr, tg, tb, t_alpha // 2), outline=(tr, tg, tb, t_alpha))
                            
                            connections += 1
                            if connections > 3: break # Optimize: limit complexity
                if connections > 3: break

        # ANTI-MATTER PARTICLES (Leaking reality)
        for vx, vy, va in self._vertices:
            if random.random() < 0.2:
                px, py = vx - bx0, vy - by0
                s = random.uniform(1, 3)
                # Random sparks
                draw.ellipse([px-s, py-s, px+s, py+s], fill=(255, 255, 255, int(alpha * va)))

        # Bloom (Quantum Glow)
        if self.event_horizon > 0:
            scratch = scratch.filter(ImageFilter.GaussianBlur(self.event_horizon))

        # Composite
        layer.image.alpha_composite(scratch, dest=(int(bx0), int(by0)))

        # Maintain Vertex History (limit to prevent lag)
        if len(self._vertices) > 60:
            self._vertices = self._vertices[-60:]

TOOL_CLASS = VoidRiftBrushTool