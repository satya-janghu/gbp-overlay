"""Text overlay rendering for GBP images."""
import io
import os
import threading
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageStat
from app.config import FONT_DIR, FONTS

# Per-thread font cache to avoid sharing FreeTypeFont objects across threads.
# Pillow font objects are not documented as thread-safe; concurrent ImageDraw.text()
# calls with the same font could corrupt internal state.
_thread_local = threading.local()


def _get_font(font_file: str, size: int) -> ImageFont.FreeTypeFont:
    """Get per-thread cached font object."""
    cache = getattr(_thread_local, "font_cache", None)
    if cache is None:
        cache = {}
        _thread_local.font_cache = cache

    key = (font_file, size)
    if key not in cache:
        path = os.path.join(FONT_DIR, font_file)
        cache[key] = ImageFont.truetype(path, size)
    return cache[key]

def _analyze_regions(image: Image.Image) -> dict[str, float]:
    """Analyze image regions and score for overlay placement.

    Downsamples to max 800px before analysis to reduce memory ~25×
    (a 4000×3000 image would create ~72MB of float32 arrays without this).

    Uses entropy + gradient magnitude + luminance variance with bottom bias.
    Score = (1 - norm_entropy) * 0.35 + (1 - norm_gradient) * 0.35
          + (1 - norm_variance) * 0.15 + position_bias * 0.15
    """
    # Downsample for analysis only — negligible quality impact on scoring
    analysis_img = image.copy()
    analysis_img.thumbnail((800, 800), Image.LANCZOS)

    gray = analysis_img.convert("L")
    width, height = analysis_img.size
    gray_array = np.array(gray)
    analysis_img.close()

    # Sobel kernels for gradient magnitude
    sobel_x = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    sobel_y = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)

    bar_height = height // 4
    positions = {
        "bottom-center": (0, height - bar_height, width, bar_height),
        "top-center": (0, 0, width, bar_height),
        "top-left": (0, 0, width // 2, bar_height),
        "top-right": (width // 2, 0, width // 2, bar_height),
        "bottom-left": (0, height - bar_height, width // 2, bar_height),
        "bottom-right": (width // 2, height - bar_height, width // 2, bar_height),
    }

    # Position bias: prefer bottom positions
    position_bias = {
        "bottom-center": 1.0,
        "bottom-left": 0.9,
        "bottom-right": 0.9,
        "top-center": 0.0,
        "top-left": 0.1,
        "top-right": 0.1,
    }

    entropy_values = {}
    gradient_values = {}
    variance_values = {}

    for name, (x, y, w, h) in positions.items():
        region = gray_array[y:y + h, x:x + w]

        # Shannon entropy on grayscale histogram
        hist, _ = np.histogram(region, bins=256, range=(0, 256))
        hist = hist / hist.sum()
        hist = hist[hist > 0]
        entropy_values[name] = -np.sum(hist * np.log2(hist))

        # Gradient magnitude via Sobel (simple convolution)
        if region.shape[0] >= 3 and region.shape[1] >= 3:
            from scipy.signal import convolve2d
            gx = convolve2d(region.astype(np.float32), sobel_x, mode='same', boundary='symm')
            gy = convolve2d(region.astype(np.float32), sobel_y, mode='same', boundary='symm')
            gradient_values[name] = np.mean(np.sqrt(gx**2 + gy**2))
        else:
            gradient_values[name] = 0

        # Luminance variance
        variance_values[name] = float(np.var(region))

    # Normalize
    max_ent = max(entropy_values.values()) or 1
    max_grad = max(gradient_values.values()) or 1
    max_var = max(variance_values.values()) or 1

    scores = {}
    for name in positions:
        norm_ent = entropy_values[name] / max_ent
        norm_grad = gradient_values[name] / max_grad
        norm_var = variance_values[name] / max_var
        bias = position_bias[name]
        scores[name] = (
            (1 - norm_ent) * 0.35
            + (1 - norm_grad) * 0.35
            + (1 - norm_var) * 0.15
            + bias * 0.15
        )

    return scores

def _determine_colors(image: Image.Image, position: str) -> dict:
    """Determine text and bar colors based on region luminance."""
    gray = image.convert("L")
    width, height = image.size
    bar_height = height // 4

    if "bottom" in position:
        y = height - bar_height
    else:
        y = 0

    region = gray.crop((0, y, width, y + bar_height))
    avg_luminance = ImageStat.Stat(region).mean[0]

    if avg_luminance < 128:
        text_color = (255, 255, 255, 255)
        bar_color = (0, 0, 0, 140)
    else:
        text_color = (26, 26, 26, 255)
        bar_color = (255, 255, 255, 153)

    bar_alpha = bar_color[3]
    bar_lum = bar_color[0]
    alpha_ratio = bar_alpha / 255
    effective_bg_lum = bar_lum * alpha_ratio + avg_luminance * (1 - alpha_ratio)

    text_lum = text_color[0]
    l1 = max(text_lum, effective_bg_lum) / 255 * 0.7152 + 0.05
    l2 = min(text_lum, effective_bg_lum) / 255 * 0.7152 + 0.05
    contrast = l1 / l2

    while contrast < 4.5 and bar_alpha < 230:
        bar_alpha += 15
        alpha_ratio = bar_alpha / 255
        effective_bg_lum = bar_lum * alpha_ratio + avg_luminance * (1 - alpha_ratio)
        l1 = max(text_lum, effective_bg_lum) / 255 * 0.7152 + 0.05
        l2 = min(text_lum, effective_bg_lum) / 255 * 0.7152 + 0.05
        contrast = l1 / l2

    return {
        "text_color": text_color,
        "bar_color": (*bar_color[:3], bar_alpha),
    }

def _calculate_font_sizes(image_width: int, image_height: int, keyword: str,
                          location: str, font_name: str,
                          text_scale: float = 1.0) -> tuple[int, int]:
    """Calculate font sizes for keyword and location text.

    Keyword: min(image_width, image_height) / 25, clamped [20, 56], scaled.
    Location: 77% of keyword size.
    Shrink if text exceeds 85% of image width.
    """
    font_info = FONTS.get(font_name, FONTS["Montserrat"])

    keyword_size = int(min(image_width, image_height) / 25 * text_scale)
    keyword_size = max(20, min(56, keyword_size))
    location_size = int(keyword_size * 0.77)

    max_text_width = int(image_width * 0.85)

    bold_font = _get_font(font_info["bold"], keyword_size)
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), keyword, font=bold_font)
    kw_width = bbox[2] - bbox[0]

    if kw_width > max_text_width:
        keyword_size = int(keyword_size * max_text_width / kw_width)
        location_size = int(keyword_size * 0.77)

    reg_font = _get_font(font_info["regular"], location_size)
    bbox = draw.textbbox((0, 0), location, font=reg_font)
    loc_width = bbox[2] - bbox[0]

    if loc_width > max_text_width:
        location_size = int(location_size * max_text_width / loc_width)

    return keyword_size, location_size


def _draw_pill_bar_and_text(draw, overlay_img, width, height, position,
                            keyword, location, font_name, colors,
                            keyword_size, location_size):
    """Draw a pill-shaped (rounded rectangle) bar with text centered inside."""
    font_info = FONTS.get(font_name, FONTS["Montserrat"])
    bold_font = _get_font(font_info["bold"], keyword_size)
    reg_font = _get_font(font_info["regular"], location_size)

    # Measure text
    dummy_img = Image.new("RGBA", (1, 1))
    dummy_draw = ImageDraw.Draw(dummy_img)
    kw_bbox = dummy_draw.textbbox((0, 0), keyword, font=bold_font)
    loc_bbox = dummy_draw.textbbox((0, 0), location, font=reg_font)
    dummy_img.close()

    kw_height = kw_bbox[3] - kw_bbox[1]
    loc_height = loc_bbox[3] - loc_bbox[1]
    kw_width = kw_bbox[2] - kw_bbox[0]
    loc_width = loc_bbox[2] - loc_bbox[0]

    line_spacing = int(kw_height * 0.2)
    text_block_height = kw_height + line_spacing + loc_height
    padding_v = int(text_block_height * 0.18)

    # Pill-shaped bar: width based on text content, not full image width
    max_text_width = max(kw_width, loc_width)
    padding_h = int(max_text_width * 0.15)
    bar_w = max_text_width + padding_h * 2
    bar_height = text_block_height + padding_v * 2
    bar_x = (width - bar_w) // 2
    corner_radius = int(bar_height * 0.3)

    if "bottom" in position:
        bar_y = height - bar_height - int(height * 0.03)  # small margin from edge
    else:
        bar_y = int(height * 0.03)

    # Draw rounded rectangle
    draw.rounded_rectangle(
        [(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_height)],
        radius=corner_radius,
        fill=colors["bar_color"]
    )

    # Draw keyword text (centered in bar)
    kw_x = bar_x + (bar_w - kw_width) // 2
    kw_y = bar_y + padding_v
    draw.text((kw_x, kw_y), keyword, font=bold_font, fill=colors["text_color"])

    # Draw location text (centered in bar)
    loc_x = bar_x + (bar_w - loc_width) // 2
    loc_y = kw_y + kw_height + line_spacing
    draw.text((loc_x, loc_y), location, font=reg_font, fill=colors["text_color"])

    return position


def render_overlay_bytes(image_bytes: bytes, keyword: str, location: str,
                         font_name: str,
                         position: str | None = None,
                         text_scale: float = 1.0) -> bytes:
    """Render text overlay on image from bytes, returning JPEG bytes."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = None
    result = None
    try:
        width, height = img.size

        if position is None:
            scores = _analyze_regions(img)
            position = max(scores, key=scores.get)

        colors = _determine_colors(img, position)
        keyword_size, location_size = _calculate_font_sizes(
            width, height, keyword, location, font_name, text_scale
        )

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        _draw_pill_bar_and_text(
            draw, overlay, width, height, position,
            keyword, location, font_name, colors,
            keyword_size, location_size
        )

        result = Image.alpha_composite(img, overlay).convert("RGB")

        buf = io.BytesIO()
        result.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    finally:
        if result is not None:
            result.close()
        if overlay is not None:
            overlay.close()
        img.close()


def render_overlay(image_path: str, keyword: str, location: str,
                   font_name: str, output_path: str,
                   position: str | None = None,
                   text_scale: float = 1.0) -> str:
    """Render text overlay on image.

    Args:
        image_path: Path to source image
        keyword: Keyword text for overlay
        location: Location text for overlay
        font_name: Font name from FONTS dict
        output_path: Path to save processed image
        position: Override position (None = auto-detect best)
        text_scale: Scale factor for text size (1.0 = default)

    Returns: output_path
    """
    with Image.open(image_path) as _base:
        img = _base.convert("RGBA")
    overlay = None
    result = None
    try:
        width, height = img.size

        if position is None:
            scores = _analyze_regions(img)
            position = max(scores, key=scores.get)

        colors = _determine_colors(img, position)
        keyword_size, location_size = _calculate_font_sizes(
            width, height, keyword, location, font_name, text_scale
        )

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        _draw_pill_bar_and_text(
            draw, overlay, width, height, position,
            keyword, location, font_name, colors,
            keyword_size, location_size
        )

        result = Image.alpha_composite(img, overlay).convert("RGB")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        result.save(output_path, format="JPEG", quality=90)

        return output_path
    finally:
        if result is not None:
            result.close()
        if overlay is not None:
            overlay.close()
        img.close()
