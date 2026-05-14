"""Selection controller: select-all / deselect / invert / transform /
fill / erase / crop-to-selection.

Owns every operation that reads or mutates the active project's
``selection`` field plus the fill/erase paths that consume that mask.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Tuple

from PIL import Image, ImageChops

from app.core.project import Selection

if TYPE_CHECKING:
    from ..main_window import MainWindow


class SelectionController:
    def __init__(self, win: "MainWindow") -> None:
        self.win = win

    # --- query --------------------------------------------------------------

    def selection_or_full(self) -> Selection:
        """Return the current selection, or a full-canvas rect if there's none.
        Lets copy/paste treat \"no selection = whole canvas\" without having
        every caller re-implement that fallback."""
        proj = self.win.current()
        if proj.selection is not None:
            return proj.selection
        cw, ch = proj.stack.width, proj.stack.height
        return Selection.rect(0, 0, cw, ch, cw, ch)

    # --- replace / clear ----------------------------------------------------

    def set_selection(self, sel) -> None:
        proj = self.win.current()
        proj.selection = sel
        self.win.canvas.refresh()
        if hasattr(self.win, "_plugin_event_listeners"):
            self.win.emit_event("selection_changed")

    def select_all(self) -> None:
        proj = self.win.current()
        cw, ch = proj.stack.width, proj.stack.height
        proj.selection = Selection.rect(0, 0, cw, ch, cw, ch)
        self.win.canvas.refresh()

    def deselect(self) -> None:
        proj = self.win.current()
        if proj.selection is None:
            return
        proj.selection = None
        self.win.canvas.refresh()

    # --- invert / transform -------------------------------------------------

    def invert(self) -> None:
        proj = self.win.current()
        cw, ch = proj.stack.width, proj.stack.height
        if proj.selection is None:
            proj.selection = Selection.rect(0, 0, cw, ch, cw, ch)
            self.win.canvas.refresh()
            return
        sel_mask = self._mask_at_canvas(proj.selection.mask, cw, ch)
        inverted = sel_mask.point(lambda v: 255 - v)
        bb = inverted.getbbox()
        proj.selection = Selection(bbox=bb, mask=inverted) if bb else None
        self.win.canvas.refresh()

    def transform(self) -> None:
        proj = self.win.current()
        if proj.selection is None:
            self.win.statusBar().showMessage("No selection to transform.")
            return
        name = self.win._tool_name_by_id("sel_transform")
        if name is None:
            return
        self.win._on_tool_selected(name)

    # --- fill / erase -------------------------------------------------------

    def fill_with(self, color: Tuple[int, int, int, int]) -> None:
        win = self.win
        proj = win.current()
        layer = proj.stack.active
        if layer is None:
            return
        cw, ch = proj.stack.width, proj.stack.height
        ox, oy = layer.offset
        if proj.selection is None:
            layer_mask = Image.new("L", layer.image.size, 255)
        else:
            sel_mask = self._mask_at_canvas(proj.selection.mask, cw, ch)
            layer_mask = Image.new("L", layer.image.size, 0)
            layer_mask.paste(sel_mask, (-ox, -oy))
        fill_layer = Image.new("RGBA", layer.image.size, color)
        r, g, b, a = fill_layer.split()
        fill_layer = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, layer_mask)))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src.alpha_composite(fill_layer)
        layer.image = src
        proj.stack.invalidate_cache()
        win.canvas.refresh()
        win._mark_dirty()
        win.history_ctrl.commit("Fill")

    def fill_primary(self) -> None:
        self.fill_with(self.win.tool_ctx.primary_color)

    def fill_secondary(self) -> None:
        self.fill_with(self.win.tool_ctx.secondary_color)

    def erase(self) -> None:
        win = self.win
        proj = win.current()
        layer = proj.stack.active
        if layer is None or proj.selection is None:
            return
        cw, ch = proj.stack.width, proj.stack.height
        sel_mask = self._mask_at_canvas(proj.selection.mask, cw, ch)
        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(sel_mask, (-ox, -oy))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        r, g, b, a = src.split()
        keep = layer_mask.point(lambda v: 255 - v)
        layer.image = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, keep)))
        proj.stack.invalidate_cache()
        win.canvas.refresh()
        win._mark_dirty()
        win.history_ctrl.commit("Erase selection")

    # --- crop ---------------------------------------------------------------

    def crop_to_selection(self) -> None:
        win = self.win
        proj = win.current()
        sel = proj.selection
        if sel is None:
            win.statusBar().showMessage("No selection to crop to.")
            return
        x0, y0, x1, y1 = sel.bbox
        new_w, new_h = x1 - x0, y1 - y0
        if new_w <= 0 or new_h <= 0:
            return
        stack = proj.stack
        for layer in stack.layers:
            ox, oy = layer.offset
            new_img = Image.new("RGBA", (new_w, new_h), (0, 0, 0, 0))
            new_img.paste(layer.image, (ox - x0, oy - y0))
            layer.image = new_img
            layer.offset = (0, 0)
        stack.width, stack.height = new_w, new_h
        proj.selection = None
        stack.invalidate_cache()
        win.canvas.fit_to_window()
        win._mark_dirty()
        win.history_ctrl.commit(f"Crop to selection {new_w}×{new_h}")

    # --- helpers ------------------------------------------------------------

    @staticmethod
    def _mask_at_canvas(mask: Image.Image, cw: int, ch: int) -> Image.Image:
        """Return ``mask`` resized/padded to ``(cw, ch)`` without altering it."""
        if mask.size == (cw, ch):
            return mask
        full = Image.new("L", (cw, ch), 0)
        full.paste(mask, (0, 0))
        return full
