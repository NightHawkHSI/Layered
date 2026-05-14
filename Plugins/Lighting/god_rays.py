from PIL import Image, ImageChops, ImageFilter
from app.plugins.plugin_api import Plugin, PluginContext, Setting

class GodRaysPlugin(Plugin):
    name = "Radiant God Rays"
    version = "1.0.0"

    def register(self, ctx: PluginContext) -> None:
        # FIX: Save the context so we can use it in 'ping' or other methods
        self.ctx = ctx
        
        ctx.register_filter(
            "God Rays",
            self.apply_rays,
            settings=[
                Setting("decay", "float", 0.9, "Streak Length", 0.1, 1.0, 0.05),
                Setting("density", "float", 0.5, "Density", 0.1, 1.0, 0.1),
                Setting("weight", "float", 0.5, "Brightness", 0.1, 1.0, 0.1),
                Setting("ray_color", "color", (255, 220, 150, 255), "Ray Color"),
            ],
            category="Light"
        )
        
        # This will now work without the 'AttributeError'
        ctx.register_action("Check Plugin Status", self.ping)

    def ping(self):
        # Now self.ctx is defined!
        self.ctx.status("God Rays System: Online and Ready ☀️")

    @staticmethod
    def apply_rays(img: Image.Image, decay=0.9, density=0.5, weight=0.5, ray_color=(255, 220, 150, 255)) -> Image.Image:
        # 1. Setup
        working_img = img.convert("RGBA")
        w, h = working_img.size
        
        # 2. Create the "Light Source" mask from the image alpha
        # We want the rays to come from the solid parts of the drawing
        alpha = working_img.getchannel("A")
        
        # Create a solid color image for the rays
        r, g, b, _ = ray_color
        rays = Image.new("RGBA", (w, h), (r, g, b, 255))
        rays.putalpha(alpha)
        
        # 3. Generate the "Radial Blur" (God Ray effect)
        # We simulate this by repeatedly scaling and overlaying the image
        # This creates streaks that point toward the center
        step_image = rays.copy()
        
        # We do 12 passes of scaling to create the streaks
        for _ in range(12):
            # Slightly scale the image up
            scale_factor = 1.0 + (0.05 * density)
            new_w = int(w * scale_factor)
            new_h = int(h * scale_factor)
            
            # Resize and crop back to original size (centered)
            temp = step_image.resize((new_w, new_h), Image.BILINEAR)
            left = (new_w - w) // 2
            top = (new_h - h) // 2
            step_image = temp.crop((left, top, left + w, top + h))
            
            # Fade the step
            alpha_step = step_image.getchannel("A").point(lambda p: int(p * decay))
            step_image.putalpha(alpha_step)
            
            # Composite the new step onto the main rays image
            rays.alpha_composite(step_image)

        # 4. Final Composite
        # Adjust brightness of the rays
        if weight != 1.0:
            final_alpha = rays.getchannel("A").point(lambda p: int(p * weight))
            rays.putalpha(final_alpha)

        # Merge original image on top of rays
        final_output = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        final_output.alpha_composite(rays)
        final_output.alpha_composite(working_img)
        
        return final_output