"""pdf extractor — pymupdf based, pure-Python."""
from __future__ import annotations

import contextlib
import io
import logging
import os
import statistics
import sys
from pathlib import Path
from typing import Any

import pymupdf  # type: ignore[import-not-found]
from PIL import Image as PILImage

from any2md.extractors.base import ExtractResult

log = logging.getLogger(__name__)

# pymupdf's find_tables() prints "Consider using the pymupdf_layout package..."
# directly to stdout from C code, bypassing set_messages and Python's
# sys.stdout. Route messages to stderr for normal calls AND wrap find_tables
# with an fd-level stdout redirect so it doesn't leak into the markdown output.
pymupdf.set_messages(stream=sys.stderr)
pymupdf.TOOLS.mupdf_display_errors(False)


@contextlib.contextmanager
def _silence_stdout():
    """fd-level stdout suppression — needed for C-printf calls inside pymupdf."""
    sys.stdout.flush()
    saved_fd = os.dup(1)
    devnull_fd = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull_fd, 1)
        os.close(devnull_fd)
        yield
    finally:
        sys.stdout.flush()
        os.dup2(saved_fd, 1)
        os.close(saved_fd)

_PT_TO_PX = 4.0 / 3.0                                # 96 DPI / 72 DPI


def _pt_to_px(v: float) -> float:
    return round(float(v) * _PT_TO_PX, 1)


