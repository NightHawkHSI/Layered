import importlib.util
import math
import sys
import random
import colorsys

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.layer import Layer
from app.tools import Tool

# ─────────────────────────────────────────────────────────────────────────────
# load shared builtins
# ─────────────────────────────────────────────────────────────────────────────

_K = "_layered_builtin_tools"

if _K not in sys.modules:

    _s = Path(__file__).resolve().parents[3] / "_builtin_tools.py"

    _p = importlib.util.spec_from_file_location(_K, _s)

    _m = importlib.util.module_from_spec(_p)

    sys.modules[_K] = _m

    _p.loader.exec_module(_m)

_bt   = sys.modules[_K]
_walk = _bt._walk


# ─────────────────────────────────────────────────────────────────────────────
# TOOL
# ─────────────────────────────────────────────────────────────────────────────

class ConstellationBrushTool(Tool):

    name = "Constellation"
    icon = "✦"

    def __init__(self, ctx=None):

        super().__init__(ctx)

        # base
        self.star_count   = 8
        self.spread_pct   = 400
        self.connect_pct  = 500
        self.glow_radius  = 3

        # star controls
        self.min_star_size     = 1
        self.max_star_size     = 5

        # lines
        self.line_width        = 1
        self.connection_alpha  = 35

        # realism
        self.color_shift       = 18
        self.sparkle_chance    = 3
        self.big_star_chance   = 3

        # spacing/density
        self.density           = 100
        self.star_spacing_mult = 2.8

        # blur
        self.blur_strength     = 0.8

        # neon
        self.neon_chance       = 8    # % of stars that get neon treatment
        self.neon_intensity    = 1.2  # stored as tenths (slider 1-30)

        # internals
        self._prev_stars: list[tuple[int, int]] = []
        self._last_pt: tuple[int, int] | None = None

    # ─────────────────────────────────────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────────────────────────────────────

    def build_ui(self, parent, ctx):

        from PyQt6.QtWidgets import (
            QGridLayout,
            QLabel,
            QMenu,
            QToolButton,
            QWidget,
            QWidgetAction,
        )

        from app.ui.slider_field import SliderField

        btn = QToolButton(parent)

        btn.setText("Constellation ▾")

        btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        btn.setFixedWidth(140)

        menu = QMenu(btn)

        panel = QWidget(menu)

        grid = QGridLayout(panel)

        grid.setContentsMargins(10, 8, 10, 8)

        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)

        SLIDERS = [

            # attr, label, lo, hi, width, float?
            ("star_count",        "Stars",          1,   20, 110, False),
            ("spread_pct",        "Spread %",      10, 1000, 110, False),
            ("connect_pct",       "Connect %",      0, 1000, 110, False),
            ("glow_radius",       "Glow",           0,   12, 110, False),

            ("min_star_size",     "Min Size",       1,    8, 110, False),
            ("max_star_size",     "Max Size",       1,   20, 110, False),

            ("line_width",        "Line Width",     1,    8, 110, False),
            ("connection_alpha",  "Line Glow",      0,  100, 110, False),

            ("color_shift",       "Color Shift",    0,  100, 110, False),
            ("sparkle_chance",    "Sparkle %",      0,  100, 110, False),
            ("big_star_chance",   "Big Star %",     0,   50, 110, False),

            ("density",           "Density %",     10,  300, 110, False),

            # FLOAT SETTINGS
            ("star_spacing_mult", "Spacing",       1,   80, 110, True),
            ("blur_strength",     "Blur",          1,   50, 110, True),

            # NEON
            ("neon_chance",       "Neon %",        0,  100, 110, False),
            ("neon_intensity",    "Neon Glow",     1,   30, 110, True),

        ]

        def lbl(t):

            l = QLabel(t)

            l.setStyleSheet("""
                QLabel {
                    font-size: 11px;
                }
            """)

            return l

        # ── Brush Size (lives on ctx, not self) ───────────────────────────
        grid.addWidget(lbl("Brush Size"), 0, 0)
        s_size = SliderField(1, 500, max(1, int(ctx.brush_size)), slider_width=110)
        s_size.valueChanged.connect(lambda v: setattr(ctx, "brush_size", int(v)))
        grid.addWidget(s_size, 0, 1)

        # ── All other settings (on self) ──────────────────────────────────
        GRID_OFFSET = 1   # first row already used by Brush Size

        for i, (
            attr,
            label,
            lo,
            hi,
            width,
            is_float
        ) in enumerate(SLIDERS):

            row, col = divmod(i, 2)
            row += GRID_OFFSET   # push below the Brush Size row

            grid.addWidget(
                lbl(label),
                row,
                col * 2
            )

            current = getattr(self, attr)

            if is_float:
                current = int(current * 10)

            s = SliderField(
                lo,
                hi,
                current,
                slider_width=width
            )

            def make_handler(a, float_mode):

                def _handler(v):

                    if float_mode:
                        setattr(self, a, v / 10.0)
                    else:
                        setattr(self, a, int(v))

                return _handler

            s.valueChanged.connect(
                make_handler(attr, is_float)
            )

            grid.addWidget(
                s,
                row,
                col * 2 + 1
            )

        wa = QWidgetAction(menu)

        wa.setDefaultWidget(panel)

        menu.addAction(wa)

        btn.setMenu(menu)

        return btn

    # ─────────────────────────────────────────────────────────────────────────
    # spacing
    # ─────────────────────────────────────────────────────────────────────────

    def _spacing(self):

        return max(

            self.ctx.brush_size * 0.35,

            (
                self.ctx.brush_size *
                self.ctx.brush_spacing *
                self.star_spacing_mult
            )

        )

    # ─────────────────────────────────────────────────────────────────────────
    # stroke
    # ─────────────────────────────────────────────────────────────────────────

    def press(self, layer: Layer, x: int, y: int) -> None:

        self._last_pt = (x, y)

        self._prev_stars.clear()

        self._stamp(layer, x, y)

    def move(self, layer: Layer, x: int, y: int) -> None:

        if self._last_pt is None:

            self._last_pt = (x, y)

            return

        for px, py in _walk(
            self._last_pt,
            (x, y),
            self._spacing()
        ):
            self._stamp(layer, px, py)

        self._last_pt = (x, y)

    def release(self, layer: Layer, x: int, y: int) -> None:

        self._prev_stars.clear()

        super().release(layer, x, y)

    # ─────────────────────────────────────────────────────────────────────────
    # stamp
    # ─────────────────────────────────────────────────────────────────────────

    def _stamp(self, layer: Layer, cx: int, cy: int) -> None:

        ox, oy = layer.offset

        br = max(1, self.ctx.brush_size)

        spread_r = max(
            1,
            int(br * self.spread_pct / 100)
        )

        connect_r = int(
            br * self.connect_pct / 100
        )

        alpha = int(
            255 *
            max(
                0.0,
                min(1.0, self.ctx.brush_opacity)
            )
        )

        r, g, b = self.ctx.primary_color[:3]

        W, H = layer.image.width, layer.image.height

        # ─────────────────────────────────────────────────────────────────────
        # generate stars
        # ─────────────────────────────────────────────────────────────────────

        new_stars: list[tuple[int, int]] = []

        actual_star_count = max(
            1,
            int(
                self.star_count *
                (self.density / 100)
            )
        )

        for _ in range(actual_star_count):

            angle = random.uniform(
                0,
                2 * math.pi
            )

            dist = (
                random.uniform(0.0, 1.0) ** 1.8
            ) * spread_r

            sx = int(
                cx - ox +
                dist * math.cos(angle)
            )

            sy = int(
                cy - oy +
                dist * math.sin(angle)
            )

            if 0 <= sx < W and 0 <= sy < H:

                new_stars.append((sx, sy))

        if not new_stars:
            return

        # ─────────────────────────────────────────────────────────────────────
        # nearby previous stars
        # ─────────────────────────────────────────────────────────────────────

        close_prev: list[tuple[int, int]] = []

        if connect_r > 0 and self._prev_stars:

            for p in self._prev_stars:

                if any(

                    math.hypot(
                        nx - p[0],
                        ny - p[1]
                    ) <= connect_r

                    for nx, ny in new_stars
                ):
                    close_prev.append(p)

        # ─────────────────────────────────────────────────────────────────────
        # scratch bounds
        # ─────────────────────────────────────────────────────────────────────

        all_pts = new_stars + close_prev

        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]

        pad = max(
            int(self.glow_radius * 8 + self.max_star_size * 6),
            20
        )

        bx0 = max(0, min(xs) - pad)
        by0 = max(0, min(ys) - pad)

        bx1 = min(W, max(xs) + pad)
        by1 = min(H, max(ys) + pad)

        bw = bx1 - bx0
        bh = by1 - by0

        if bw <= 0 or bh <= 0:
            return

        scratch = Image.new(
            "RGBA",
            (bw, bh),
            (0, 0, 0, 0)
        )

        sd = ImageDraw.Draw(scratch)

        def lc(px, py):

            return (
                px - bx0,
                py - by0
            )

        # ─────────────────────────────────────────────────────────────────────
        # lines
        # ─────────────────────────────────────────────────────────────────────

        for (sx, sy) in new_stars:

            for (px, py) in close_prev:

                dist = math.hypot(
                    sx - px,
                    sy - py
                )

                if dist <= connect_r and dist > 0:

                    line_a = int(
                        alpha *
                        (self.connection_alpha / 100.0) *
                        (1.0 - dist / connect_r)
                    )

                    if line_a < 2:
                        continue

                    # glow line
                    sd.line(
                        [lc(sx, sy), lc(px, py)],
                        fill=(
                            r,
                            g,
                            b,
                            max(1, line_a // 6)
                        ),
                        width=max(
                            1,
                            self.line_width + 3
                        )
                    )

                    # sharp line
                    sd.line(
                        [lc(sx, sy), lc(px, py)],
                        fill=(
                            255,
                            255,
                            255,
                            line_a
                        ),
                        width=self.line_width
                    )

        # ─────────────────────────────────────────────────────────────────────
        # stars
        # ─────────────────────────────────────────────────────────────────────

        for (sx, sy) in new_stars:

            lx, ly = lc(sx, sy)

            size_bias = (
                random.uniform(0.0, 1.0) ** 2.4
            )

            dot_r = int(

                self.min_star_size +

                (
                    self.max_star_size -
                    self.min_star_size
                ) * size_bias

            )

            dot_r = max(
                self.min_star_size,
                min(
                    self.max_star_size,
                    dot_r
                )
            )

            brightness = random.uniform(
                0.65,
                1.45
            )

            cr = random.randint(
                -self.color_shift,
                self.color_shift
            )

            cg = random.randint(
                -self.color_shift,
                self.color_shift
            )

            cb = random.randint(
                -self.color_shift,
                self.color_shift
            )

            sr = max(
                0,
                min(
                    255,
                    int(r * brightness) + cr
                )
            )

            sg = max(
                0,
                min(
                    255,
                    int(g * brightness) + cg
                )
            )

            sb = max(
                0,
                min(
                    255,
                    int(b * brightness) + cb
                )
            )

            star_temp = random.random()

            if star_temp < 0.15:

                sr = min(255, sr + 40)
                sg = min(255, sg + 10)

            elif star_temp > 0.85:

                sb = min(255, sb + 50)

            star_alpha = int(
                alpha *
                random.uniform(0.7, 1.0)
            )

            # outer glow
            glow_r = dot_r + random.randint(3, 8)

            sd.ellipse(
                [
                    lx - glow_r,
                    ly - glow_r,
                    lx + glow_r,
                    ly + glow_r
                ],
                fill=(
                    sr,
                    sg,
                    sb,
                    max(1, star_alpha // 18)
                )
            )

            # inner glow
            inner_glow = dot_r + 2

            sd.ellipse(
                [
                    lx - inner_glow,
                    ly - inner_glow,
                    lx + inner_glow,
                    ly + inner_glow
                ],
                fill=(
                    sr,
                    sg,
                    sb,
                    max(1, star_alpha // 6)
                )
            )

            # core
            sd.ellipse(
                [
                    lx - dot_r,
                    ly - dot_r,
                    lx + dot_r,
                    ly + dot_r
                ],
                fill=(
                    255,
                    255,
                    255,
                    star_alpha
                )
            )

            # colored center
            if dot_r >= 2:

                sd.ellipse(
                    [
                        lx - dot_r + 1,
                        ly - dot_r + 1,
                        lx + dot_r - 1,
                        ly + dot_r - 1
                    ],
                    fill=(
                        sr,
                        sg,
                        sb,
                        int(star_alpha * 0.7)
                    )
                )

            # neon glow on random stars
            if random.random() < (self.neon_chance / 100.0):

                neon_hue = random.random()
                nr, ng, nb = [
                    int(c * 255)
                    for c in colorsys.hsv_to_rgb(neon_hue, 1.0, 1.0)
                ]
                mult = self.neon_intensity

                # wide outer bloom
                bloom = int(dot_r * 5 * mult) + random.randint(4, 14)
                sd.ellipse(
                    [
                        lx - bloom, ly - bloom,
                        lx + bloom, ly + bloom
                    ],
                    fill=(nr, ng, nb, max(1, star_alpha // 10))
                )

                # mid halo
                halo = int(dot_r * 2.5 * mult) + 3
                sd.ellipse(
                    [
                        lx - halo, ly - halo,
                        lx + halo, ly + halo
                    ],
                    fill=(nr, ng, nb, max(1, star_alpha // 4))
                )

                # saturated core
                sd.ellipse(
                    [
                        lx - dot_r, ly - dot_r,
                        lx + dot_r, ly + dot_r
                    ],
                    fill=(nr, ng, nb, star_alpha)
                )

                # bright white pinpoint
                sd.ellipse(
                    [
                        lx - 1, ly - 1,
                        lx + 1, ly + 1
                    ],
                    fill=(255, 255, 255, star_alpha)
                )
            if random.random() < (
                self.sparkle_chance / 100.0
            ):

                spike_len = (
                    dot_r +
                    random.randint(4, 10)
                )

                spike_alpha = max(
                    1,
                    int(star_alpha * 0.45)
                )

                sd.line(
                    [
                        lx - spike_len,
                        ly,
                        lx + spike_len,
                        ly
                    ],
                    fill=(
                        255,
                        255,
                        255,
                        spike_alpha
                    ),
                    width=1
                )

                sd.line(
                    [
                        lx,
                        ly - spike_len,
                        lx,
                        ly + spike_len
                    ],
                    fill=(
                        255,
                        255,
                        255,
                        spike_alpha
                    ),
                    width=1
                )

                if dot_r >= 2:

                    diag = int(spike_len * 0.7)

                    sd.line(
                        [
                            lx - diag,
                            ly - diag,
                            lx + diag,
                            ly + diag
                        ],
                        fill=(
                            255,
                            255,
                            255,
                            spike_alpha // 2
                        ),
                        width=1
                    )

                    sd.line(
                        [
                            lx - diag,
                            ly + diag,
                            lx + diag,
                            ly - diag
                        ],
                        fill=(
                            255,
                            255,
                            255,
                            spike_alpha // 2
                        ),
                        width=1
                    )

            # giant stars
            if random.random() < (
                self.big_star_chance / 100.0
            ):

                giant = (
                    dot_r +
                    random.randint(12, 24)
                )

                giant_alpha = max(
                    1,
                    int(star_alpha * 0.25)
                )

                sd.line(
                    [
                        lx - giant,
                        ly,
                        lx + giant,
                        ly
                    ],
                    fill=(
                        255,
                        255,
                        255,
                        giant_alpha
                    ),
                    width=1
                )

                sd.line(
                    [
                        lx,
                        ly - giant,
                        lx,
                        ly + giant
                    ],
                    fill=(
                        255,
                        255,
                        255,
                        giant_alpha
                    ),
                    width=1
                )

        # ─────────────────────────────────────────────────────────────────────
        # blur
        # ─────────────────────────────────────────────────────────────────────

        if self.glow_radius > 0:

            scratch = scratch.filter(

                ImageFilter.GaussianBlur(

                    radius=max(
                        0.1,
                        self.glow_radius *
                        self.blur_strength
                    )

                )

            )

        # ─────────────────────────────────────────────────────────────────────
        # composite
        # ─────────────────────────────────────────────────────────────────────

        layer.image.alpha_composite(
            scratch,
            dest=(bx0, by0)
        )

        # ─────────────────────────────────────────────────────────────────────
        # history
        # ─────────────────────────────────────────────────────────────────────

        self._prev_stars = (
            self._prev_stars +
            new_stars
        )[-60:]


TOOL_CLASS = ConstellationBrushTool