"""Deterministic markdown post-processing after the agent + subagents.

The LLM cleaner sometimes skips rules (e.g. it might add the document
title and prune fluff but forget the scan-page marker rule). These passes
guarantee a few high-signal cleanups regardless of model behavior. Keep
them surgical — anything subjective belongs in the cleaner subagent.
"""
from __future__ import annotations

import re
from typing import Any

# Marker emitted by the renderer: **[Image - <container.kind> #<idx>...]**
_IMAGE_MARKER_RE = re.compile(
    r"^\*\*\[Image - (?P<kind>\w+) #(?P<idx>\d+)(?:, \"(?P<label>[^\"]*)\")?\]\*\*\s*$",
    re.MULTILINE,
)
# Same marker but matched as a whole line (incl. its trailing newline) for
# wholesale removal — the marker is an internal scaffold for the agent +
# reviewer (count N image refs → N markers); it is noise in the final output.
_IMAGE_MARKER_LINE_RE = re.compile(
    r"^\*\*\[Image - \w+ #\d+(?:, \"[^\"]*\")?\]\*\*[ \t]*\n?",
    re.MULTILINE,
)

# Caption-body patterns that indicate a decorative / logo / watermark image
# — short, mostly describing a brand mark with no information value.
_LOGO_CAPTION_RE = re.compile(
    r"^\s*(?:Logo[: ]|Watermark[: ]|Branding[: ]|Decorative image|"
    r"H[iì]nh trang tr[íi]|Logo\s+(?:image|with))",
    re.IGNORECASE,
)
_LOGO_KEYWORDS_RE = re.compile(
    r"\b(?:red square|white curved lines|accelio|brand(?:ing)?|trademark|"
    r"™|\(R\)|watermark|logo)\b",
    re.IGNORECASE,
)


def titlecase_h1(md: str) -> str:
    """Convert a leading `# ALL CAPS HEADING` into Title Case.

    Only touches a single line starting with `# ` whose alphabetic content is
    entirely uppercase. Acronyms (all-caps tokens >=2 chars surrounded by
    word boundaries) are preserved during the conversion.
    """
    lines = md.splitlines()
    for i, line in enumerate(lines[:5]):  # scan only the top of the document
        if not line.startswith("# ") or line.startswith("## "):
            continue
        title = line[2:].strip()
        letters = [c for c in title if c.isalpha()]
        if not letters or not all(c.isupper() for c in letters):
            continue
        # Title Case while keeping short stopwords lowercase (except first word).
        words = title.split()
        small = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of",
                 "on", "or", "the", "to", "vs", "via"}
        out: list[str] = []
        for j, w in enumerate(words):
            lower = w.lower()
            if j != 0 and lower in small:
                out.append(lower)
            else:
                out.append(w.capitalize())
        lines[i] = "# " + " ".join(out)
        break
    return "\n".join(lines)


def dedupe_adjacent_image_markers(md: str) -> str:
    """Collapse runs of an identical image-marker line into a single one.

    The reviewer is supposed to delete duplicates but sometimes leaves them.
    Match exact marker-line equality including the body caption — only when
    BOTH the marker line AND the immediately-following caption body are the
    same as the previous occurrence.
    """
    blocks = re.split(r"(?=^\*\*\[Image - )", md, flags=re.MULTILINE)
    seen: dict[str, int] = {}
    out: list[str] = []
    for blk in blocks:
        if blk.startswith("**[Image - "):
            # split this image-block from its trailing content (next blank line
            # or next non-image content). Treat the entire block as the dedupe
            # key — same marker + same caption = duplicate.
            key = blk.strip()
            if seen.get(key):
                continue
            seen[key] = 1
        out.append(blk)
    return "".join(out)


def strip_decorative_image_blocks(md: str) -> str:
    """Remove `**[Image - ...]**` blocks whose caption is logo / watermark.

    Heuristic: caption first non-empty line matches the `Logo:` pattern, OR
    the caption body is <= 2 short lines that contain brand-mark keywords.
    """
    blocks = re.split(r"(?=^\*\*\[Image - )", md, flags=re.MULTILINE)
    kept: list[str] = []
    for blk in blocks:
        if not blk.startswith("**[Image - "):
            kept.append(blk)
            continue
        # Separate marker line from caption body
        marker_end = blk.find("\n")
        if marker_end == -1:
            kept.append(blk)
            continue
        body = blk[marker_end + 1:]
        # Take the part of body up to the next blank line — that's the caption
        caption_end = body.find("\n\n")
        caption = body if caption_end == -1 else body[:caption_end]
        caption_stripped = caption.strip()
        if not caption_stripped:
            kept.append(blk)
            continue
        first_line = caption_stripped.splitlines()[0]
        line_count = len(caption_stripped.splitlines())
        is_logo = bool(_LOGO_CAPTION_RE.match(first_line))
        is_brand_short = (
            line_count <= 2
            and len(caption_stripped) < 200
            and bool(_LOGO_KEYWORDS_RE.search(caption_stripped))
        )
        if is_logo or is_brand_short:
            # drop the marker + caption, keep anything past the caption end
            if caption_end == -1:
                continue
            kept.append(body[caption_end + 2:])
        else:
            kept.append(blk)
    out = "".join(kept)
    return re.sub(r"\n{3,}", "\n\n", out)


