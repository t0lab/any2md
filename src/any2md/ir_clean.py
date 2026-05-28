"""IR post-extraction cleanup.

Strips redundant / empty / default fields from raw IR before feeding the agent.
Raw IR (from extractors) keeps everything for debugging / auditing; this pass
produces the compact view the agent sees.

Rules per format documented in
docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md
"""
from __future__ import annotations

import copy
import re
from typing import Any

# Filesystem-path leak in image alt_text (artifact of sample authoring environment)
_FILESYSTEM_PATH_RE = re.compile(
    r"^([a-zA-Z]:[\\/]|/|\\\\).*\.(png|jpe?g|gif|webp|bmp|tiff?)$",
    re.IGNORECASE,
)

_NOISE_PDF_META_KEYS = {"creator", "producer", "creationDate", "modDate"}


def clean_ir(ir: dict[str, Any]) -> dict[str, Any]:
    """Return a cleaned copy of `ir`. Original is not modified."""
    out = copy.deepcopy(ir)
    fmt = out.get("format")
    if fmt == "pptx":
        _clean_pptx(out)
    elif fmt == "xlsx":
        _clean_xlsx(out)
    elif fmt == "pdf":
        _clean_pdf(out)
    elif fmt == "html":
        _clean_html(out)
    elif fmt == "docx":
        _clean_docx(out)
    elif fmt == "markdown":
        _clean_markdown(out)
    _drop_empties(out)
    return out


# ---------- helpers ----------

def _is_empty(v: Any) -> bool:
    """None / "" / [] / {} count as empty. 0 and False do not."""
    if v is None:
        return True
    if isinstance(v, (str, list, dict)) and len(v) == 0:
        return True
    return False


def _drop_empties(obj: Any) -> Any:
    """Recursively drop keys whose value is empty after recursion."""
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            cleaned = _drop_empties(obj[k])
            if _is_empty(cleaned):
                del obj[k]
            else:
                obj[k] = cleaned
        return obj
    if isinstance(obj, list):
        return [_drop_empties(x) for x in obj]
    return obj


def _drop_bbox_unit(obj: Any) -> None:
    """Strip `unit` subkey from every bbox dict in the tree."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "bbox" and isinstance(v, dict):
                v.pop("unit", None)
            _drop_bbox_unit(v)
    elif isinstance(obj, list):
        for x in obj:
            _drop_bbox_unit(x)


def _is_filesystem_path_leak(s: str) -> bool:
    return bool(_FILESYSTEM_PATH_RE.match(s or ""))


# ---------- per-format ----------

def _clean_pptx(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    for slide in ir.get("slides", []):
        kept_shapes: list[dict[str, Any]] = []
        for shape in slide.get("shapes", []):
            t = shape.get("type")
            if t == "text":
                kept_paras: list[dict[str, Any]] = []
                for p in shape.get("paragraphs", []):
                    p.pop("alignment", None)
                    if p.get("runs"):
                        kept_paras.append(p)
                shape["paragraphs"] = kept_paras
                if not kept_paras:
                    continue
            elif t == "table":
                # rows_rich carries paragraphs + rowspan/colspan + per-cell text fallback.
                # The outer flat `rows` is a strict subset.
                shape.pop("rows", None)
                # Strip alignment + drop empty paragraphs inside table cells too
                for row in shape.get("rows_rich", []):
                    for cell in row:
                        kept = []
                        for p in cell.get("paragraphs", []):
                            p.pop("alignment", None)
                            if p.get("runs"):
                                kept.append(p)
                        cell["paragraphs"] = kept
            elif t == "image":
                img = shape.get("image", {})
                if _is_filesystem_path_leak(img.get("alt_text", "")):
                    img.pop("alt_text", None)
                img.pop("bbox", None)
            elif t == "chart":
                if not shape.get("axis_labels"):
                    shape.pop("axis_labels", None)
            elif t == "connector":
                if (
                    shape.get("from_shape_id") is None
                    and shape.get("to_shape_id") is None
                    and not shape.get("label")
                ):
                    continue
            kept_shapes.append(shape)
        slide["shapes"] = kept_shapes


def _clean_xlsx(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    for sh in ir.get("sheets", []):
        for tbl in sh.get("tables", []):
            tbl.pop("header_row", None)


def _clean_pdf(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    meta = ir.get("metadata", {})
    for k in list(meta.keys()):
        if k in _NOISE_PDF_META_KEYS:
            del meta[k]
    for p in ir.get("pages", []):
        p.pop("extracted_text", None)
        for tb in p.get("text_blocks", []):
            tb.pop("is_likely_heading", None)


def _clean_html(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    kept_blocks: list[dict[str, Any]] = []
    for blk in ir.get("blocks", []):
        if blk.get("type") in ("paragraph", "heading"):
            kept_runs: list[dict[str, Any]] = []
            for r in blk.get("runs", []):
                txt = r.get("text", "")
                # Drop pure-whitespace runs that carry no formatting
                if txt.strip() == "" and set(r.keys()) <= {"text"}:
                    continue
                kept_runs.append(r)
            blk["runs"] = kept_runs
            if not kept_runs:
                continue
        kept_blocks.append(blk)
    ir["blocks"] = kept_blocks


def _clean_docx(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    ir["blocks"] = _clean_block_list(ir.get("blocks", []))


def _clean_markdown(ir: dict[str, Any]) -> None:
    _drop_bbox_unit(ir)
    ir["blocks"] = _clean_block_list(ir.get("blocks", []))


def _clean_block_list(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop whitespace-only runs and empty container blocks; recurse into nests."""
    kept: list[dict[str, Any]] = []
    for blk in blocks:
        t = blk.get("type")
        if t in ("paragraph", "heading"):
            kept_runs = [
                r for r in blk.get("runs", [])
                if not (r.get("text", "").strip() == "" and set(r.keys()) <= {"text"})
            ]
            blk["runs"] = kept_runs
            if not kept_runs:
                continue
        elif t in ("textbox", "blockquote"):
            blk["blocks"] = _clean_block_list(blk.get("blocks", []))
            if not blk["blocks"]:
                continue
        kept.append(blk)
    return kept
