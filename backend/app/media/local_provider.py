import io
from uuid import uuid4
from PIL import Image, ImageDraw, ImageFont

from app.media.interface import (
    ImageGenerationProvider,
    ImageGenerationRequest,
    ImageGenerationResult,
    TransientImageGenerationError,
    PermanentImageGenerationError,
)


class LocalTestImageGenerationProvider(ImageGenerationProvider):
    """
    Local test provider for image generation.
    Generates deterministic, visually clean PNG banner images using Pillow.
    Explicitly labeled with is_stub: True and provider: "local_test".
    Never pretends to be real cloud image provider output.
    """

    def __init__(self, simulate_transient_failure: bool = False, simulate_permanent_failure: bool = False):
        self.simulate_transient_failure = simulate_transient_failure
        self.simulate_permanent_failure = simulate_permanent_failure

    def generate_image(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if self.simulate_permanent_failure:
            raise PermanentImageGenerationError("Simulated permanent image generation failure (policy or invalid prompt).")

        if self.simulate_transient_failure:
            raise TransientImageGenerationError("Simulated transient image generation error (503 / timeout).")

        # Create an aesthetically modern banner (dark slate palette matching Content OS)
        w, h = request.width, request.height
        image = Image.new("RGB", (w, h), color=(15, 23, 42))  # slate-900
        draw = ImageDraw.Draw(image)

        # Draw decorative background gradients / geometric grid lines
        for x in range(0, w, 60):
            draw.line([(x, 0), (x, h)], fill=(30, 41, 59), width=1)  # slate-800
        for y in range(0, h, 60):
            draw.line([(0, y), (w, y)], fill=(30, 41, 59), width=1)

        # Draw decorative accent badge border
        accent_color = (99, 102, 241)  # indigo-500
        draw.rectangle([40, 40, w - 40, h - 40], outline=accent_color, width=2)

        # Header tag
        draw.rectangle([60, 60, 260, 96], fill=(30, 27, 75))  # indigo-950
        draw.text((75, 70), "CONTENT OS • MEDIA", fill=(165, 180, 252))  # indigo-300

        # Topic / title text
        display_title = request.title or "Generated Media Asset"
        if len(display_title) > 65:
            display_title = display_title[:62] + "..."

        draw.text((60, 140), display_title, fill=(248, 250, 252))  # slate-50

        # Prompt excerpt
        prompt_snippet = request.prompt
        if len(prompt_snippet) > 140:
            prompt_snippet = prompt_snippet[:137] + "..."
        draw.text((60, 200), f"Prompt: {prompt_snippet}", fill=(148, 163, 184))  # slate-400

        # Version stamp
        draw.text((60, h - 80), f"Version ID: {str(request.content_version_id)}", fill=(100, 116, 139))  # slate-500

        # Provider tag in bottom right
        draw.text((w - 240, h - 80), "PROVIDER: LOCAL_TEST", fill=(251, 191, 36))  # amber-400

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        raw_bytes = buffer.getvalue()

        asset_id = f"local_{uuid4().hex[:12]}"
        alt_text = f"Banner image representing: {display_title}"

        return ImageGenerationResult(
            provider="local_test",
            provider_asset_id=asset_id,
            mime_type="image/png",
            width=w,
            height=h,
            data=raw_bytes,
            alt_text=alt_text,
            metadata={
                "generator": "Pillow/LocalTestImageGenerationProvider",
                "simulated": True,
                "color_palette": "dark_slate_indigo",
            },
            is_stub=True,
        )