def strip_scan_page_markers(md: str, ir: dict[str, Any]) -> str:
    """Remove `**[Image - pdf_page #N, "Page N"]**` lines for full-page scans.

    The caption body (already a transcription of the page) is kept; only the
    structural marker line is stripped. We strip when EITHER:
      - the IR is flagged `is_scanned: True` (whole document is a scan), OR
      - the specific page has no real text content (text_blocks empty or all
        very short).
    """
    if ir.get("format") != "pdf":
        return md

    is_scanned_doc = bool(ir.get("is_scanned"))
    scan_pages: set[int] = set()
    if is_scanned_doc:
        for page in ir.get("pages", []) or []:
            scan_pages.add(int(page.get("index", 0)))
    else:
        for page in ir.get("pages", []) or []:
            blocks = page.get("text_blocks", []) or []
            total_text = sum(len((b.get("text") or "").strip()) for b in blocks)
            if total_text < 40 and page.get("page_image"):
                scan_pages.add(int(page.get("index", 0)))

    if not scan_pages:
        return md

    def _strip(match: re.Match[str]) -> str:
        if match.group("kind") != "pdf_page":
            return match.group(0)
        idx = int(match.group("idx"))
        if idx not in scan_pages:
            return match.group(0)
        return ""

    cleaned = _IMAGE_MARKER_RE.sub(_strip, md)
    # collapse stray blank-line runs left behind by the removed line
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned


def strip_image_markers(md: str) -> str:
    """Drop every `**[Image - ...]**` scaffold line, keeping the caption /
    transcription that follows it as plain content.

    Run LAST among the image passes: `strip_decorative_image_blocks` and
    `dedupe_adjacent_image_markers` both key off the marker line, so they
    must see it before it's removed here.
    """
    cleaned = _IMAGE_MARKER_LINE_RE.sub("", md)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip() + "\n"


def demote_h2_subtitle(md: str) -> str:
    """Demote a `## subtitle` line that immediately follows another `## section`.

    Pptx slides commonly carry both a section title ("03 · DECISION FLOW") and
    a subtitle ("Sơ đồ logic xét duyệt tín dụng"). On chunk 0 the agent renders
    these as `##` / `###`, but on continuation chunks it sometimes emits both
    at `##`, flattening the hierarchy. We detect the pattern locally: two
    consecutive `##` headings with only blank lines between them → the second
    is a subtitle, demote it to `###`. If real content appears between them,
    they are independent sections and we leave them alone. Lines inside fenced
    code blocks are ignored.
    """
    lines = md.splitlines()
    in_fence = False
    pending_h2 = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        is_h2 = line.startswith("## ") and not line.startswith("### ")
        if is_h2:
            if pending_h2:
                lines[i] = "#" + line  # ## -> ###
                pending_h2 = False
            else:
                pending_h2 = True
        elif line.strip() and not stripped.startswith("#"):
            pending_h2 = False
    result = "\n".join(lines)
    if md.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def collapse_duplicate_h1(md: str) -> str:
    """Keep only the first `# ` heading; demote any later ones to `## `.

    Multi-chunk renders synthesize one document title per chunk, so the
    joined markdown can carry several H1s. The first wins as the document
    title; the rest become section headings. Lines inside fenced code
    blocks are left untouched (a `# comment` is not a heading).
    """
    lines = md.splitlines()
    seen_h1 = False
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("# "):
            if seen_h1:
                lines[i] = "#" + line
            else:
                seen_h1 = True
    result = "\n".join(lines)
    if md.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def apply_postprocess(md: str, ir: dict[str, Any]) -> str:
    """Run all deterministic post-processing passes."""
    md = strip_scan_page_markers(md, ir)
    md = strip_decorative_image_blocks(md)
    md = dedupe_adjacent_image_markers(md)
    md = strip_image_markers(md)
    md = demote_h2_subtitle(md)
    md = titlecase_h1(md)
    return md
