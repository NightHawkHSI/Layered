"""Small image-placement helpers used by the import flow."""
from __future__ import annotations

from PIL import Image


def fit_to_canvas(image: Image.Image, canvas_w: int, canvas_h: int) -> Image.Image:
    """Scale `image` down to fit within (canvas_w, canvas_h) preserving aspect.

    Returns the original image untouched if it already fits.
    """
    iw, ih = image.size
    if iw <= canvas_w and ih <= canvas_h:
        return image
    s = min(canvas_w / iw, canvas_h / ih)
    new_w = max(1, int(round(iw * s)))
    new_h = max(1, int(round(ih * s)))
    return image.resize((new_w, new_h), Image.Resampling.LANCZOS)


def centered_offset(image_size: tuple[int, int], canvas_w: int, canvas_h: int) -> tuple[int, int]:
    iw, ih = image_size
    return ((canvas_w - iw) // 2, (canvas_h - ih) // 2)


def place_on_canvas(
    image: Image.Image,
    canvas_w: int,
    canvas_h: int,
    *,
    center: bool = True,
    scale_to_fit: bool = True,
) -> Image.Image:
    """Return a canvas-sized RGBA image with `image` placed inside.

    If `scale_to_fit` and the image is larger than the canvas, the image is
    scaled down. If `center`, the image is centered; otherwise it is anchored
    at (0, 0).
    """
    if image.mode != "RGBA":
        image = image.convert("RGBA")
    if scale_to_fit:
        image = fit_to_canvas(image, canvas_w, canvas_h)
    base = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    if center:
        ox, oy = centered_offset(image.size, canvas_w, canvas_h)
    else:
        ox, oy = 0, 0
    base.paste(image, (ox, oy), image)
    return base
