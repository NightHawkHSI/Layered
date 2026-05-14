from PIL import Image, ImageFilter, ImageChops, ImageOps
from app.plugins.plugin_api import Plugin, PluginContext, Setting

class NeonGlowPlugin(Plugin):
    name = "Neon Edge Bloom"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        ctx.register_filter(
            "Neon Glow",
            self.apply_neon,
            settings=[
                Setting("glow_color", "color", (0, 255, 150, 255), "Neon Color"),
                Setting("spread", "int", 15, "Glow Spread", 1, 50),
                Setting("intensity", "float", 0.8, "Intensity", 0.1, 2.0, 0.1),
                Setting("outline_only", "bool", False, "Outline Only"),
            ],
            category="Artistic"
        )

    @staticmethod
    def apply_neon(img: Image.Image, glow_color=(0, 255, 150, 255), spread=15, intensity=0.8, outline_only=False) -> Image.Image:
        # 1. Prepare base images
        working_img = img.convert("RGBA")
        
        # 2. Isolate the "edge" or content
        # We use the Alpha channel to find where the drawing is
        alpha = working_img.getchannel("A")
        
        # Create a mask of the edges
        edges = alpha.filter(ImageFilter.FIND_EDGES)
        # Make edges thicker based on spread
        edges = edges.filter(ImageFilter.MaxFilter(3))
        
        # 3. Create the Glow Layer
        # Fill a new image with the user's chosen neon color
        r, g, b, _ = glow_color
        glow_layer = Image.new("RGBA", working_img.size, (r, g, b, 255))
        
        # Apply the edge mask to the color
        glow_layer.putalpha(edges)
        
        # 4. Multi-Pass Blur (Bloom)
        # We blur the edges heavily to create the light "bleeding" effect
        bloom = glow_layer.filter(ImageFilter.GaussianBlur(radius=spread))
        
        # Adjust intensity by manipulating the alpha channel
        if intensity != 1.0:
            bloom_alpha = bloom.getchannel("A").point(lambda p: min(255, int(p * intensity)))
            bloom.putalpha(bloom_alpha)

        # 5. Composite
        # We place the bloom *underneath* the original image to keep the drawing sharp
        # OR we just return the bloom if "outline_only" is checked
        if outline_only:
            return bloom
        
        final = Image.new("RGBA", working_img.size, (0, 0, 0, 0))
        final.alpha_composite(bloom)
        final.alpha_composite(working_img)
        
        return final