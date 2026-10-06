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


BOLD_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
REGULAR_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(path: str, size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _render_card(title: str, subtitle: str, w: int, h: int) -> Image.Image:
    """
    A post card: gradient background, the headline set large, a topic line and a brand footer.
    Readable on a phone, no debug text.
    """
    image = Image.new("RGB", (w, h))
    top, bottom = (76, 29, 149), (14, 116, 144)  # violet to teal, dark enough for white text
    px = image.load()
    for y in range(h):
        t = y / max(1, h - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    draw = ImageDraw.Draw(image, "RGBA")

    # Headline: shrink until it fits in the card.
    margin = 80
    max_width = w - 2 * margin
    headline_size = 84
    while True:
        font = _font(BOLD_FONT, headline_size)
        lines = _wrap(draw, title, font, max_width)
        line_height = int(headline_size * 1.18)
        if len(lines) * line_height <= h * 0.50 or headline_size <= 40:
            break
        headline_size -= 4
    y = margin + 40
    for line in lines[:6]:
        draw.text((margin, y), line, font=font, fill=(255, 255, 255, 255))
        y += line_height

    if subtitle:
        sub_font = _font(REGULAR_FONT, 34)
        sub_lines = _wrap(draw, subtitle, sub_font, max_width)
        draw.text((margin, y + 18), sub_lines[0] if sub_lines else subtitle, font=sub_font, fill=(255, 255, 255, 215))

    # Brand footer: the three bars of the logo, the name, and a thin rule.
    footer_y = h - 110
    draw.line([(margin, footer_y), (w - margin, footer_y)], fill=(255, 255, 255, 60), width=2)
    bx = margin
    for height, alpha in ((26, 140), (40, 200), (54, 255)):
        draw.rounded_rectangle([bx, footer_y + 40 + (54 - height), bx + 14, footer_y + 40 + 54],
                               radius=4, fill=(255, 255, 255, alpha))
        bx += 22
    draw.text((bx + 16, footer_y + 40), "Content OS", font=_font(BOLD_FONT, 30), fill=(255, 255, 255, 255))
    return image.convert("RGB")


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

        w, h = request.width, request.height
        title = (request.title or request.topic or "Content OS").strip()
        image = _render_card(title, (request.topic or "").strip(), w, h)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        raw_bytes = buffer.getvalue()

        asset_id = f"local_{uuid4().hex[:12]}"
        alt_text = f"Post image: {title}"

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
