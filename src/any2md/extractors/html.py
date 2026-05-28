"""html extractor — lxml + bs4 based, pure-Python."""
from __future__ import annotations

import base64
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup, NavigableString, Tag

from any2md.extractors._image_utils import image_dimensions, normalize_to_png
from any2md.extractors.base import ExtractResult

log = logging.getLogger(__name__)

_BLOCK_TAGS = {
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "ul", "ol", "table", "pre", "blockquote",
    "img", "figure", "dl", "hr",
}


class HtmlExtractor:
    format = "html"

    def __init__(self, fetch_remote_images: bool = False, fetch_timeout: int = 10):
        self.fetch_remote_images = fetch_remote_images
        self.fetch_timeout = fetch_timeout

    def extract(self, source: Path) -> ExtractResult:
        warnings: list[str] = []
        images: dict[str, bytes] = {}
        text = source.read_text(encoding="utf-8", errors="replace")

        if not text.strip():
            warnings.append("HTML file is empty")
            return ExtractResult(
                ir={
                    "format": "html",
                    "source": str(source),
                    "title": None,
                    "base_url": None,
                    "blocks": [],
                },
                images=images,
                warnings=warnings,
            )

        soup = BeautifulSoup(text, "lxml")
        for unwanted in soup(["script", "style", "noscript"]):
            unwanted.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else None
        base_url = None
        base = soup.find("base")
        if base and base.get("href"):
            base_url = base["href"]

        body = soup.body or soup
        blocks: list[dict[str, Any]] = []
        img_counter = 0

        for elem in self._walk_blocks(body):
            new_blocks, new_images, img_counter, new_warnings = self._element_to_blocks(
                elem, source, base_url, img_counter
            )
            for b in new_blocks:
                b["order"] = len(blocks)
                blocks.append(b)
            images.update(new_images)
            warnings.extend(new_warnings)

        self._wire_image_neighbors(blocks)

        ir = {
            "format": "html",
            "source": str(source),
            "title": title,
            "base_url": base_url,
            "blocks": blocks,
        }
        return ExtractResult(ir=ir, images=images, warnings=warnings)

    # ----------------- helpers -----------------

    def _walk_blocks(self, root: Tag):
        """Yield top-level block elements in document order.

        Skip elements that will be processed by an ancestor (nested lists,
        figcaption inside figure, li inside ul/ol).
        """
        for child in root.descendants:
            if not isinstance(child, Tag):
                continue
            if child.name not in _BLOCK_TAGS:
                continue
            # Skip nested ul/ol — handled recursively by ancestor
            if child.name in {"ul", "ol"} and child.find_parent(["ul", "ol", "dl"]):
                continue
            # Skip img inside a figure — handled by figure
            if child.name == "img" and child.find_parent("figure"):
                continue
            # Skip dl entries duplicated through descendants
            yield child

    def _element_to_blocks(
        self,
        elem: Tag,
        source: Path,
        base_url: str | None,
        img_counter: int,
    ) -> tuple[list[dict[str, Any]], dict[str, bytes], int, list[str]]:
        images: dict[str, bytes] = {}
        warnings: list[str] = []

        if elem.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(elem.name[1])
            return (
                [{"type": "heading", "level": level, "runs": self._runs(elem)}],
                images,
                img_counter,
                warnings,
            )

        if elem.name == "p":
            runs = self._runs(elem)
            if not runs or all(not r.get("text", "").strip() for r in runs):
                return [], images, img_counter, warnings
            return (
                [{"type": "paragraph", "runs": runs}],
                images,
                img_counter,
                warnings,
            )

        if elem.name in {"ul", "ol"}:
            return self._flatten_list(elem, level=0), images, img_counter, warnings

        if elem.name == "dl":
            return self._flatten_dl(elem), images, img_counter, warnings

        if elem.name == "hr":
            return [{"type": "divider"}], images, img_counter, warnings

        if elem.name == "table":
            rows: list[list[str]] = []
            for tr in elem.find_all("tr"):
                row = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                rows.append(row)
            return (
                [{"type": "table", "rows": rows}],
                images,
                img_counter,
                warnings,
            )

        if elem.name == "pre":
            code = elem.find("code")
            lang = None
            content = elem.get_text()
            if code:
                cls = code.get("class") or []
                for c in cls:
                    if c.startswith("language-"):
                        lang = c[len("language-"):]
                        break
                content = code.get_text()
            return (
                [{"type": "code", "language": lang, "content": content}],
                images,
                img_counter,
                warnings,
            )

        if elem.name == "blockquote":
            return (
                [{"type": "blockquote",
                  "blocks": [{"order": 0, "type": "paragraph", "runs": self._runs(elem)}]}],
                images,
                img_counter,
                warnings,
            )

        if elem.name == "figure":
            img = elem.find("img")
            cap = elem.find("figcaption")
            caption_runs = self._runs(cap) if cap else []
            if img is None:
                if caption_runs:
                    return (
                        [{"type": "paragraph", "runs": caption_runs}],
                        images, img_counter, warnings,
                    )
                return [], images, img_counter, warnings
            img_counter += 1
            block, new_images, w_warnings = self._image_block(
                img, source, base_url, img_counter
            )
            images.update(new_images)
            warnings.extend(w_warnings)
            if block is None:
                return [], images, img_counter, warnings
            fig = {"type": "figure", "image": block["image"]}
            if caption_runs:
                fig["caption"] = caption_runs
            return [fig], images, img_counter, warnings

        if elem.name == "img":
            img_counter += 1
            block, new_images, w_warnings = self._image_block(
                elem, source, base_url, img_counter
            )
            images.update(new_images)
            warnings.extend(w_warnings)
            return ([block] if block else [], images, img_counter, warnings)

        return [], images, img_counter, warnings

    def _flatten_list(self, list_elem: Tag, level: int) -> list[dict[str, Any]]:
        """Expand <ul>/<ol> into a flat sequence of paragraph blocks with list_kind+list_level.

        Nested lists become subsequent paragraphs with increased list_level.
        """
        out: list[dict[str, Any]] = []
        list_kind = "bullet" if list_elem.name == "ul" else "numbered"
        for li in list_elem.find_all("li", recursive=False):
            # Capture li's direct text (ignoring nested ul/ol — handled separately)
            li_clone_runs = self._li_runs(li)
            if li_clone_runs:
                out.append({
                    "type": "paragraph",
                    "list_kind": list_kind,
                    "list_level": level,
                    "runs": li_clone_runs,
                })
            # Recurse into nested ul/ol inside this li
            for nested in li.find_all(["ul", "ol"], recursive=False):
                out.extend(self._flatten_list(nested, level + 1))
        return out

    def _li_runs(self, li: Tag) -> list[dict[str, Any]]:
        """Build runs for an <li>, excluding nested <ul>/<ol> content."""
        runs: list[dict[str, Any]] = []
        for child in li.descendants:
            if self._is_inside_nested_list(child, li):
                continue
            if isinstance(child, NavigableString):
                text = str(child)
                if not text.strip():
                    continue
                run: dict[str, Any] = {"text": text}
                parent = child.parent
                while parent is not None and parent is not li:
                    self._apply_run_style(parent, run)
                    parent = parent.parent
                runs.append(run)
            elif isinstance(child, Tag) and child.name == "br":
                runs.append({"text": "\n"})
        return runs

    def _is_inside_nested_list(self, child: Any, li: Tag) -> bool:
        """True if child sits inside a <ul>/<ol> that is a descendant of li."""
        p = child.parent
        while p is not None and p is not li:
            if isinstance(p, Tag) and p.name in ("ul", "ol"):
                return True
            p = p.parent
        return False

    def _flatten_dl(self, dl: Tag) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for child in dl.find_all(["dt", "dd"], recursive=False):
            runs = self._runs(child)
            if child.name == "dt":
                # Mark dt runs as bold
                for r in runs:
                    r["bold"] = True
            if runs:
                out.append({"type": "paragraph", "runs": runs})
        return out

    def _runs(self, elem: Tag) -> list[dict[str, Any]]:
        runs: list[dict[str, Any]] = []
        for child in elem.descendants:
            if isinstance(child, NavigableString):
                text = str(child)
                if not text.strip():
                    continue
                parent = child.parent
                run: dict[str, Any] = {"text": text}
                while parent is not None and parent is not elem:
                    self._apply_run_style(parent, run)
                    parent = parent.parent
                runs.append(run)
            elif isinstance(child, Tag) and child.name == "br":
                runs.append({"text": "\n"})
        return runs or [{"text": elem.get_text(strip=True)}]

    def _apply_run_style(self, parent: Tag, run: dict[str, Any]) -> None:
        if parent.name in ("b", "strong"):
            run["bold"] = True
        elif parent.name in ("i", "em"):
            run["italic"] = True
        elif parent.name == "u":
            run["underline"] = True
        elif parent.name == "code":
            run["code"] = True
        elif parent.name == "a" and parent.get("href"):
            run["hyperlink"] = parent["href"]

    def _image_block(
        self,
        img_elem: Tag,
        source: Path,
        base_url: str | None,
        img_counter: int,
    ) -> tuple[dict[str, Any] | None, dict[str, bytes], list[str]]:
        images: dict[str, bytes] = {}
        warnings: list[str] = []
        src = img_elem.get("src", "")
        alt = img_elem.get("alt", "")
        img_id = f"img_{img_counter}"
        blob, fetch_status, fetch_error = self._load_image(src, source.parent, base_url)
        if blob is None:
            warnings.append(f"Image {src!r}: {fetch_error or 'load failed'}")
            return (
                {
                    "type": "image",
                    "image": {
                        "id": img_id, "relative_path": "", "width_px": 0, "height_px": 0,
                        "alt_text": alt or None,
                        "container": {"kind": "html_section", "index": 1, "label": None},
                        "neighbors": {
                            "before_text": "", "after_text": "",
                            "before_kind": None, "after_kind": None,
                        },
                        "fetch_status": fetch_status,
                        **({"fetch_error": fetch_error} if fetch_error else {}),
                    },
                },
                images,
                warnings,
            )
        normalized = normalize_to_png(blob)
        w, h = image_dimensions(normalized)
        rel_path = f"raw_images/{img_id}.png"
        images[rel_path] = normalized
        return (
            {
                "type": "image",
                "image": {
                    "id": img_id, "relative_path": rel_path,
                    "width_px": w, "height_px": h,
                    "alt_text": alt or None,
                    "container": {"kind": "html_section", "index": 1, "label": None},
                    "neighbors": {
                        "before_text": "", "after_text": "",
                        "before_kind": None, "after_kind": None,
                    },
                    "fetch_status": fetch_status,
                },
            },
            images,
            warnings,
        )

    def _load_image(
        self,
        src: str,
        base_dir: Path,
        base_url: str | None,
    ) -> tuple[bytes | None, str, str | None]:
        if not src:
            return None, "failed", "empty src"

        m = re.match(r"^data:[^;]+;base64,(.+)$", src)
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

    def _wire_image_neighbors(self, blocks: list[dict[str, Any]]) -> None:
        for i, b in enumerate(blocks):
            if b.get("type") not in ("image", "figure"):
                continue
            before_text, after_text = "", ""
            before_kind, after_kind = None, None
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
            return " | ".join(" ".join(row) for row in block.get("rows", [])[:2])
        if t == "code":
            return block.get("content", "")[:200]
        if t == "figure":
            caption = block.get("caption") or []
            return "".join(r.get("text", "") for r in caption)
        return ""
