import numpy as np
from PIL import Image
from app.plugin_api import Plugin, PluginContext, Setting

class RetroVisionPlugin(Plugin):
    name = "Retro Vision"
    version = "1.2.0"

    # Define color palettes (R, G, B)
    PALETTES = {
        "GameBoy": [
            (15, 56, 15), (48, 98, 48), (139, 172, 15), (155, 188, 15)
        ],
        "Cyberpunk": [
            (2, 0, 20), (117, 0, 184), (255, 0, 110), (0, 245, 255)
        ],
        "1-Bit (B&W)": [
            (0, 0, 0), (255, 255, 255)
        ],
        "C64": [
            (0,0,0), (255,255,255), (136,0,0), (170,255,238),
            (204,68,204), (0,204,85), (0,0,170), (238,238,119)
        ]
    }

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Retro Console",
            self.apply_retro,
            settings=[
                Setting(
                    name="palette_name",
                    type="choice",
                    choices=list(self.PALETTES.keys()),
                    default="GameBoy",
                    label="Console Palette"
                ),
                Setting(
                    name="pixel_size",
                    type="int",
                    default=4,
                    label="Pixel Size (Downscale)",
                    min=1,
                    max=20
                ),
                Setting(
                    name="dither",
                    type="bool",
                    default=True,
                    label="Enable Dithering"
                ),
            ],
            category="Stylize"
        )

    def apply_retro(self, img: Image.Image, palette_name="GameBoy", pixel_size=4, dither=True) -> Image.Image:
        # 1. Pixelate: Scale down then scale back up
        orig_size = img.size
        small_w = max(1, orig_size[0] // pixel_size)
        small_h = max(1, orig_size[1] // pixel_size)
        
        # Convert to RGB (quantization doesn't work on RGBA directly)
        working_img = img.convert("RGB")
        working_img = working_img.resize((small_w, small_h), resample=Image.NEAREST)

        # 2. Build the palette image for Pillow to use as a map
        palette_data = self.PALETTES.get(palette_name, self.PALETTES["GameBoy"])
        
        # Flatten the list of tuples into a single list [r,g,b, r,g,b...]
        flat_palette = []
        for color in palette_data:
            flat_palette.extend(color)
        
        # Pad palette to 256 colors (768 values) as required by Pillow
        flat_palette.extend([0] * (768 - len(flat_palette)))
        
        palette_img = Image.new("P", (1, 1))
        palette_img.putpalette(flat_palette)

        # 3. Apply quantization (the magic part)
        # This maps the image colors to the nearest palette color
        dither_type = Image.FLOYDSTEINBERG if dither else Image.NONE
        working_img = working_img.quantize(palette=palette_img, dither=dither_type)

        # 4. Scale back to original size
        out = working_img.convert("RGBA").resize(orig_size, resample=Image.NEAREST)
        
        # 5. Restore original alpha mask so the background stays transparent
        if img.mode == "RGBA":
            _, _, _, a = img.split()
            # Downscale/upscale alpha to match the pixelation
            a = a.resize((small_w, small_h), Image.NEAREST).resize(orig_size, Image.NEAREST)
            out.putalpha(a)
            
        return out