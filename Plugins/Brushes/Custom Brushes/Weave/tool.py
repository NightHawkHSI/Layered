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
# TOOL: Advanced Weave Brush
# —————————————————————————————————————————————————————————————————————————————

class WeaveBrushTool(Tool):

    name = "Weave"
    icon = "▦"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        
        # Pattern Controls
        self.cell_size   = 12
        self.thread_w    = 5
        self.angle_deg   = 0
        self.contrast    = 40
        
        # Realism
        self.softness    = 0.5
        self.color_shift = 15
        self.highlight   = 30
        
        # Internals
        self._last_pt = None

    # —————————————————————————————————————————————————————————————————————————
    # UI (Grid Layout Popup)
    # —————————————————————————————————————————————————————————————————————————

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import (
            QGridLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction
        )
        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)
        btn.setText("Weave Settings ▾")
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setFixedWidth(150)

        menu = QMenu(btn)
        panel = QWidget(menu)
        grid = QGridLayout(panel)
        grid.setContentsMargins(12, 10, 12, 10)
        grid.setSpacing(6)

        SLIDERS = [
            # attr, label, lo, hi, is_float
            ("cell_size",   "Cell Size",     4,   60, False),
            ("thread_w",    "Thread Width",  1,   30, False),
            ("angle_deg",   "Pattern °",     0,  180, False),
            ("contrast",    "Depth/Gap",     0,  100, False),
            ("highlight",   "3D Sheen",      0,  100, False),
            ("color_shift", "Fiber Var",     0,  100, False),
            ("softness",    "Edge Blur",     0,   50, True),
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
    # Logic
    # —————————————————————————————————————————————————————————————————————————

    def _spacing(self):
        return max(2.0, self.ctx.brush_size * self.ctx.brush_spacing * 0.4)

    def press(self, layer, x, y):
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer, x, y):
        if self._last_pt is None: return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy = layer.offset
        br = max(2, int(self.ctx.brush_size // 2))
        alpha = int(255 * self.ctx.brush_opacity)
        
        # Determine bounds
        pad = int(self.softness + 2)
        bx0, by0 = cx - ox - br - pad, cy - oy - br - pad
        bx1, by1 = cx - ox + br + pad, cy - oy + br + pad
        
        W, H = layer.image.width, layer.image.height
        bx0, by0 = max(0, bx0), max(0, by0)
        bx1, by1 = min(W, bx1), min(H, by1)
        
        bw, bh = int(bx1 - bx0), int(by1 - by0)
        if bw <= 0 or bh <= 0: return

        # Prep colors
        r, g, b = self.ctx.primary_color[:3]
        dark_f = 1.0 - (self.contrast / 100.0)
        dr, dg, db = [int(c * dark_f) for c in (r, g, b)]
        
        high_f = 1.0 + (self.highlight / 100.0)
        hr, hg, hb = [min(255, int(c * high_f)) for c in (r, g, b)]

        # Draw Weave Tile
        cell = max(4, self.cell_size)
        tw = max(1, min(self.thread_w, cell - 1))
        
        # Create a scratch area slightly larger than brush to handle rotation
        tile_sz = int((br + pad) * 2.5)
        scratch = Image.new("RGBA", (tile_sz, tile_sz), (0, 0, 0, 0))
        draw = ImageDraw.Draw(scratch)
        
        cols = (tile_sz // cell) + 2
        
        # 1. Background (The "Gaps")
        draw.rectangle([0, 0, tile_sz, tile_sz], fill=(0, 0, 0, alpha))

        for i in range(-1, cols):
            pos = i * cell
            
            for j in range(-1, cols):
                x_pos = j * cell
                y_pos = i * cell
                
                # Fiber color jitter
                if self.color_shift > 0:
                    v = random.randint(-self.color_shift, self.color_shift)
                    cr, cg, cb = [max(0, min(255, c + v)) for c in (r, g, b)]
                else:
                    cr, cg, cb = r, g, b

                # Weave Pattern Logic: (Row + Col) % 2
                # This alternates which thread passes "Over"
                if (i + j) % 2 == 0:
                    # Horizontal thread is OVER
                    # Vertical thread segment
                    draw.rectangle([x_pos + (cell-tw)//2, y_pos, x_pos + (cell+tw)//2, y_pos + cell], fill=(dr, dg, db, alpha))
                    # Horizontal thread segment
                    draw.rectangle([x_pos, y_pos + (cell-tw)//2, x_pos + cell, y_pos + (cell+tw)//2], fill=(cr, cg, cb, alpha))
                    # Add highlight on top thread
                    draw.line([x_pos + 2, y_pos + cell//2, x_pos + cell - 2, y_pos + cell//2], fill=(hr, hg, hb, alpha // 2), width=tw//3)
                else:
                    # Vertical thread is OVER
                    # Horizontal thread segment
                    draw.rectangle([x_pos, y_pos + (cell-tw)//2, x_pos + cell, y_pos + (cell+tw)//2], fill=(dr, dg, db, alpha))
                    # Vertical thread segment
                    draw.rectangle([x_pos + (cell-tw)//2, y_pos, x_pos + (cell+tw)//2, y_pos + cell], fill=(cr, cg, cb, alpha))
                    # Add highlight on top thread
                    draw.line([x_pos + cell//2, y_pos + 2, x_pos + cell//2, y_pos + cell - 2], fill=(hr, hg, hb, alpha // 2), width=tw//3)

        # 2. Rotate
        if self.angle_deg != 0:
            scratch = scratch.rotate(self.angle_deg, resample=Image.BILINEAR)

        # 3. Mask to Circle
        mask = Image.new("L", (tile_sz, tile_sz), 0)
        m_draw = ImageDraw.Draw(mask)
        m_draw.ellipse([tile_sz//2 - br, tile_sz//2 - br, tile_sz//2 + br, tile_sz//2 + br], fill=255)
        
        # Apply softness to mask
        if self.softness > 0:
            mask = mask.filter(ImageFilter.GaussianBlur(self.softness))
        
        final_tile = Image.new("RGBA", (tile_sz, tile_sz), (0, 0, 0, 0))
        final_tile.paste(scratch, (0, 0), mask)

        # 4. Composite
        # Calculate centering crop
        res_x = int(cx - ox - tile_sz // 2)
        res_y = int(cy - oy - tile_sz // 2)
        layer.image.alpha_composite(final_tile, dest=(res_x, res_y))

TOOL_CLASS = WeaveBrushTool