"""Split large IRs into chunks the agent can process within context limits.

Chunks by natural unit:
- pptx: slide
- pdf:  page
- xlsx: sheet
- html / markdown / docx: top-level block

Greedy packing: keep adding units until token or image cap would be exceeded,
then start a new chunk. A single unit larger than the caps is emitted alone
with `truncated=True` — no in-unit splitting in this phase.

Token counting uses a simple `len(s) // 3` character heuristic — no
tokenizer download, no extra dependency, works on restricted-egress
runtimes (Databricks serverless, locked-down enterprise VPCs).

Calibration: on the project's mixed Vietnamese + English JSON-serialized
IR, measured ratios are 2.3–3.4 chars/token (English HTML highest, VN
xlsx lowest). Dividing by 3 sits in the middle of that band — under-counts
VN content by ~10-20% and over-counts English by ~10-13%. `max_chunk_tokens`
already carries a safety margin, so this is fine for budget gating. Do
not use this function for exact billing.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Literal, TypedDict

log = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS = 20_000
DEFAULT_MAX_IMAGES = 80


def count_tokens(s: str) -> int:
    """Estimate token count via `len(s) // 3` — a conservative heuristic
    used purely for chunk-budget gating.
    """
    return max(1, len(s) // 3)


class IRChunk(TypedDict):
    chunk_index: int                                  # 0-based
    total_chunks: int
    unit_kind: Literal["slide", "page", "sheet", "block"]
    unit_start: int                                   # inclusive; native index for slide/page/sheet, array pos for block
    unit_end: int                                     # inclusive
    token_count: int                                  # heuristic (len // 4) of chunk's ir (JSON serialized)
    image_count: int
    truncated: bool                                   # True when a single oversize unit was emitted alone
    ir: dict[str, Any]                                # valid IR (same `format`, subset of units)


def chunk_ir(
    ir: dict[str, Any],
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_images: int = DEFAULT_MAX_IMAGES,
) -> list[IRChunk]:
    fmt = ir.get("format")
    if fmt == "pptx":
        return _pack(
            ir, units_key="slides", unit_kind="slide",
            native_index=lambda u: u.get("index", 0),
            image_count_fn=_count_pptx_slide_images,
            max_tokens=max_tokens, max_images=max_images,
        )
    if fmt == "pdf":
        return _pack(
            ir, units_key="pages", unit_kind="page",
            native_index=lambda u: u.get("index", 0),
            image_count_fn=_count_pdf_page_images,
            max_tokens=max_tokens, max_images=max_images,
        )
    if fmt == "xlsx":
        return _pack(
            ir, units_key="sheets", unit_kind="sheet",
            native_index=lambda u: u.get("index", 0),
            image_count_fn=lambda u: len(u.get("images", [])),
            max_tokens=max_tokens, max_images=max_images,
        )
    if fmt in ("html", "markdown", "docx"):
        return _pack(
            ir, units_key="blocks", unit_kind="block",
            native_index=None,
            image_count_fn=_count_html_block_images,
            max_tokens=max_tokens, max_images=max_images,
        )
    raise ValueError(f"unknown IR format: {fmt!r}")


# ---------- core packer ----------

def _pack(
    ir: dict[str, Any],
    *,
    units_key: str,
    unit_kind: str,
    native_index: Callable[[dict], int] | None,
    image_count_fn: Callable[[dict], int],
    max_tokens: int,
    max_images: int,
) -> list[IRChunk]:
    template = {k: v for k, v in ir.items() if k != units_key}
    units = ir.get(units_key, [])

    if not units:
        empty_ir = dict(template)
        empty_ir[units_key] = []
        return [IRChunk(
            chunk_index=0, total_chunks=1, unit_kind=unit_kind,  # type: ignore[arg-type]
            unit_start=0, unit_end=-1,
            token_count=count_tokens(json.dumps(empty_ir, ensure_ascii=False, default=str)),
            image_count=0, truncated=False, ir=empty_ir,
        )]

    # Pass 1 — greedy pack into raw chunks (start_pos, end_pos, units, tokens, imgs, truncated)
    raw: list[tuple[int, int, list, int, int, bool]] = []
    cur_start = -1
    cur: list[dict] = []
    cur_tokens = 0
    cur_imgs = 0

    for i, u in enumerate(units):
        u_tokens = count_tokens(json.dumps(u, ensure_ascii=False, default=str))
        u_imgs = image_count_fn(u)
        oversized = u_tokens > max_tokens or u_imgs > max_images

        # Flush current chunk if adding this unit would exceed caps
        if cur and (cur_tokens + u_tokens > max_tokens or cur_imgs + u_imgs > max_images):
            raw.append((cur_start, i - 1, cur, cur_tokens, cur_imgs, False))
            cur, cur_tokens, cur_imgs = [], 0, 0
            cur_start = -1

        # Oversized single unit — emit alone with truncated=True
        if oversized and not cur:
            raw.append((i, i, [u], u_tokens, u_imgs, True))
            log.warning(
                "ir_chunk: %s[%d] exceeds caps (tokens=%d > %d or images=%d > %d); "
                "emitting oversize chunk",
                units_key, i, u_tokens, max_tokens, u_imgs, max_images,
            )
            continue

        if cur_start == -1:
            cur_start = i
        cur.append(u)
        cur_tokens += u_tokens
        cur_imgs += u_imgs

    if cur:
        raw.append((cur_start, len(units) - 1, cur, cur_tokens, cur_imgs, False))

    # Pass 2 — materialize IRChunks
    total = len(raw)
    result: list[IRChunk] = []
    for idx, (start_pos, end_pos, subset, tokens, imgs, truncated) in enumerate(raw):
        if native_index is not None:
            unit_start = native_index(units[start_pos])
            unit_end = native_index(units[end_pos])
        else:
            unit_start = start_pos
            unit_end = end_pos
        chunk_ir_obj = dict(template)
        chunk_ir_obj[units_key] = subset
        # Recount on materialized object (template adds a small constant)
        chunk_tokens = count_tokens(json.dumps(chunk_ir_obj, ensure_ascii=False, default=str))
        result.append(IRChunk(
            chunk_index=idx,
            total_chunks=total,
            unit_kind=unit_kind,  # type: ignore[arg-type]
            unit_start=unit_start,
            unit_end=unit_end,
            token_count=chunk_tokens,
            image_count=imgs,
            truncated=truncated,
            ir=chunk_ir_obj,
        ))
    return result


# ---------- image counters ----------

def _count_pptx_slide_images(slide: dict[str, Any]) -> int:
    return sum(
        1 for s in _iter_pptx_shapes(slide.get("shapes", []))
        if s.get("type") == "image"
    )


def _iter_pptx_shapes(shapes):
    for s in shapes:
        yield s
        if s.get("type") == "group":
            yield from _iter_pptx_shapes(s.get("children", []))


def _count_pdf_page_images(page: dict[str, Any]) -> int:
    base = 1 if page.get("page_image") else 0
    return base + len(page.get("images_on_page", []))


def _count_html_block_images(block: dict[str, Any]) -> int:
    return 1 if block.get("type") in ("image", "figure") else 0
