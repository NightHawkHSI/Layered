"""GPU-accelerated layer compositor using moderngl.

Soft-imports ``moderngl``. When unavailable, :func:`gpu_available` returns
False and callers should fall back to :class:`tile_renderer.TileRenderer`
or :meth:`LayerStack.composite`.

Architecture
------------
* One RGBA8 texture per layer, lazily (re-)uploaded when the source PIL
  image's identity (``id``) changes.
* A target framebuffer the size of the canvas; layers composite into it
  in stack order using a single fragment shader that branches on a blend
  mode integer.
* The tile renderer's dirty-rect system maps cleanly onto a future GPU
  scissor-rect path. This file ships the full-canvas variant first;
  scissor / per-tile is a small extension once measured useful.

The shader covers the same nine modes as :mod:`blending`. Porter-Duff
"over" alpha compositing is built into the fragment math so the host
can stop allocating intermediate PIL images for the common case.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

from .layer import LayerStack


try:  # soft-import — moderngl is optional
    import moderngl   # type: ignore
    _HAS_GL = True
except Exception:
    moderngl = None     # type: ignore[assignment]
    _HAS_GL = False


def gpu_available() -> bool:
    return _HAS_GL


# ----------------------------------------------------------------------
# GLSL kernels
# ----------------------------------------------------------------------

_VS = """
#version 330
in vec2 in_pos;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

# Blend mode IDs intentionally match `blending._MODE_*`.
_FS = """
#version 330
uniform sampler2D u_base;
uniform sampler2D u_top;
uniform sampler2D u_mask;
uniform int  u_mode;
uniform float u_opacity;
uniform int  u_use_mask;
in vec2 v_uv;
out vec4 frag;

vec3 blend(vec3 b, vec3 t, int mode) {
    if (mode == 1) return b * t;                                // Multiply
    if (mode == 2) return 1.0 - (1.0 - b) * (1.0 - t);           // Screen
    if (mode == 3) return mix(2.0 * b * t,
                              1.0 - 2.0 * (1.0 - b) * (1.0 - t),
                              step(0.5, b));                     // Overlay
    if (mode == 4) return min(b, t);                             // Darken
    if (mode == 5) return max(b, t);                             // Lighten
    if (mode == 6) return clamp(b + t, 0.0, 1.0);                // Add
    if (mode == 7) return clamp(b - t, 0.0, 1.0);                // Subtract
    if (mode == 8) return abs(b - t);                            // Difference
    return t;                                                    // Normal
}

void main() {
    vec4 base = texture(u_base, v_uv);
    vec4 top  = texture(u_top,  v_uv);
    if (u_use_mask == 1) {
        top.a *= texture(u_mask, v_uv).r;
    }
    top.a *= u_opacity;
    vec3 c = blend(base.rgb, top.rgb, u_mode);
    float a_out = top.a + base.a * (1.0 - top.a);
    vec3 rgb_out = (c * top.a + base.rgb * base.a * (1.0 - top.a))
                   / max(a_out, 1e-6);
    frag = vec4(rgb_out, a_out);
}
"""


_MODE_LOOKUP = {
    "Normal": 0, "Multiply": 1, "Screen": 2, "Overlay": 3,
    "Darken": 4, "Lighten": 5, "Add": 6, "Subtract": 7, "Difference": 8,
}


# ----------------------------------------------------------------------
# Renderer
# ----------------------------------------------------------------------

