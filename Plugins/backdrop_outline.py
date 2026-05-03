"""backdrop_outline.py — Backdrop & Soft Outline Generator for Layered.

Registered as a filter so the host's settings dialog drives live preview
automatically (see app.main_window._invoke_filter). Filter receives the
active layer image, returns the composite of (backdrop + sprite). To put
the backdrop on its own layer, duplicate the layer first, then run.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter

from app.plugin_api import Plugin, PluginContext, Setting


def _build_backdrop(
    sprite: Image.Image,
    fill_rgba: tuple[int, int, int, int],
    expand: int,
    softness: float,
) -> Image.Image:
    if sprite.mode != "RGBA":
        sprite = sprite.convert("RGBA")

    alpha = sprite.getchannel("A")

    if expand > 0:
        kernel = min(expand * 2 + 1, 201)
        dilated = alpha.filter(ImageFilter.MaxFilter(kernel))
    else:
        dilated = alpha.copy()

    if softness > 0:
        blurred = dilated.filter(ImageFilter.GaussianBlur(radius=softness))
        orig = np.array(alpha, dtype=np.float32)
        blur = np.array(blurred, dtype=np.float32)
        mask = np.maximum(orig, blur)
        mask = Image.fromarray(np.clip(mask, 0, 255).astype(np.uint8), "L")
    else:
        mask = dilated

    r, g, b, a = fill_rgba
    if a < 255:
        m = np.array(mask, dtype=np.float32) * (a / 255.0)
        mask = Image.fromarray(np.clip(m, 0, 255).astype(np.uint8), "L")

    plate = Image.new("RGBA", sprite.size, (r, g, b, 255))
    plate.putalpha(mask)
    return plate


def _filter_fn(
    img: Image.Image,
    *,
    fill_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    expand: int = 14,
    softness: float = 10.0,
    bake: bool = True,
) -> Image.Image:
    sprite = img if img.mode == "RGBA" else img.convert("RGBA")

    rgba = tuple(int(v) for v in fill_color)
    fill_rgba = rgba if len(rgba) == 4 else (*rgba, 255)

    backdrop = _build_backdrop(sprite, fill_rgba, expand, softness)

    if not bake:
        return backdrop

    out = backdrop.copy()
    out.paste(sprite, (0, 0), sprite)
    return out


class BackdropOutlinePlugin(Plugin):
    name = "Backdrop Outline"
    version = "2.0.0"
    author = ""

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Backdrop Outline",
            _filter_fn,
            settings=[
                Setting(
                    name="fill_color",
                    type="color",
                    default=(255, 255, 255, 255),
                    label="Fill Color",
                ),
                Setting(
                    name="expand",
                    type="int",
                    default=14,
                    label="Expand (px)",
                    min=0,
                    max=80,
                    step=1,
                ),
                Setting(
                    name="softness",
                    type="float",
                    default=10.0,
                    label="Softness",
                    min=0.0,
                    max=40.0,
                    step=0.5,
                ),
                Setting(
                    name="bake",
                    type="bool",
                    default=True,
                    label="Composite with sprite",
                ),
            ],
            category="Backdrop",
        )

        ctx.logger.info("Backdrop Outline registered as filter (live preview).")
