import importlib.util, math, sys, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from app.layer import Layer
from app.tools import Tool

_K = "_layered_builtin_tools"
if _K not in sys.modules:
    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"
    _p = importlib.util.spec_from_file_location(_K, _s)
    _m = importlib.util.module_from_spec(_p)
    sys.modules[_K] = _m
    _p.loader.exec_module(_m)
_walk = sys.modules[_K]._walk


class LightningBrushTool(Tool):
    """Lightning / electric arc brush.

    Each stamp fires a branching lightning bolt from the cursor.  The bolt
    recurses outward, splitting into two sub-branches at random intervals,
    each branch getting thinner and more transparent until the depth limit
    is reached.  A soft glow bloom is composited behind the arcs.

    Settings
    --------
    Reach    – total bolt length in px (20–300)
    Branches – max recursion depth (1–5); higher = more splits
    Chaos    – how jagged / random the path is (0–100)
    Glow     – softness of the background bloom (0–8)
    Spread ° – angular fan for the initial bolts (10–360)
    """

    name = "Lightning"
    icon = "⚡"

    def __init__(self, ctx=None):
        super().__init__(ctx)
        self.reach      = 80
        self.branches   = 3
        self.chaos      = 60
        self.glow       = 4
        self.spread_deg = 360
        self._last_pt: tuple[int, int] | None = None

    def build_ui(self, parent, ctx):
        from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget
        from app.ui.slider_field import SliderField

        host = QWidget(parent)
        row  = QHBoxLayout(host)
        row.setContentsMargins(4, 0, 4, 0)
        row.setSpacing(10)

        def lbl(t):
            l = QLabel(t)
            l.setStyleSheet("font-size:11px;")
            return l

        for attr, label, lo, hi, w in [
            ("reach",      "Reach",    20, 300, 85),
            ("branches",   "Branches",  1,   5, 75),
            ("chaos",      "Chaos",     0, 100, 75),
            ("glow",       "Glow",      0,   8, 70),
            ("spread_deg", "Spread °", 10, 360, 80),
        ]:
            row.addWidget(lbl(label))
            s = SliderField(lo, hi, getattr(self, attr), slider_width=w)
            s.valueChanged.connect(lambda v, a=attr: setattr(self, a, int(v)))
            row.addWidget(s)

        row.addStretch()
        return host

    def _spacing(self):
        return max(4.0, self.reach * 0.7)

    def press(self, layer: Layer, x: int, y: int) -> None:
        self._last_pt = (x, y)
        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:
        if self._last_pt is None:
            self._last_pt = (x, y)
            return
        for px, py in _walk(self._last_pt, (x, y), self._spacing()):
            self._stamp(layer, px, py)
        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:
        super().release(layer, x, y)

    # ── stamp ─────────────────────────────────────────────────────────────────
    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:
        ox, oy  = layer.offset
        alpha   = int(255 * max(0.0, min(1.0, self.ctx.brush_opacity)))
        r, g, b = self.ctx.primary_color[:3]
        W, H    = layer.image.width, layer.image.height

        pad  = self.reach + self.glow * 2 + 4
        lx   = cx - ox;  ly = cy - oy
        bx0  = max(0, lx - pad);  bx1 = min(W, lx + pad)
        by0  = max(0, ly - pad);  by1 = min(H, ly + pad)
        bw   = bx1 - bx0;         bh  = by1 - by0
        if bw <= 0 or bh <= 0:
            return

        # glow layer (blurred)
        glow_img  = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        # sharp arcs layer
        arc_img   = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow_img)
        arc_draw  = ImageDraw.Draw(arc_img)

        rx, ry = lx - bx0, ly - by0

        # fire N primary bolts spread across the fan
        num_primary = max(1, self.ctx.brush_size // 8 + 1)
        half_spread = math.radians(self.spread_deg) / 2.0

        for i in range(num_primary):
            if num_primary == 1:
                base_angle = random.uniform(-half_spread, half_spread)
            else:
                base_angle = -half_spread + (2 * half_spread * i / (num_primary - 1))
                base_angle += random.uniform(-0.15, 0.15)

            self._bolt(
                arc_draw, glow_draw,
                rx, ry,
                base_angle,
                self.reach,
                alpha,
                r, g, b,
                depth=0,
                max_depth=max(1, self.branches),
                bw=bw, bh=bh,
            )

        # blur the glow layer
        if self.glow > 0:
            glow_img = glow_img.filter(
                ImageFilter.GaussianBlur(radius=self.glow)
            )

        layer.image.alpha_composite(glow_img, dest=(bx0, by0))
        layer.image.alpha_composite(arc_img,  dest=(bx0, by0))

    # ── recursive bolt ────────────────────────────────────────────────────────
    def _bolt(
        self,
        draw, glow_draw,
        x0, y0,
        angle,
        length,
        alpha,
        r, g, b,
        depth,
        max_depth,
        bw, bh,
    ):
        if length < 3 or alpha < 5:
            return

        chaos_f = self.chaos / 100.0
        # number of jagged segments for this bolt
        segs    = max(2, int(length / 8))
        seg_len = length / segs

        px, py  = float(x0), float(y0)
        cur_ang = angle

        for seg in range(segs):
            # jag the angle
            cur_ang += random.uniform(-chaos_f, chaos_f) * math.pi * 0.5
            nx = px + seg_len * math.cos(cur_ang)
            ny = py + seg_len * math.sin(cur_ang)

            # fade along the bolt
            seg_a = int(alpha * (1.0 - seg / segs * 0.4))
            width = max(1, 3 - depth)

            draw.line([(round(px), round(py)), (round(nx), round(ny))],
                      fill=(r, g, b, seg_a), width=width)

            # glow arc is thicker and dimmer
            glow_draw.line([(round(px), round(py)), (round(nx), round(ny))],
                           fill=(r, g, b, seg_a // 4), width=width + 2)

            # random branch split
            if (depth < max_depth
                    and seg > 0
                    and random.random() < 0.25):
                branch_angle  = cur_ang + random.choice((-1, 1)) * random.uniform(
                    0.3, 0.9
                )
                self._bolt(
                    draw, glow_draw,
                    nx, ny,
                    branch_angle,
                    length * random.uniform(0.4, 0.65),
                    int(alpha * 0.55),
                    r, g, b,
                    depth + 1,
                    max_depth,
                    bw, bh,
                )

            px, py = nx, ny


TOOL_CLASS = LightningBrushTool