class GpuRenderer:
    """moderngl-backed compositor for a LayerStack.

    Construct once per project; call :meth:`render` to get a freshly
    composited PIL image.

    Raises RuntimeError if moderngl is not installed; check
    :func:`gpu_available` first.
    """

    def __init__(self, stack: LayerStack):
        if not _HAS_GL:
            raise RuntimeError("moderngl not installed — run `pip install moderngl`")
        self.stack = stack
        self.ctx = moderngl.create_standalone_context()
        self.prog = self.ctx.program(vertex_shader=_VS, fragment_shader=_FS)
        # Fullscreen quad
        quad = np.array([
            -1.0, -1.0, 0.0, 1.0,
             1.0, -1.0, 1.0, 1.0,
            -1.0,  1.0, 0.0, 0.0,
             1.0,  1.0, 1.0, 0.0,
        ], dtype="f4")
        self.vbo = self.ctx.buffer(quad.tobytes())
        self.vao = self.ctx.simple_vertex_array(self.prog, self.vbo, "in_pos", "in_uv")

        # Ping-pong FBOs so each layer reads from the previous composite.
        self._fbo_a = self._make_fbo()
        self._fbo_b = self._make_fbo()

        # Per-layer texture cache: id(layer.image) -> (texture, version)
        self._tex_cache: dict[int, moderngl.Texture] = {}
        self._mask_cache: dict[int, moderngl.Texture] = {}

    def _make_fbo(self):
        tex = self.ctx.texture((self.stack.width, self.stack.height), components=4)
        tex.repeat_x = False; tex.repeat_y = False
        tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        return self.ctx.framebuffer(color_attachments=[tex])

    # ------------------------------------------------------------------
    # Texture upload
    # ------------------------------------------------------------------

    def _upload(self, img: Image.Image, cache: dict, mode: str) -> "moderngl.Texture":
        key = id(img)
        cached = cache.get(key)
        if cached is not None and cached.size == img.size:
            return cached
        if img.mode != mode:
            img = img.convert(mode)
        if cached is not None:
            cached.release()
        tex = self.ctx.texture(img.size, components=4 if mode == "RGBA" else 1,
                               data=img.tobytes())
        tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
        cache[key] = tex
        return tex

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------

    def render(self) -> Image.Image:
        w, h = self.stack.width, self.stack.height
        if self._fbo_a.size != (w, h):
            self._fbo_a.release(); self._fbo_b.release()
            self._fbo_a = self._make_fbo()
            self._fbo_b = self._make_fbo()

        # Clear FBO A to transparent — running base.
        self._fbo_a.use(); self._fbo_a.clear(0.0, 0.0, 0.0, 0.0)

        cur_base, cur_dst = self._fbo_a, self._fbo_b

        for layer in self.stack.layers:
            if not layer.visible or layer.opacity <= 0.0:
                continue
            if layer.is_adjustment:
                # GPU path for adjustments not yet implemented — read
                # back, run CPU filter, re-upload. Profitable to keep
                # adjustments rare; fast path optimises pixel layers.
                self._cpu_adjustment_pass(cur_base, cur_dst, layer)
                cur_base, cur_dst = cur_dst, cur_base
                continue

            positioned = self.stack._positioned(layer)
            tex = self._upload(positioned, self._tex_cache, "RGBA")
            base_tex = cur_base.color_attachments[0]
            base_tex.use(0)
            tex.use(1)

            use_mask = 0
            if layer.mask is not None and layer.mask_enabled:
                m = layer.mask
                if m.size != (w, h):
                    canvas_m = Image.new("L", (w, h), 0)
                    canvas_m.paste(m, layer.offset)
                    m = canvas_m
                m_tex = self._upload(m, self._mask_cache, "L")
                m_tex.use(2)
                use_mask = 1

            self.prog["u_base"].value = 0
            self.prog["u_top"].value = 1
            self.prog["u_mask"].value = 2
            self.prog["u_mode"].value = _MODE_LOOKUP.get(layer.blend_mode, 0)
            self.prog["u_opacity"].value = float(layer.opacity)
            self.prog["u_use_mask"].value = use_mask

            cur_dst.use(); cur_dst.clear(0.0, 0.0, 0.0, 0.0)
            self.vao.render(moderngl.TRIANGLE_STRIP)
            cur_base, cur_dst = cur_dst, cur_base

        # Read back final composite into a PIL image.
        data = cur_base.read(components=4)
        return Image.frombytes("RGBA", (w, h), data)

    def _cpu_adjustment_pass(self, src_fbo, dst_fbo, layer) -> None:
        """Read GPU composite back, apply CPU adjustment, write to dst_fbo."""
        w, h = self.stack.width, self.stack.height
        base = Image.frombytes("RGBA", (w, h), src_fbo.read(components=4))
        from .adjustments import apply_adjustment
        filtered = apply_adjustment(base, layer.adjustment, layer.adjustment_params)
        mask = Image.new("L", (w, h), 255)
        if layer.mask is not None and layer.mask_enabled:
            m = layer.mask
            full = Image.new("L", (w, h), 0)
            if m.size != layer.image.size:
                m = m.resize(layer.image.size)
            full.paste(m, layer.offset)
            mask = full
        if layer.opacity < 0.999:
            mask = mask.point(lambda v: int(v * layer.opacity))
        out = Image.composite(filtered, base, mask)
        dst_fbo.use(); dst_fbo.clear(0.0, 0.0, 0.0, 0.0)
        # Direct texture upload bypass: write straight into the dst attachment.
        tex = dst_fbo.color_attachments[0]
        tex.write(out.tobytes())

    # ------------------------------------------------------------------
    # Resource cleanup
    # ------------------------------------------------------------------

    def release(self) -> None:
        for tex in self._tex_cache.values():
            try: tex.release()
            except Exception: pass
        for tex in self._mask_cache.values():
            try: tex.release()
            except Exception: pass
        self._tex_cache.clear()
        self._mask_cache.clear()
        try: self._fbo_a.release()
        except Exception: pass
        try: self._fbo_b.release()
        except Exception: pass
        try: self.vao.release()
        except Exception: pass
        try: self.vbo.release()
        except Exception: pass
        try: self.prog.release()
        except Exception: pass
        try: self.ctx.release()
        except Exception: pass
