"""Collect image references from cleaned IR across formats.

Each entry: {id, relative_path, alt_text?, container_kind, container_index, label?, context_text?}
- container_kind: pptx_slide | xlsx_sheet | pdf_page | html_block
- container_index: 1-based for slide/page/sheet; 0-based for html block
- context_text: best-effort surrounding text for caption prompting
"""
from __future__ import annotations

from typing import Any, TypedDict


class ImageRef(TypedDict, total=False):
    id: str
    relative_path: str
    alt_text: str
    container_kind: str
    container_index: int
    label: str
    context_text: str


def collect_image_refs(ir: dict[str, Any]) -> list[ImageRef]:
    fmt = ir.get("format")
    if fmt == "pptx":
        refs = _collect_pptx(ir)
    elif fmt == "xlsx":
        refs = _collect_xlsx(ir)
    elif fmt == "pdf":
        refs = _collect_pdf(ir)
    elif fmt == "html":
        refs = _collect_html(ir)
    elif fmt == "docx":
        refs = _collect_blocks(ir, "docx_section")
    elif fmt == "markdown":
        refs = _collect_blocks(ir, "md_section")
    else:
        return []
    return _dedup_by_id(refs)


def _dedup_by_id(refs: list[ImageRef]) -> list[ImageRef]:
    """Keep the first occurrence per image_id.

    A single image xref can appear multiple times in the IR — e.g. a PDF
    embeds the same logo on N pages, or a pptx reuses a master-slide
    picture. Captioning is per-image-bytes, not per-placement, so feeding
    duplicates burns vision-API calls and inflates the metric. The first
    occurrence wins so the context_text comes from where the image is
    first encountered in reading order.
    """
    seen: set[str] = set()
    out: list[ImageRef] = []
    for r in refs:
        rid = r.get("id") or ""
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append(r)
    return out


def _img_entry(img: dict[str, Any], container_kind: str, container_index: int,
               *, label: str | None = None, context_text: str = "") -> ImageRef:
    rel = img.get("relative_path") or img.get("path") or ""
    entry: ImageRef = {
        "id": img.get("id") or _id_from_path(rel),
        "relative_path": rel,
        "container_kind": container_kind,
        "container_index": container_index,
    }
    alt = img.get("alt_text")
    if isinstance(alt, str) and alt.strip():
        entry["alt_text"] = alt
    if label:
        entry["label"] = label
    if context_text:
        entry["context_text"] = context_text
    return entry


def _id_from_path(rel: str) -> str:
    return rel.rsplit("/", 1)[-1].rsplit(".", 1)[0] if rel else ""


# ---------- per-format ----------

def _collect_pptx(ir: dict[str, Any]) -> list[ImageRef]:
    out: list[ImageRef] = []
    for slide in ir.get("slides", []):
        idx = slide.get("index", 0)
        ctx_text = _slide_text(slide)
        for shape in slide.get("shapes", []):
            if shape.get("type") == "image":
                img = shape.get("image", {})
                out.append(_img_entry(
                    img, "pptx_slide", idx,
                    label=shape.get("name"),
                    context_text=ctx_text,
                ))
            elif shape.get("type") == "group":
                for sub in shape.get("shapes", []):
                    if sub.get("type") == "image":
                        out.append(_img_entry(
                            sub.get("image", {}), "pptx_slide", idx,
                            label=sub.get("name"),
                            context_text=ctx_text,
                        ))
    return out


def _slide_text(slide: dict[str, Any]) -> str:
    chunks: list[str] = []
    if isinstance(slide.get("title"), str):
        chunks.append(slide["title"])
    for shape in slide.get("shapes", []):
        if shape.get("type") == "text":
            for p in shape.get("paragraphs", []):
                for r in p.get("runs", []):
                    txt = r.get("text", "")
                    if txt:
                        chunks.append(txt)
    return " ".join(chunks).strip()[:500]


def _collect_xlsx(ir: dict[str, Any]) -> list[ImageRef]:
    out: list[ImageRef] = []
    for sheet in ir.get("sheets", []):
        name = sheet.get("name", "")
        idx = sheet.get("index", 0)
        for anchor in sheet.get("images", []):
            out.append(_img_entry(
                anchor.get("image", {}), "xlsx_sheet", idx,
                label=name,
            ))
    return out


def _collect_pdf(ir: dict[str, Any]) -> list[ImageRef]:
    out: list[ImageRef] = []
    for page in ir.get("pages", []):
        idx = page.get("number", page.get("index", 0))
        ctx_text = " ".join(
            tb.get("text", "")
            for tb in page.get("text_blocks", [])
        )[:500]
        for img in page.get("images_on_page", []):
            out.append(_img_entry(img, "pdf_page", idx, context_text=ctx_text))
    return out


def _collect_html(ir: dict[str, Any]) -> list[ImageRef]:
    out: list[ImageRef] = []
    blocks = ir.get("blocks", [])
    for i, blk in enumerate(blocks):
        kind = blk.get("type")
        if kind == "image":
            out.append(_img_entry(blk.get("image") or blk, "html_block", i))
        elif kind == "figure":
            img = blk.get("image") or blk
            label = blk.get("caption", "")
            out.append(_img_entry(img, "html_block", i, label=label))
    return out


def _collect_blocks(ir: dict[str, Any], container_kind: str) -> list[ImageRef]:
    """Collect image refs from a block-list IR (docx / markdown).

    Recurses into textbox / blockquote nests and pulls context_text from each
    image's wired `neighbors`.
    """
    out: list[ImageRef] = []
    _walk_block_images(ir.get("blocks", []), out, container_kind)
    return out


def _walk_block_images(
    blocks: list[dict[str, Any]], out: list[ImageRef], container_kind: str
) -> None:
    for blk in blocks:
        kind = blk.get("type")
        if kind in ("image", "figure"):
            img = blk.get("image") or blk
            nb = img.get("neighbors") or {}
            ctx = f"{nb.get('before_text', '')} {nb.get('after_text', '')}".strip()
            idx = (img.get("container") or {}).get("index", 1)
            out.append(_img_entry(img, container_kind, idx, context_text=ctx[:500]))
        elif kind in ("textbox", "blockquote"):
            _walk_block_images(blk.get("blocks", []), out, container_kind)
