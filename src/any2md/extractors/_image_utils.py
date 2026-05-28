"""Shared image normalization for extractors.

All extractors must funnel image bytes through `normalize_to_png` before
storing them in `ExtractResult.images`. Downstream (`captions.py`) sends
`data:image/png;base64,...` to the vision LLM, so the bytes MUST actually
be PNG.

Behavior:
  - Raster (PNG / JPEG / GIF / BMP / WEBP / TIFF): PIL re-encode to PNG.
  - SVG: try optional `cairosvg` to rasterize. If unavailable / fails,
    return the raw SVG bytes — `captions.py` detects this via `is_svg`
    and falls back to alt_text rather than wasting vision-API retries.
  - Unknown / corrupt: return blob unchanged (same alt_text fallback).
"""
from __future__ import annotations

import io

from PIL import Image as PILImage


def is_svg(blob: bytes) -> bool:
    if not blob:
        return False
    head = blob.lstrip()[:512]
    if head.startswith(b"<svg"):
        return True
    return head.startswith(b"<?xml") and b"<svg" in head


def normalize_to_png(blob: bytes, *, max_dim: int = 2048) -> bytes:
    if is_svg(blob):
        try:
            import cairosvg  # type: ignore

            return cairosvg.svg2png(bytestring=blob, output_width=max_dim)
        except Exception:
            return blob

    try:
        with PILImage.open(io.BytesIO(blob)) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            if im.width > max_dim or im.height > max_dim:
                im.thumbnail((max_dim, max_dim))
            out = io.BytesIO()
            im.save(out, format="PNG")
            return out.getvalue()
    except Exception:
        return blob


def image_dimensions(blob: bytes) -> tuple[int, int]:
    try:
        with PILImage.open(io.BytesIO(blob)) as im:
            return im.size
    except Exception:
        return (0, 0)
