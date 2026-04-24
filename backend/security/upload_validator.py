"""
Upload validation helpers — magic-bytes verification, size caps, MIME/ext sanitization.

Why:
  - Declared content-type (multipart Content-Type) is attacker-controlled and
    cannot be trusted. We must verify file *contents* via Pillow.
  - SVG is rejected explicitly: it is a script-execution surface (onload, <script>,
    foreignObject) that browsers happily render when served as image/svg+xml or
    embedded as a `data:image/svg+xml` URI inside HTML / iframe / innerHTML.
  - Returns sanitized (content_type, ext) derived from the *real* image format,
    so callers never persist attacker-controlled values.
"""

from __future__ import annotations

import io
from pathlib import Path

from fastapi import HTTPException

try:
    from PIL import Image, UnidentifiedImageError
except ImportError:
    Image = None  # type: ignore
    UnidentifiedImageError = Exception  # type: ignore


MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB
MAX_IMAGE_DIMENSION = 8000  # pixels per side
MAX_IMAGE_PIXELS = 64_000_000  # decompression-bomb guard (~8000x8000)
MAX_ANIMATION_FRAMES = 100  # GIF/WEBP frame-count cap (per-render DoS guard)

# Pillow format -> canonical (content_type, extension)
_FORMAT_MAP: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
    "WEBP": ("image/webp", ".webp"),
    "GIF": ("image/gif", ".gif"),
}


def validate_image_bytes(
    content: bytes,
    *,
    max_bytes: int = MAX_IMAGE_BYTES,
    field_label: str = "Dosya",
) -> tuple[str, str]:
    """
    Verify `content` is a real image of an allowed format. Raises 400 with a
    Turkish, user-facing message on any failure. Returns sanitized
    (content_type, ext) derived from actual decoded format.

    Allowed formats: JPEG, PNG, WEBP, GIF. SVG and all other formats rejected.
    """
    if not content:
        raise HTTPException(status_code=400, detail=f"{field_label} bos")

    if len(content) > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HTTPException(
            status_code=413,
            detail=f"{field_label} cok buyuk (en fazla {mb} MB).",
        )

    if Image is None:
        # Pillow missing — fail closed rather than blindly accept.
        raise HTTPException(
            status_code=500,
            detail="Sunucu gorsel dogrulama hazir degil. Yoneticiye bildirin.",
        )

    # Per-call defense: re-assert MAX_IMAGE_PIXELS in case another module mutated
    # this global Pillow setting (defensive against shared-state surprises).
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

    try:
        with Image.open(io.BytesIO(content)) as img:
            fmt = (img.format or "").upper()
            width, height = img.size
            n_frames = int(getattr(img, "n_frames", 1) or 1)
            # verify() consumes the file pointer; reopen for size check above first.
        # Second pass: fully decode to catch malformed images that pass open().
        with Image.open(io.BytesIO(content)) as img2:
            img2.verify()
    except UnidentifiedImageError:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} gecerli bir gorsel degil.",
        )
    except Exception:
        # Pillow raises various exceptions for malformed images / decompression bombs.
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} bozuk veya desteklenmiyor.",
        )

    if fmt not in _FORMAT_MAP:
        raise HTTPException(
            status_code=400,
            detail=f"{field_label} bicimi desteklenmiyor (yalnizca JPG, PNG, WEBP, GIF).",
        )

    if width > MAX_IMAGE_DIMENSION or height > MAX_IMAGE_DIMENSION:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_label} cozunurlugu cok yuksek "
                f"(en fazla {MAX_IMAGE_DIMENSION}x{MAX_IMAGE_DIMENSION} piksel)."
            ),
        )

    # Animation frame-count cap (GIF/WEBP). Defends downstream renderers from
    # many-frame DoS where each frame is small but total render cost is large.
    if n_frames > MAX_ANIMATION_FRAMES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{field_label} cok fazla kareye sahip "
                f"(en fazla {MAX_ANIMATION_FRAMES} kare)."
            ),
        )

    return _FORMAT_MAP[fmt]


def safe_filename_ext(filename: str | None, sanitized_ext: str) -> str:
    """Return a non-traversal extension. Always prefers the sanitized ext from
    magic-bytes detection; never trusts the user-supplied filename."""
    return sanitized_ext  # canonical ext from real format
