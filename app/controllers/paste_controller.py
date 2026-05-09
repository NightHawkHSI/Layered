"""Paste / copy / cut controller.

The changelog cited paste edge cases (rounds 17-22) as a recurring
regression source: same-project vs cross-project, fits-canvas vs
oversized, internal clipboard vs system clipboard, anchor vs extend vs
crop. Owning the whole flow in one place keeps those branches visible
and lets each variant be exercised on its own.

Public surface called from MainWindow:
    copy(), cut(), paste(), paste_into_current(), image_from_clipboard()

Internal paste exec helpers (also used by the radial menu):
    paste_new_layer(), paste_into_layer(), paste_new_project()
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple

import numpy as np
from PIL import Image, ImageChops
from PyQt6.QtCore import QBuffer, QIODevice
from PyQt6.QtGui import QImage
from PyQt6.QtWidgets import QApplication, QMessageBox

from ..layer import Layer
from ..project import Project, Selection

if TYPE_CHECKING:
    from ..main_window import MainWindow


# Internal copy buffer payload: (image, original_bbox_or_None, source_project_or_None).
CopyBuffer = Optional[Tuple[Image.Image, Optional[Tuple[int, int, int, int]], Optional[Project]]]


class PasteController:
    def __init__(self, win: "MainWindow") -> None:
        self.win = win
        self.copy_buffer: CopyBuffer = None
        # Hold a ref so the radial menu popup isn't GC'd before it closes.
        self._radial_menu = None

    # --- copy / cut ---------------------------------------------------------

    def copy(self) -> None:
        win = self.win
        proj = win.current()
        layer = proj.stack.active
        if layer is None:
            return
        sel = win.selection_ctrl.selection_or_full()
        bb = sel.bbox
        ox, oy = layer.offset
        cw, ch = proj.stack.width, proj.stack.height

        # Build canvas-aligned RGBA buffer in NumPy. PIL's `paste` has
        # version-dependent RGBA-without-mask behaviour; doing the blit
        # manually keeps semi-transparent pixels lossless.
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src_arr = np.asarray(src, dtype=np.uint8)
        sh, sw = src_arr.shape[:2]
        canvas_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
        y0 = max(0, oy); y1 = min(ch, oy + sh)
        x0 = max(0, ox); x1 = min(cw, ox + sw)
        if y1 > y0 and x1 > x0:
            canvas_arr[y0:y1, x0:x1] = src_arr[y0 - oy:y1 - oy, x0 - ox:x1 - ox]

        bx0, by0, bx1, by1 = bb
        bx0 = max(0, min(cw, bx0)); bx1 = max(0, min(cw, bx1))
        by0 = max(0, min(ch, by0)); by1 = max(0, min(ch, by1))
        if bx1 <= bx0 or by1 <= by0:
            return
        crop_arr = canvas_arr[by0:by1, bx0:bx1].copy()

        sel_mask = sel.mask
        if sel_mask.size != (cw, ch):
            full = Image.new("L", (cw, ch), 0)
            full.paste(sel_mask, (0, 0))
            sel_mask = full
        mask_arr = np.asarray(sel_mask, dtype=np.uint16)[by0:by1, bx0:bx1]
        crop_arr[..., 3] = (
            crop_arr[..., 3].astype(np.uint16) * mask_arr // 255
        ).astype(np.uint8)
        cropped = Image.fromarray(crop_arr, mode="RGBA")

        # Tag with source project so a later paste can detect "same project"
        # (drop pixels back at original bbox) vs "different project / external"
        # (treat as new image, ask for size mode).
        self.copy_buffer = (cropped, (bx0, by0, bx1, by1), proj)
        self._push_image_to_clipboard(cropped)
        win.statusBar().showMessage(f"Copied {bx1 - bx0}×{by1 - by0} region")

    def cut(self) -> None:
        win = self.win
        self.copy()
        proj = win.current()
        layer = proj.stack.active
        if layer is None or self.copy_buffer is None:
            return
        sel = win.selection_ctrl.selection_or_full()
        cw, ch = proj.stack.width, proj.stack.height
        canvas_mask = sel.mask
        if canvas_mask.size != (cw, ch):
            full = Image.new("L", (cw, ch), 0)
            full.paste(canvas_mask, (0, 0))
            canvas_mask = full
        ox, oy = layer.offset
        layer_mask = Image.new("L", layer.image.size, 0)
        layer_mask.paste(canvas_mask, (-ox, -oy))
        src = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        r, g, b, a = src.split()
        keep = layer_mask.point(lambda v: 255 - v)
        layer.image = Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, keep)))
        proj.stack.invalidate_cache()
        win.canvas.refresh()
        win._mark_dirty()
        win.history_ctrl.commit("Cut selection")

    # --- paste --------------------------------------------------------------

    def paste(self) -> None:
        """Show a cursor-anchored radial menu of paste choices.

        Default: New Layer / Current Layer / New Project. When the
        clipboard image is bigger than the current canvas, the menu
        expands to four extend/keep × new/current variants so the user
        controls canvas resizing inline instead of through a modal.
        """
        win = self.win
        proj = win.current()
        if proj is None:
            return
        img, bb, source_proj, source_label = self._resolve_paste_source()
        if img is None:
            return
        cw, ch = proj.stack.width, proj.stack.height
        iw, ih = img.size
        bigger = iw > cw or ih > ch

        if bigger:
            labels = [
                "New Layer\n(keep canvas)",
                "Current Layer\n(keep canvas)",
                "New Layer\n(extend canvas)",
                "Current Layer\n(extend canvas)",
                "New Project",
            ]
            actions = [
                lambda: self.paste_new_layer(img, bb, source_proj, source_label, mode="crop"),
                lambda: self.paste_into_layer(img, bb, source_proj, source_label, extend=False),
                lambda: self.paste_new_layer(img, bb, source_proj, source_label, mode="extend"),
                lambda: self.paste_into_layer(img, bb, source_proj, source_label, extend=True),
                lambda: self.paste_new_project(img, source_label),
            ]
        else:
            labels = ["New Layer", "Current Layer", "New Project"]
            actions = [
                lambda: self.paste_new_layer(img, bb, source_proj, source_label, mode="anchor"),
                lambda: self.paste_into_layer(img, bb, source_proj, source_label, extend=False),
                lambda: self.paste_new_project(img, source_label),
            ]

        from PyQt6.QtGui import QCursor
        from ..ui.radial_menu import RadialMenu
        menu = RadialMenu(labels, win)
        menu.chosen.connect(lambda i: actions[i]())
        menu.show_at(QCursor.pos())
        self._radial_menu = menu

    def paste_into_current(self) -> None:
        """Ctrl+Shift+V — skip the radial menu and paste directly into
        the active layer."""
        img, bb, source_proj, source_label = self._resolve_paste_source()
        if img is None:
            return
        self.paste_into_layer(img, bb, source_proj, source_label, extend=False)

    # --- paste exec variants ------------------------------------------------

    def paste_new_layer(self, img, bb, source_proj, source_label: str, mode: str) -> None:
        """``mode``: 'anchor' (same-proj or fits), 'extend', 'crop'."""
        win = self.win
        proj = win.current()
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        cw, ch = proj.stack.width, proj.stack.height
        iw, ih = img.size

        if source_proj is proj and bb is not None:
            # Same project: drop pixels back at original bbox.
            img_arr = np.asarray(img, dtype=np.uint8)
            ihx, iwx = img_arr.shape[:2]
            bx, by = bb[0], bb[1]
            new_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
            y0 = max(0, by); y1 = min(ch, by + ihx)
            x0 = max(0, bx); x1 = min(cw, bx + iwx)
            if y1 > y0 and x1 > x0:
                new_arr[y0:y1, x0:x1] = img_arr[y0 - by:y1 - by, x0 - bx:x1 - bx]
            proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
            action_desc = "Paste selection"
        else:
            img_arr = np.asarray(img, dtype=np.uint8)
            ih_a, iw_a = img_arr.shape[:2]
            if mode == "extend":
                new_w, new_h = max(cw, iw), max(ch, ih)
                resized = (new_w, new_h) != (cw, ch)
                if resized:
                    proj.stack.resize_canvas(new_w, new_h)
                # Center pasted pixels in the (possibly enlarged) canvas
                # so the user sees them in the middle, not the top-left.
                new_arr = np.zeros((new_h, new_w, 4), dtype=np.uint8)
                ox = max(0, (new_w - iw_a) // 2)
                oy = max(0, (new_h - ih_a) // 2)
                new_arr[oy:oy + ih_a, ox:ox + iw_a] = img_arr
                proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
                if resized:
                    win.canvas.fit_to_window()
                action_desc = f"Paste ({source_label}) — extend canvas to {new_w}×{new_h}"
            elif mode == "anchor":
                ox = max(0, (cw - iw) // 2)
                oy = max(0, (ch - ih) // 2)
                new_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
                new_arr[oy:oy + ih_a, ox:ox + iw_a] = img_arr
                proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
                action_desc = f"Paste ({source_label}) — anchor full image"
            else:  # crop — fit pasted pixels to canvas, centered.
                new_arr = np.zeros((ch, cw, 4), dtype=np.uint8)
                ih_c = min(ih_a, ch); iw_c = min(iw_a, cw)
                # Pull from source center to keep visually-important pixels.
                src_x = max(0, (iw_a - iw_c) // 2)
                src_y = max(0, (ih_a - ih_c) // 2)
                dst_x = max(0, (cw - iw_c) // 2)
                dst_y = max(0, (ch - ih_c) // 2)
                new_arr[dst_y:dst_y + ih_c, dst_x:dst_x + iw_c] = img_arr[src_y:src_y + ih_c, src_x:src_x + iw_c]
                proj.stack.add_layer(Layer(name=source_label, image=Image.fromarray(new_arr, mode="RGBA")))
                action_desc = f"Paste ({source_label}) — crop to canvas"

        proj.stack.invalidate_cache()
        # Keep a selection around the pasted content so the user can
        # immediately fill/modify it (Paint.NET-style workflow).
        pasted_layer = proj.stack.active
        if pasted_layer is not None:
            pasted_img = pasted_layer.image
            if pasted_img.mode == "RGBA":
                alpha = pasted_img.split()[3]
                sel_mask = alpha.point(lambda a: 255 if a > 0 else 0)
            else:
                sel_mask = Image.new("L", pasted_img.size, 255)
            bb2 = sel_mask.getbbox()
            proj.selection = Selection(bbox=bb2, mask=sel_mask) if bb2 is not None else None
        else:
            proj.selection = None
        # add_layer should set active, but be explicit so the transform
        # tool below acts on the correct layer.
        proj.stack.set_active(len(proj.stack.layers) - 1)
        win.layer_panel.refresh()
        win.canvas.refresh()
        win._mark_dirty()
        win.history_ctrl.commit(action_desc)
        win._activate_transform_tool()

    def paste_into_layer(self, img, bb, source_proj, source_label: str, *, extend: bool) -> None:
        win = self.win
        proj = win.current()
        layer = proj.stack.active
        if layer is None:
            win.statusBar().showMessage("No active layer to paste into.")
            return
        if img.mode != "RGBA":
            img = img.convert("RGBA")

        if extend:
            cw, ch = proj.stack.width, proj.stack.height
            iw, ih = img.size
            new_w, new_h = max(cw, iw), max(ch, ih)
            if (new_w, new_h) != (cw, ch):
                proj.stack.resize_canvas(new_w, new_h)
                win.canvas.fit_to_window()

        ox, oy = layer.offset
        if source_proj is proj and bb is not None:
            cx, cy = bb[0], bb[1]
        else:
            cx, cy = 0, 0

        img_arr = np.asarray(img, dtype=np.uint8)
        ih, iw = img_arr.shape[:2]
        lw, lh = layer.image.size
        ly = cy - oy; lx = cx - ox
        y0 = max(0, ly); y1 = min(lh, ly + ih)
        x0 = max(0, lx); x1 = min(lw, lx + iw)
        if y1 <= y0 or x1 <= x0:
            win.statusBar().showMessage("Paste falls outside the active layer.")
            return
        buf = np.zeros((lh, lw, 4), dtype=np.uint8)
        buf[y0:y1, x0:x1] = img_arr[y0 - ly:y1 - ly, x0 - lx:x1 - lx]
        pasted = Image.fromarray(buf, mode="RGBA")
        src_layer = layer.image if layer.image.mode == "RGBA" else layer.image.convert("RGBA")
        src_layer.alpha_composite(pasted)
        layer.image = src_layer
        proj.selection = None
        proj.stack.invalidate_cache()
        win.layer_panel.refresh()
        win.canvas.refresh()
        win._mark_dirty()
        win.history_ctrl.commit(f"Paste into {layer.name}")

    def paste_new_project(self, img, source_label: str) -> None:
        win = self.win
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        w, h = img.size
        proj = Project.blank(w, h, name=source_label)
        # Replace the auto-Background with the pasted image so the new
        # project shows pixels immediately.
        proj.stack.layers = []
        proj.stack.active_index = -1
        proj.stack.add_layer(Layer(name=source_label, image=img, offset=(0, 0)))
        proj.dirty = True
        win.projects.append(proj)
        win.active_project = len(win.projects) - 1
        win._bind_current()
        win._refresh_tabs()

    # --- clipboard helpers --------------------------------------------------

    def _resolve_paste_source(self):
        """Return (img, bb, source_proj, source_label) or (None, None, None, '')."""
        cb = QApplication.clipboard()
        img: Optional[Image.Image] = None
        bb: Optional[Tuple[int, int, int, int]] = None
        source_proj: Optional[Project] = None
        source_label = "Pasted"
        if self.copy_buffer is not None:
            img, bb, source_proj = self.copy_buffer
            source_label = "Pasted Selection"
            if cb is not None and not cb.ownsClipboard():
                external = self.image_from_clipboard()
                if external is not None:
                    ext_img, ext_label = external
                    if ext_img.size != img.size:
                        img, source_label = ext_img, ext_label
                        bb = None
                        source_proj = None
        else:
            external = self.image_from_clipboard()
            if external is not None:
                img, source_label = external
        return img, bb, source_proj, source_label

    def image_from_clipboard(self) -> Optional[Tuple[Image.Image, str]]:
        cb = QApplication.clipboard()
        if cb is None:
            return None
        md = cb.mimeData()
        if md is None:
            return None

        if md.hasImage():
            qimg = cb.image()
            if not qimg.isNull():
                buf = QBuffer()
                buf.open(QIODevice.OpenModeFlag.ReadWrite)
                if qimg.save(buf, "PNG"):
                    img = Image.open(BytesIO(bytes(buf.data()))).convert("RGBA")
                    buf.close()
                    return img, "Pasted Image"
                buf.close()

        if md.hasUrls():
            for url in md.urls():
                if not url.isLocalFile():
                    continue
                path = url.toLocalFile()
                try:
                    img = Image.open(path).convert("RGBA")
                except Exception as e:
                    self.win.log.warning("Paste: could not open %s: %s", path, e)
                    continue
                return img, Path(path).stem or "Pasted Image"

        return None

    def _push_image_to_clipboard(self, img: Image.Image) -> None:
        cb = QApplication.clipboard()
        if cb is None:
            return
        rgba = img if img.mode == "RGBA" else img.convert("RGBA")
        data = rgba.tobytes("raw", "RGBA")
        qimg = QImage(data, rgba.width, rgba.height, rgba.width * 4,
                      QImage.Format.Format_RGBA8888).copy()
        cb.setImage(qimg)

    # --- modal fallback (legacy code path; kept for non-radial callers) ---

    def ask_paste_mode(self, img_size: Tuple[int, int],
                       canvas_size: Tuple[int, int]) -> Optional[str]:
        win = self.win
        iw, ih = img_size
        cw, ch = canvas_size
        bigger = iw > cw or ih > ch

        box = QMessageBox(win)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Paste Image")
        box.setText(f"Pasted image: {iw} × {ih}\nCanvas: {cw} × {ch}")
        info = "How should the image be placed?\n\n"
        if bigger:
            info += "• Extend Canvas — grow canvas so the full image fits.\n"
        info += (
            "• Anchor Full Image — keep canvas size; layer stores the full image so you "
            "can move/resize it later without losing pixels outside the canvas.\n"
            "• Crop to Canvas — keep canvas size; clip the image to canvas bounds (legacy)."
        )
        box.setInformativeText(info)

        extend_btn = box.addButton("Extend Canvas", QMessageBox.ButtonRole.AcceptRole) if bigger else None
        anchor_btn = box.addButton("Anchor Full Image", QMessageBox.ButtonRole.AcceptRole)
        crop_btn = box.addButton("Crop to Canvas", QMessageBox.ButtonRole.AcceptRole)
        cancel_btn = box.addButton(QMessageBox.StandardButton.Cancel)

        box.setDefaultButton(extend_btn if extend_btn is not None else anchor_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is None or clicked is cancel_btn:
            return None
        if clicked is extend_btn:
            return "extend"
        if clicked is anchor_btn:
            return "anchor"
        if clicked is crop_btn:
            return "crop"
        return None
