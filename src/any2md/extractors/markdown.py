"""markdown extractor — markdown-it-py based, pure-Python.

Lossless-ish representation: the IR mirrors source structure so the agent
keeps most things verbatim (the agent's job on markdown is normalization +
image-caption replacement, not generation).
"""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

from any2md.extractors._image_utils import image_dimensions, normalize_to_png
from any2md.extractors.base import ExtractResult

log = logging.getLogger(__name__)

# `gfm-like` would be ideal but it enables linkify, which needs the optional
# `linkify-it-py` package. Enable the two GFM rules we actually want on top of
# CommonMark instead — both ship in markdown-it-py core, no extra dependency.
_FRONTMATTER_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)


class MarkdownExtractor:
    format = "markdown"

    def __init__(self, fetch_remote_images: bool = False, fetch_timeout: int = 10):
        self.fetch_remote_images = fetch_remote_images
        self.fetch_timeout = fetch_timeout

    def extract(self, source: Path) -> ExtractResult:
        warnings: list[str] = []
        images: dict[str, bytes] = {}
        self._img_counter = 0

        text = source.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = self._split_frontmatter(text)
        base_dir = source.parent

        md = MarkdownIt("commonmark").enable(["table", "strikethrough"])
        tree = SyntaxTreeNode(md.parse(body))

        blocks: list[dict[str, Any]] = []
        for node in tree.children:
            for b in self._node_to_blocks(node, base_dir, images, warnings):
                b["order"] = len(blocks)
                blocks.append(b)

        self._wire_image_neighbors(blocks)

        ir: dict[str, Any] = {
            "format": "markdown",
            "source": str(source),
            "frontmatter": frontmatter,
            "base_dir": str(base_dir),
            "blocks": blocks,
        }
        return ExtractResult(ir=ir, images=images, warnings=warnings)

    # ----------------- frontmatter -----------------

    def _split_frontmatter(self, text: str) -> tuple[dict[str, Any] | None, str]:
        m = _FRONTMATTER_RE.match(text)
        if not m:
            return None, text
        fm = self._parse_simple_yaml(m.group(1))
        return (fm or None), text[m.end():]

    def _parse_simple_yaml(self, raw: str) -> dict[str, Any]:
        """Minimal `key: value` parse — pyyaml is not a dependency.

        Nested structures / lists are flattened to their raw string value;
        good enough to surface title/tags/date without pulling in a YAML dep.
        """
        out: dict[str, Any] = {}
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or ":" not in line:
                continue
            if line[0] in " \t-":  # nested/list continuation — skip in v1
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key:
                out[key] = val
        return out

    # ----------------- node dispatch -----------------

    def _node_to_blocks(
        self,
        node: SyntaxTreeNode,
        base_dir: Path,
        images: dict[str, bytes],
        warnings: list[str],
    ) -> list[dict[str, Any]]:
        t = node.type
        if t == "heading":
            runs, _ = self._runs_and_images(node)
            level = int(node.tag[1]) if node.tag[1:2].isdigit() else 1
            return [{"type": "heading", "level": level, "runs": runs}] if runs else []

        if t == "paragraph":
            runs, imgs = self._runs_and_images(node)
            out: list[dict[str, Any]] = []
            if any(r.get("text", "").strip() for r in runs):
                out.append({"type": "paragraph", "runs": runs})
            for src, alt in imgs:
                out.append(self._image_block(src, alt, base_dir, images, warnings))
            return out

        if t in ("bullet_list", "ordered_list"):
            out = []
            self._flatten_list(node, 0, out, base_dir, images, warnings)
            return out

        if t == "table":
            return [self._table_block(node)]

        if t in ("fence", "code_block"):
            info = (node.info or "").strip()
            lang = info.split()[0] if info else None
            return [{"type": "code", "language": lang, "content": node.content}]

        if t == "blockquote":
            nested: list[dict[str, Any]] = []
            for child in node.children:
                for b in self._node_to_blocks(child, base_dir, images, warnings):
                    b["order"] = len(nested)
                    nested.append(b)
            return [{"type": "blockquote", "blocks": nested}] if nested else []

        if t == "hr":
            return [{"type": "divider"}]

        if t == "html_block":
            content = node.content or ""
            return [{"type": "raw_html", "content": content}] if content.strip() else []

        # Unknown container — recurse so nothing is silently dropped.
        out = []
        for child in node.children:
            out.extend(self._node_to_blocks(child, base_dir, images, warnings))
        return out

    def _flatten_list(
        self,
        list_node: SyntaxTreeNode,
        level: int,
        out: list[dict[str, Any]],
        base_dir: Path,
        images: dict[str, bytes],
        warnings: list[str],
    ) -> None:
        """Expand a list into flat paragraph blocks carrying list_kind + list_level.

        Nested lists recurse with an incremented level — mirrors the HTML
        extractor so the renderer treats both identically.
        """
        kind = "bullet" if list_node.type == "bullet_list" else "numbered"
        for item in list_node.children:
            if item.type != "list_item":
                continue
            item_runs: list[dict[str, Any]] = []
            item_imgs: list[tuple[str, str]] = []
            nested: list[SyntaxTreeNode] = []
            extra: list[dict[str, Any]] = []
            for child in item.children:
                if child.type in ("bullet_list", "ordered_list"):
                    nested.append(child)
                elif child.type == "paragraph":
                    r, im = self._runs_and_images(child)
                    item_runs.extend(r)
                    item_imgs.extend(im)
                else:
                    extra.extend(self._node_to_blocks(child, base_dir, images, warnings))
            if any(r.get("text", "").strip() for r in item_runs):
                out.append({
                    "type": "paragraph",
                    "list_kind": kind,
                    "list_level": level,
                    "runs": item_runs,
                })
            for src, alt in item_imgs:
                out.append(self._image_block(src, alt, base_dir, images, warnings))
            out.extend(extra)
            for n in nested:
                self._flatten_list(n, level + 1, out, base_dir, images, warnings)

    def _table_block(self, table_node: SyntaxTreeNode) -> dict[str, Any]:
        rows: list[list[str]] = []
        for section in table_node.children:           # thead / tbody
            for tr in section.children:
                if tr.type != "tr":
                    continue
                row = [self._cell_text(cell) for cell in tr.children if cell.type in ("th", "td")]
                rows.append(row)
        return {"type": "table", "rows": rows}

    def _cell_text(self, cell: SyntaxTreeNode) -> str:
        runs: list[dict[str, Any]] = []
        inline = self._inline_of(cell)
        if inline is not None:
            self._walk_inline(inline, {}, runs, [])
        return "".join(r.get("text", "") for r in runs).strip()

    # ----------------- inline runs + images -----------------

    def _inline_of(self, node: SyntaxTreeNode) -> SyntaxTreeNode | None:
        for c in node.children:
            if c.type == "inline":
                return c
        return None

    def _runs_and_images(
        self, node: SyntaxTreeNode
    ) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
        runs: list[dict[str, Any]] = []
        imgs: list[tuple[str, str]] = []
        inline = self._inline_of(node)
        if inline is not None:
            self._walk_inline(inline, {}, runs, imgs)
        return runs, imgs

    def _walk_inline(
        self,
        node: SyntaxTreeNode,
        style: dict[str, Any],
        runs: list[dict[str, Any]],
        imgs: list[tuple[str, str]],
    ) -> None:
        for child in node.children:
            t = child.type
            if t == "text":
                if child.content:
                    runs.append({"text": child.content, **style})
            elif t == "code_inline":
                runs.append({"text": child.content, "code": True, **style})
            elif t in ("softbreak", "hardbreak"):
                runs.append({"text": "\n"})
            elif t == "strong":
                self._walk_inline(child, {**style, "bold": True}, runs, imgs)
            elif t == "em":
                self._walk_inline(child, {**style, "italic": True}, runs, imgs)
            elif t == "s":
                # No strikethrough field on TextRun — keep the text, drop the mark.
                self._walk_inline(child, style, runs, imgs)
            elif t == "link":
                href = child.attrs.get("href", "")
                sub = {**style, "hyperlink": href} if href else style
                self._walk_inline(child, sub, runs, imgs)
            elif t == "image":
                src = str(child.attrs.get("src", ""))
                imgs.append((src, child.content or ""))
            elif t == "html_inline":
                if child.content:
                    runs.append({"text": child.content, **style})
            elif child.children:
                self._walk_inline(child, style, runs, imgs)

    # ----------------- images -----------------

    def _image_block(
        self,
        src: str,
        alt: str,
        base_dir: Path,
        images: dict[str, bytes],
        warnings: list[str],
    ) -> dict[str, Any]:
        self._img_counter += 1
        img_id = f"img_{self._img_counter}"
        container = {"kind": "md_section", "index": 1, "label": None}
        neighbors = {
            "before_text": "", "after_text": "",
            "before_kind": None, "after_kind": None,
        }
        blob, status, err = self._load_image(src, base_dir)
        if blob is None:
            warnings.append(f"Image {src!r}: {err or 'load failed'}")
            ref: dict[str, Any] = {
                "id": img_id, "relative_path": "", "width_px": 0, "height_px": 0,
                "container": container, "neighbors": neighbors, "fetch_status": status,
            }
            if alt:
                ref["alt_text"] = alt
            if err:
                ref["fetch_error"] = err
            return {"type": "image", "image": ref}

        normalized = normalize_to_png(blob)
        w, h = image_dimensions(normalized)
        rel_path = f"raw_images/{img_id}.png"
        images[rel_path] = normalized
        ref = {
            "id": img_id, "relative_path": rel_path,
            "width_px": w, "height_px": h,
            "container": container, "neighbors": neighbors, "fetch_status": status,
        }
        if alt:
            ref["alt_text"] = alt
        return {"type": "image", "image": ref}

    def _load_image(
        self, src: str, base_dir: Path
    ) -> tuple[bytes | None, str, str | None]:
        if not src:
            return None, "failed", "empty src"

        m = re.match(r"^data:[^;]+;base64,(.+)$", src, re.DOTALL)
        if m:
            try:
                return base64.b64decode(m.group(1)), "ok", None
            except Exception as e:
                return None, "failed", f"data URI decode: {e}"

        parsed = urlparse(src)
        if parsed.scheme in ("http", "https"):
            if not self.fetch_remote_images:
                return None, "skipped", "remote fetch disabled"
            try:
                import urllib.request
                with urllib.request.urlopen(src, timeout=self.fetch_timeout) as resp:
                    return resp.read(), "ok", None
            except Exception as e:
                return None, "failed", f"fetch error: {e}"

        candidate = (base_dir / src).resolve()
        try:
            return candidate.read_bytes(), "ok", None
        except Exception as e:
            return None, "failed", f"read error: {e}"

    # ----------------- image neighbors -----------------

    def _wire_image_neighbors(self, blocks: list[dict[str, Any]]) -> None:
        for i, b in enumerate(blocks):
            if b.get("type") != "image":
                continue
            before_text = after_text = ""
            before_kind = after_kind = None
            if i > 0:
                prev = blocks[i - 1]
                before_kind = prev.get("type")
                before_text = self._block_text(prev)
            if i + 1 < len(blocks):
                nxt = blocks[i + 1]
                after_kind = nxt.get("type")
                after_text = self._block_text(nxt)
            b["image"]["neighbors"] = {
                "before_text": before_text[:200],
                "after_text": after_text[:200],
                "before_kind": before_kind,
                "after_kind": after_kind,
            }

    def _block_text(self, block: dict[str, Any]) -> str:
        t = block.get("type")
        if t in ("heading", "paragraph"):
            return "".join(r.get("text", "") for r in block.get("runs", []))
        if t == "table":
            return " | ".join(" ".join(str(c) for c in row) for row in block.get("rows", [])[:2])
        if t == "code":
            return block.get("content", "")[:200]
        if t == "blockquote":
            inner = block.get("blocks", [])
            return self._block_text(inner[0]) if inner else ""
        return ""
