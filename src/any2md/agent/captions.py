"""Parallel image captioning pre-pass.

Calls `vision_llm.ainvoke()` per image with LangChain's unified message
format. Rate-limited via Semaphore (concurrency cap) + simple token bucket
(requests-per-minute). Falls back to alt_text / placeholder on persistent failure.

Spec: docs/superpowers/specs/2026-05-21-databricks-converter/07-agent.md
      §"Caption pre-pass"
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from typing import TYPE_CHECKING

from ..extractors._image_utils import is_svg
from .image_refs import ImageRef, collect_image_refs

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from ..options import ConvertOptions

log = logging.getLogger(__name__)


IMAGE_CAPTIONER_PROMPT = """\
You are an image-content extractor for a document-to-markdown pipeline.
You receive ONE image plus its surrounding-document context, and return
either a short numeric summary OR a full verbatim transcription.

<procedure>
1. CLASSIFY the image (see <classification/>).
2. If it is a NUMERIC_TABLE, follow <mode_a/>.
3. Otherwise, follow <mode_b/>.
4. Apply <language/> rules to anything YOU write (not to text copied
   from the image — that stays in its original language).
5. Emit the extraction. No prefix, no quotes, no code fence.
</procedure>

<classification>
NUMERIC_TABLE = a grid of rows x columns whose cells are DOMINATED by
numeric values (figures, percentages, currency, dates, counts) plus
at most short header/label cells. The grid is the entire payload — no
surrounding charts, diagrams, photos, screenshots, logos, or prose.

NOT NUMERIC_TABLE (use mode B):
- Tables whose cells are mostly sentences, descriptions, or prose.
- Tables inside a screenshot or a larger composition.
- Anything containing a chart, flowchart, SmartArt, diagram, photo,
  illustration, UI screenshot, or logo — even when a table is present.
</classification>

<mode_a name="NUMERIC_TABLE — summary only">
Output 1-2 sentences describing what the numbers represent and the
main trend / comparison / takeaway (ranges, growth direction, outliers).
DO NOT transcribe individual cells. DO NOT output the table itself.

Example output:
  Doanh thu quy theo bo phan FY2023: ban le tang deu tu 1.2M (Q1) len
  4.8M (Q4); bo phan cong nghiep dao dong quanh 2M va dat dinh o Q3.
</mode_a>

<mode_b name="EVERYTHING ELSE — full verbatim extraction">
Transcribe ALL visible text VERBATIM in the image's original
language(s). Preserve structural cues using markdown:
- Headings, bullet/numbered lists, labels, callouts, in-image captions.
- Charts: chart type, axes/series labels, the data values you can read,
  and the trend or comparison highlighted.
- Diagrams / flowcharts / SmartArt: enumerate EVERY node text and EVERY
  connector as `A -> B` (include any edge label). Note the layout kind
  (hierarchy / cycle / process / matrix / radial / pyramid).
- Screenshots: describe the UI structure (panes, controls, menus),
  transcribe visible text, note the state or workflow shown.
- Photos / illustrations / logos: describe subject, setting, salient
  objects; transcribe any text overlays.

Markdown is allowed (lists, **bold**, inline code). Do NOT wrap the
whole output in a code fence.

Example output (mixed Vietnamese + English flowchart):
  Flowchart titled "Customer Onboarding". Layout: process (left to right).
  - Nodes: "Dang ky" -> "Xac thuc email" -> "KYC submission" -> "Approval"
  - Branch: "KYC submission" -> "Reject" labeled "documents incomplete"
  - Note next to "Approval": "SLA 24h"
</mode_b>

<language>
Output language for text YOU generate (summaries, chart-trend wording,
layout notes, scene descriptions):
  caption_language = "{caption_language}"
  - "auto"  -> match the surrounding document context language; if
               context is empty or ambiguous, use "{primary_language}".
  - "vi" / "en" -> always use that language.
Text copied FROM the image stays in its original language regardless.
</language>

<guardrails>
- Use surrounding context to disambiguate intent only; never invent
  content that is not visible in the image.
- Purely decorative images (separators, ornaments, blank backgrounds
  with no information): output exactly "Decorative image" (en) or
  "Hinh trang tri" (vi). Nothing else.
- NEVER translate text appearing in the image.
- NEVER add a prefix ("Caption:", "Mo ta:", "Description:") or wrap the
  output in quotes / code fence.
- NEVER hallucinate numbers, names, or relationships not visible.
</guardrails>

You are an image-content extractor: classify, then transcribe verbatim
(mode B) or summarize tersely (mode A). Apply language rules only to
text you generate.
"""


class _TokenBucket:
    """Releases one slot every `period_s / rate` seconds."""

    def __init__(self, rate: int, period_s: float = 60.0) -> None:
        self.interval = period_s / max(rate, 1)
        self._lock = asyncio.Lock()
        self._next_at = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_at - now
            self._next_at = max(now, self._next_at) + self.interval
        if wait > 0:
            await asyncio.sleep(wait)


async def caption_pass(
    ir: dict,
    images: dict[str, bytes],
    vision_llm: "BaseChatModel",
    options: "ConvertOptions",
) -> dict[str, str]:
    """Caption every image referenced by IR. Returns {image_id: caption}."""
    refs = collect_image_refs(ir)
    if not refs:
        return {}

    semaphore = asyncio.Semaphore(options.max_concurrent_image_captions)
    bucket = _TokenBucket(options.image_caption_requests_per_minute)
    captions: dict[str, str] = {}

    async def caption_one(ref: ImageRef) -> None:
        async with semaphore:
            await bucket.acquire()
            for attempt in range(3):
                try:
                    captions[ref["id"]] = await _invoke_captioner(
                        ref, images, vision_llm, options,
                    )
                    return
                except Exception as e:
                    log.warning("caption attempt %d failed for %s: %s", attempt + 1, ref["id"], e)
                    await asyncio.sleep(2 ** attempt)
            captions[ref["id"]] = ref.get("alt_text") or "[Image: caption unavailable]"

    await asyncio.gather(*(caption_one(r) for r in refs))
    return captions


async def _invoke_captioner(
    ref: ImageRef,
    images: dict[str, bytes],
    vision_llm: "BaseChatModel",
    options: "ConvertOptions",
) -> str:
    rel = ref["relative_path"]
    blob = images.get(rel)
    if blob is None:
        return ref.get("alt_text") or "[Image: not found]"

    if is_svg(blob):
        return ref.get("alt_text") or "[SVG diagram: caption unavailable]"

    b64 = base64.b64encode(blob).decode("ascii")
    system = IMAGE_CAPTIONER_PROMPT.format(
        caption_language=options.caption_language,
        primary_language=options.primary_language,
    )
    context_lines = [
        f"Container: {ref.get('container_kind','?')} #{ref.get('container_index','?')}",
    ]
    if ref.get("label"):
        context_lines.append(f"Label: {ref['label']}")
    if ref.get("alt_text"):
        context_lines.append(f"Alt text: {ref['alt_text']}")
    if ref.get("context_text"):
        context_lines.append(f"Surrounding text: {ref['context_text']}")
    context = "\n".join(context_lines)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": [
            {"type": "text", "text": context},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
        ]},
    ]
    result = await vision_llm.ainvoke(messages)
    text = result.content if isinstance(result.content, str) else _join_content(result.content)
    return text.strip()


def _join_content(blocks: list) -> str:
    parts: list[str] = []
    for b in blocks:
        if isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif isinstance(b, str):
            parts.append(b)
    return " ".join(parts)
