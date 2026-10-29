"""Image processing: validation, hashing, deduplication, resizing."""
import io
from PIL import Image
import imagehash

# Limit decompression to 50MP to prevent memory bombs
Image.MAX_IMAGE_PIXELS = 50_000_000

def validate_image(file_bytes: bytes) -> tuple[bool, str, int, int]:
    """Validate image format and minimum width.
    Returns (is_valid, error_message, width, height).
    """
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img.verify()  # verify it's not corrupted
        img = Image.open(io.BytesIO(file_bytes))  # reopen after verify
        try:
            width, height = img.size
            if img.format not in ("JPEG", "PNG", "WEBP"):
                return False, f"Unsupported format: {img.format}", 0, 0
            if width < 720:
                return False, f"Image too narrow: {width}px (minimum 720px)", width, height
            return True, "", width, height
        finally:
            img.close()  # Explicit close
    except (OSError, SyntaxError, Image.DecompressionBombError) as e:
        return False, f"Invalid image: {str(e)}", 0, 0

def compute_hash(image_bytes: bytes) -> str:
    """Compute perceptual hash (average hash) for deduplication."""
    img = Image.open(io.BytesIO(image_bytes))
    try:
        return str(imagehash.average_hash(img))
    finally:
        img.close()  # Explicit close

def find_duplicates(image_hashes: dict[int, str]) -> set[int]:
    """Find duplicate images based on perceptual hash similarity.
    Args: dict mapping image_id to hash string
    Returns: set of image_ids that are duplicates (keep the first seen)
    Threshold: hamming distance <= 6 out of 64 bits = ~90% similar
    """
    duplicates = set()
    items = list(image_hashes.items())
    for i in range(len(items)):
        if items[i][0] in duplicates:
            continue
        hash_i = imagehash.hex_to_hash(items[i][1])
        for j in range(i + 1, len(items)):
            if items[j][0] in duplicates:
                continue
            hash_j = imagehash.hex_to_hash(items[j][1])
            if hash_i - hash_j <= 6:
                duplicates.add(items[j][0])
    return duplicates

def resize_for_api(image_bytes: bytes, max_size: int = 768) -> bytes:
    """Resize image so longest side is max_size px. Returns JPEG bytes."""
    img = Image.open(io.BytesIO(image_bytes))
    try:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        if max(img.size) > max_size:
            img.thumbnail((max_size, max_size), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()
    finally:
        img.close()  # Explicit close

def convert_to_jpeg(image_bytes: bytes, quality: int = 90) -> bytes:
    """Convert image to JPEG format."""
    img = Image.open(io.BytesIO(image_bytes))
    try:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return buf.getvalue()
    finally:
        img.close()  # Explicit close
