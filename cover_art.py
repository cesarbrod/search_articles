"""
Cover art helpers for ebook export (EPUB / DOCX / PDF).

The user uploads a cover image; the whole image is used as the cover with
nothing overlaid on it.

Ideal cover: portrait JPEG or PNG, 1600 x 2560 px (5:8 ratio — the Kindle /
e-reader recommendation). Anything reasonably close works: the builders fit
the entire image onto the page without cropping.
"""

from io import BytesIO
from typing import Optional

from PIL import Image

# Ideal cover size in pixels (width x height), shown in the UI hint.
IDEAL_COVER_WIDTH = 1600
IDEAL_COVER_HEIGHT = 2560

_MIME_TO_EXT = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

_EXT_TO_MIME = {v: k for k, v in _MIME_TO_EXT.items()}


def ideal_size_text() -> str:
    return (f"{IDEAL_COVER_WIDTH}×{IDEAL_COVER_HEIGHT} px portrait "
            f"JPG/PNG — used whole as the cover, nothing overlaid")


def prepare_cover(data: bytes, filename: str = "") -> tuple[bytes, str, str]:
    """
    Validate uploaded cover bytes with Pillow.

    Returns (image_bytes, ext, mime). The image is re-encoded only when
    Pillow cannot keep the original format (e.g. BMP/TIFF → PNG); JPEG and
    PNG pass through untouched. Raises ValueError on invalid image data.
    """
    if not data:
        raise ValueError("Empty cover file.")
    try:
        img = Image.open(BytesIO(data))
        img.verify()
        img = Image.open(BytesIO(data))  # verify() closes; reopen
        fmt = (img.format or "").upper()
    except Exception as e:
        raise ValueError(f"Not a readable image: {e}")

    if fmt in ("JPEG", "JPG"):
        return data, "jpg", "image/jpeg"
    if fmt == "PNG":
        return data, "png", "image/png"

    # Anything else viewable (GIF/WEBP/BMP/…) → normalise to PNG.
    try:
        buf = BytesIO()
        img.convert("RGB").save(buf, format="PNG")
        return buf.getvalue(), "png", "image/png"
    except Exception as e:
        raise ValueError(f"Cannot use this image: {e}")


def guess_cover_from_filename(filename: str) -> Optional[str]:
    """Return ext hint from an upload filename, or None."""
    lower = (filename or "").lower()
    for ext in ("jpg", "jpeg", "png", "gif", "webp"):
        if lower.endswith("." + ext):
            return "jpg" if ext == "jpeg" else ext
    return None