class PdfExtractor:
    format = "pdf"

    def extract(self, source: Path) -> ExtractResult:
        warnings: list[str] = []
        images: dict[str, bytes] = {}
        doc = pymupdf.open(source)
        if doc.needs_pass:
            doc.close()
            raise ValueError(f"PDF is encrypted: {source}")

        page_count = doc.page_count
        pages_ir: list[dict[str, Any]] = []
        text_density_samples: list[float] = []

        for page_idx, page in enumerate(doc, start=1):
            extracted_text = page.get_text("text") or ""
            # Density: chars per square pt
            page_area = max(1.0, page.rect.width * page.rect.height)
            text_density_samples.append(len(extracted_text) / page_area * 1000)

            # Render full page to PNG at 150 dpi
            pix = page.get_pixmap(dpi=150)
            page_png = pix.tobytes("png")
            page_img_id = f"page_{page_idx}"
            page_img_path = f"raw_images/{page_img_id}.png"
            images[page_img_path] = self._maybe_resize_png(page_png)
            page_img_w, page_img_h = self._dims(images[page_img_path])

            # Text blocks with bbox — preserve line structure within block
            text_blocks: list[dict[str, Any]] = []
            font_sizes: list[float] = []
            try:
                d = page.get_text("dict")
                for block in d.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    line_texts: list[str] = []
                    block_sizes: list[float] = []
                    for line in block.get("lines", []):
                        line_text = "".join(
                            span.get("text", "") for span in line.get("spans", [])
                        )
                        if line_text:
                            line_texts.append(line_text)
                        for span in line.get("spans", []):
                            block_sizes.append(span.get("size", 0))
                    block_text = "\n".join(line_texts).strip()
                    if not block_text:
                        continue
                    x0, y0, x1, y1 = block.get("bbox", (0, 0, 0, 0))
                    text_blocks.append({
                        "bbox": {
                            "left": _pt_to_px(x0), "top": _pt_to_px(y0),
                            "width": _pt_to_px(x1 - x0), "height": _pt_to_px(y1 - y0),
                            "unit": "px",
                        },
                        "text": block_text,
                        "is_likely_heading": False,
                        "_avg_size": (sum(block_sizes) / len(block_sizes)) if block_sizes else 0.0,
                    })
                    if block_sizes:
                        font_sizes.extend(block_sizes)
            except Exception as e:
                warnings.append(f"Page {page_idx}: text extract failed: {e}")

            # Mark heading: avg font size > median
            if font_sizes:
                median = statistics.median(font_sizes)
                for tb in text_blocks:
                    if tb["_avg_size"] > median * 1.15:
                        tb["is_likely_heading"] = True
                    del tb["_avg_size"]

            # Sort by reading order (top, left)
            text_blocks.sort(key=lambda b: (b["bbox"]["top"], b["bbox"]["left"]))
            for order, tb in enumerate(text_blocks):
                tb["order"] = order

            # Embedded images
            images_on_page: list[dict[str, Any]] = []
            for img_idx, img_info in enumerate(page.get_images(full=True), start=1):
                xref = img_info[0]
                try:
                    pix_img = pymupdf.Pixmap(doc, xref)
                    if pix_img.alpha or pix_img.colorspace.n > 4:
                        pix_img = pymupdf.Pixmap(pymupdf.csRGB, pix_img)
                    img_png = pix_img.tobytes("png")
                except Exception as e:
                    warnings.append(f"Page {page_idx}: image #{img_idx} extract failed: {e}")
                    continue
                norm = self._maybe_resize_png(img_png)
                w, h = self._dims(norm)
                img_id = f"img_p{page_idx}_{img_idx}"
                img_path = f"raw_images/{img_id}.png"
                images[img_path] = norm

                # Resolve placement bbox(es) — an image xref can appear multiple
                # times on a page; emit one IR entry per occurrence
                rects: list[Any] = []
                try:
                    rects = list(page.get_image_rects(xref)) or []
                except Exception as e:
                    warnings.append(
                        f"Page {page_idx}: image #{img_idx} bbox resolution failed: {e}"
                    )
                if not rects:
                    rects = [None]

                for occ_idx, r in enumerate(rects, start=1):
                    occ_id = img_id if len(rects) == 1 else f"{img_id}_{occ_idx}"
                    entry: dict[str, Any] = {
                        "id": occ_id,
                        "relative_path": img_path,
                        "width_px": w,
                        "height_px": h,
                        "container": {
                            "kind": "pdf_page",
                            "index": page_idx,
                            "label": f"Page {page_idx}",
                        },
                        "neighbors": {
                            "before_text": "",
                            "after_text": "",
                            "before_kind": None,
                            "after_kind": None,
                        },
                    }
                    if r is not None:
                        try:
                            x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1
                        except AttributeError:
                            x0, y0, x1, y1 = r[0], r[1], r[2], r[3]
                        entry["bbox"] = {
                            "left": _pt_to_px(x0), "top": _pt_to_px(y0),
                            "width": _pt_to_px(x1 - x0),
                            "height": _pt_to_px(y1 - y0),
                            "unit": "px",
                        }
                    images_on_page.append(entry)

            # Tables
            tables_ir: list[dict[str, Any]] = []
            try:
                with _silence_stdout():
                    tabs = list(page.find_tables())
                for t in tabs:
                    try:
                        rows = t.extract()
                    except Exception:
                        rows = []
                    if not rows:
                        continue
                    x0, y0, x1, y1 = t.bbox
                    tables_ir.append({
                        "bbox": {
                            "left": _pt_to_px(x0), "top": _pt_to_px(y0),
                            "width": _pt_to_px(x1 - x0), "height": _pt_to_px(y1 - y0),
                            "unit": "px",
                        },
                        "rows": rows,
                    })
            except Exception:
                pass

            # Links / URI annotations
            links_ir: list[dict[str, Any]] = []
            try:
                for link in page.get_links():
                    kind_int = link.get("kind", 0)
                    kind_map = {
                        pymupdf.LINK_URI: "uri",
                        pymupdf.LINK_GOTO: "goto",
                        pymupdf.LINK_LAUNCH: "launch",
                        pymupdf.LINK_NAMED: "named",
                    }
                    kind = kind_map.get(kind_int, "other")
                    rect = link.get("from")
                    if rect is None:
                        continue
                    try:
                        x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
                    except AttributeError:
                        x0, y0, x1, y1 = rect[0], rect[1], rect[2], rect[3]
                    bbox = {
                        "left": _pt_to_px(x0), "top": _pt_to_px(y0),
                        "width": _pt_to_px(x1 - x0), "height": _pt_to_px(y1 - y0),
                        "unit": "px",
                    }
                    entry: dict[str, Any] = {"bbox": bbox, "kind": kind}
                    if kind == "uri" and link.get("uri"):
                        entry["uri"] = link["uri"]
                    elif kind == "goto" and "page" in link:
                        entry["target_page"] = int(link["page"]) + 1
                    elif kind == "launch" and link.get("file"):
                        entry["uri"] = link["file"]
                    # Capture link text (text overlapping link rect)
                    try:
                        link_text = page.get_textbox(pymupdf.Rect(x0, y0, x1, y1)).strip()
                        if link_text:
                            entry["text"] = link_text
                    except Exception:
                        pass
                    links_ir.append(entry)
            except Exception as e:
                warnings.append(f"Page {page_idx}: link extract failed: {e}")

            pages_ir.append({
                "index": page_idx,
                "page_image": {
                    "id": page_img_id,
                    "relative_path": page_img_path,
                    "width_px": page_img_w,
                    "height_px": page_img_h,
                    "container": {
                        "kind": "pdf_page",
                        "index": page_idx,
                        "label": f"Page {page_idx}",
                    },
                    "neighbors": {
                        "before_text": "",
                        "after_text": "",
                        "before_kind": None,
                        "after_kind": None,
                    },
                },
                "extracted_text": extracted_text,
                "text_blocks": text_blocks,
                "images_on_page": images_on_page,
                "tables": tables_ir,
                "links": links_ir,
            })

        is_scanned = bool(text_density_samples) and (
            statistics.mean(text_density_samples) < 0.5
        )

        # Document metadata
        meta: dict[str, Any] = {}
        try:
            raw_meta = doc.metadata or {}
            for key in ("title", "author", "subject", "keywords", "creator", "producer",
                        "creationDate", "modDate"):
                v = raw_meta.get(key)
                if v:
                    meta[key] = v
        except Exception as e:
            warnings.append(f"Metadata read failed: {e}")

        # Outline (TOC / bookmarks)
        outline_ir: list[dict[str, Any]] = []
        try:
            for entry in doc.get_toc(simple=True) or []:
                # entry = [level, title, page]
                lvl, title, pg = entry[0], entry[1], entry[2]
                outline_ir.append({
                    "level": int(lvl),
                    "title": str(title),
                    "page": int(pg) if pg else -1,
                })
        except Exception as e:
            warnings.append(f"Outline read failed: {e}")

        doc.close()
        ir: dict[str, Any] = {
            "format": "pdf",
            "source": str(source),
            "page_count": page_count,
            "is_scanned": is_scanned,
            "pages": pages_ir,
        }
        if meta:
            ir["metadata"] = meta
        if outline_ir:
            ir["outline"] = outline_ir
        return ExtractResult(ir=ir, images=images, warnings=warnings)

    # --------- helpers ---------

    def _maybe_resize_png(self, blob: bytes) -> bytes:
        try:
            with PILImage.open(io.BytesIO(blob)) as im:
                if im.width <= 2048 and im.height <= 2048:
                    return blob
                im.thumbnail((2048, 2048))
                out = io.BytesIO()
                im.save(out, format="PNG")
                return out.getvalue()
        except Exception:
            return blob

    def _dims(self, blob: bytes) -> tuple[int, int]:
        try:
            with PILImage.open(io.BytesIO(blob)) as im:
                return im.size
        except Exception:
            return (0, 0)
