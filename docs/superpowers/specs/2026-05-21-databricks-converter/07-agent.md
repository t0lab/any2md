# 07 — Agent

[← Index](./README.md)

## Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Caption pre-pass (parallel)                                │
│    rate-limited via Semaphore + token bucket                │
│    vision_model captions every ImageRef → /captions.json    │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│  Chunker                                                    │
│    chunk_ir(ir, max_chunk_tokens) → [chunk_1, chunk_2, ...] │
│    boundary: atomic unit (page/slide/sheet/section)         │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
        for each chunk (sequential):
        ┌────────────────────────────────────────┐
        │  MAIN ORCHESTRATOR (deepagent)         │
        │  - model: text_model                   │
        │  - tools: read_ir, caption_image,      │
        │           write_markdown, finalize     │
        │  - subagents: quality_reviewer         │
        │  - pre-loaded virtual FS               │
        │                                        │
        │  format == "markdown"                  │
        │     → MAIN_PROMPT_MARKDOWN             │
        │  else                                  │
        │     → MAIN_PROMPT_DEFAULT              │
        └────────────────────────────┬───────────┘
                                     │
                                     ▼
                          per-chunk /draft_N.md
                                     │
                          concat → /draft.md
                                     │
                                     ▼
                  quality_reviewer subagent (single pass)
                                     │
                                     ▼
                               /final.md → returned
```

## Virtual FS layout

```
/ir.json                            (current chunk's IR)
/captions.json                      (full file's captions, shared by all chunks)
/raw_images/<image_id>.png          (full file's images, shared by all chunks)
/raw_images/page_<n>.png            (full PDF page renders)
/previous_tail.md                   (last ~1000 chars of previous chunk's output)
/draft.md                           (main agent writes; concat of all chunks)
/final.md                           (quality reviewer writes; final output)
```

## Caption pre-pass

```python
async def caption_pass(
    ir: dict,
    images: dict[str, bytes],
    vision_llm: BaseChatModel,
    options: ConvertOptions,
) -> dict[str, str]:
    image_refs = collect_image_refs(ir)
    limiter = RateLimiter(rpm=options.image_caption_requests_per_minute)
    semaphore = asyncio.Semaphore(options.max_concurrent_image_captions)
    captions = {}

    async def caption_one(ref):
        async with semaphore:
            await limiter.acquire()
            for attempt in range(3):
                try:
                    captions[ref["id"]] = await invoke_captioner(ref, images, vision_llm, options)
                    return
                except (LLMRateLimitError, TimeoutError, ConnectionError):
                    await asyncio.sleep(2 ** attempt)
            captions[ref["id"]] = ref.get("alt_text") or "[Image: caption unavailable]"

    await asyncio.gather(*[caption_one(r) for r in image_refs])
    return captions
```

`RateLimiter` uses a token bucket releasing one token every `60 / rpm` seconds.

## Chunking

`chunk_ir(ir, max_tokens)` produces chunks whose atomic units are **never split**:

| Format | Atomic unit |
|---|---|
| pptx | 1 slide |
| pdf | 1 page |
| xlsx | 1 sheet (oversized sheet kept alone with warning) |
| docx | 1 section (heading level 1, or `w:lastRenderedPageBreak`) |
| html | 1 top-level `<section>` or `<h1>` boundary |
| markdown | 1 H1 boundary (whole file if no H1) |

If a single atomic unit exceeds `max_chunk_tokens`, it goes alone in its chunk with `oversized=true` warning.

`previous_tail.md` is set to the last ~1000 chars of the previous chunk's output and made available to the main agent for continuity (avoid duplicate headings, continue numbered lists).

```python
def chunk_ir(ir: dict, max_tokens: int) -> list[dict]:
    atomic_units = list_atomic_units(ir)
    chunks, current, current_tokens = [], [], 0
    for unit in atomic_units:
        unit_tokens = estimate_tokens(unit)
        if unit_tokens > max_tokens:
            if current: chunks.append(build_chunk(ir, current))
            chunks.append(build_chunk(ir, [unit], oversized_warning=True))
            current, current_tokens = [], 0
            continue
        if current_tokens + unit_tokens > max_tokens:
            chunks.append(build_chunk(ir, current))
            current, current_tokens = [unit], unit_tokens
        else:
            current.append(unit)
            current_tokens += unit_tokens
    if current: chunks.append(build_chunk(ir, current))
    return chunks
```

## Tools (main orchestrator)

```python
@tool
def read_ir() -> dict: ...

@tool
def caption_image(image_id: str) -> str:
    """Look up the pre-computed caption for image_id from /captions.json."""

@tool
def write_markdown(content: str) -> str:
    """Write or overwrite /draft.md (this chunk's output)."""

@tool
def read_image_bytes(image_id: str) -> str:
    """Return base64 PNG. Rarely needed — caption_image already runs vision."""

@tool
def finalize() -> str:
    """Mark chunk done. Quality reviewer runs after all chunks complete."""
```

## Subagent

```python
# agent/subagents/quality_reviewer.py
quality_reviewer: SubAgent = {
    "name": "quality-reviewer",
    "description": (
        "Use ONCE at the end to verify /draft.md matches /ir.json. "
        "Reads both, fixes missing blocks / wrong reading order / "
        "missing image captions / invalid markdown, writes /final.md. "
        "Do NOT use mid-generation."
    ),
    "system_prompt": QUALITY_REVIEWER_PROMPT,
    "model": "databricks-claude-sonnet-4-6",
    "tools": ["read_file", "write_file"],
}
```

**Image captioning is NOT a deepagent subagent** — it runs in the pre-pass via direct LLM invocation, parallelized.

## System prompts (English)

### `MAIN_PROMPT_DEFAULT`

```
You are a document-to-markdown converter running on Databricks.

TASK
You are given an intermediate representation (IR) JSON pre-loaded at /ir.json,
parsed from a source file (xlsx/docx/pptx/pdf/html). Each block or shape has
an `order` field. Produce markdown that:

1. Walks the IR in ascending `order`. Do NOT skip any block. Do NOT reorder.
2. Embeds image captions inline at each image's `order` position. Use
   caption_image(image_id) to fetch the pre-computed caption for every image.
3. Renders tables as GFM markdown tables. Renders charts as a header
   "**Chart: <title>**", a markdown table of the data, then a 1-2 sentence
   description derived from the data. Renders SmartArt as a nested bullet list
   for hierarchy/list layouts and as a Mermaid flowchart block for cycle/process
   layouts. Renders grouped shapes with diagram_hint="flowchart" as a Mermaid
   flowchart block whose edges come from the connector pairs.
4. Renders headings as #/##/### by level. Preserves text-run formatting
   (**bold**, *italic*, `code`, [link](url)).
5. Outputs pure markdown (CommonMark + GFM tables + Mermaid blocks).

PROCEDURE
- Call read_ir() once.
- Walk every block/shape by `order`.
- For each image block, call caption_image(image_id) and embed the result
  using the format below.
- When done, call write_markdown(full_content) once.
- Then call finalize().

IMAGE INLINE FORMAT
[Image: <caption> — <container.kind> #<container.index><, "<label>" if present>]

Example:
[Image: Bar chart of Q1-Q4 2023 revenue, increasing trend — pptx_slide #3, "Revenue"]

DIAGRAM FORMAT
- Chart:    **Chart: <title>**\n<markdown table>\n<1-2 sentence summary>
- SmartArt (hierarchy/list): nested bullet list of node texts
- SmartArt (cycle/process):  ```mermaid\nflowchart LR\n  A --> B ...\n```
- Group + flowchart hint:    ```mermaid``` block, edges from connector pairs

LANGUAGE
- Body text from IR is preserved VERBATIM. Do not translate. The source may
  contain mixed Vietnamese and English — keep all of it as-is.
- Generated text you produce (chart descriptions, SmartArt summaries,
  group-shape narration) follows caption_language: match context if "auto",
  else use the forced language ("vi" or "en").
- Image captions are pre-computed; embed them verbatim from caption_image().

CONSTRAINTS
- Never hallucinate content not in the IR.
- For unknown block types: emit [Unknown block: <type>]
- If /previous_tail.md is present and non-empty, ensure your output continues
  coherently (no duplicate headings; continue numbered lists).
```

### `MAIN_PROMPT_MARKDOWN`

```
You are a markdown document checker running on Databricks.

INPUT
You are given an IR at /ir.json parsed from an existing markdown file.
The IR mirrors the markdown structure — blocks are already in order.

TASK
Produce a normalized, validated markdown output:
1. Walk every block by `order`. Preserve text content verbatim (do NOT translate,
   do NOT paraphrase, do NOT add or remove content).
2. For each image block, call caption_image(image_id) and REPLACE the source
   ![alt](path) syntax with:
       [Image: <caption> — <container info>]
3. Ensure markdown syntax is valid CommonMark + GFM:
   - Fix unclosed code fences
   - Normalize heading levels if gaps exist (h1 → h3 with no h2)
   - Fix table alignment markers
   - Preserve Mermaid / code blocks verbatim
4. If frontmatter is present in /ir.json, emit it unchanged at the very top.

PROCEDURE
- Call read_ir() once.
- Look up image captions via caption_image() — they are already pre-computed.
- Call write_markdown(content) once.
- Call finalize().

LANGUAGE
- Output language = input language. Body text is preserved as-is.

CONSTRAINTS
- Do NOT add commentary, sections, or descriptions not in the IR.
- Do NOT remove content even if you think it's redundant.
```

### `IMAGE_CAPTIONER_PROMPT`

```
You caption a single image embedded in a document. Output: 1-2 sentences,
plain text only (no markdown, no quotes).

You receive:
- One PNG image
- Context: container location/label, text block before and after the image

LANGUAGE
- If caption_language == "auto": match the language of the surrounding context.
  If the context is empty or unclear, use {primary_language}.
- Otherwise: use {caption_language}.

GUIDELINES
- Be specific. Avoid generic phrases like "an image" or "a chart".
- If the image contains important text, quote KEY text VERBATIM in its original
  language (do not translate the quote), then describe in the caption language.
- Use surrounding context to ground intent.
- For decorative images, output "Decorative image" or "Hình trang trí" per language.
- Do not speculate about data not visible.
```

### `QUALITY_REVIEWER_PROMPT`

```
You review markdown produced by the main agent against the source IR.

PROCEDURE
1. Read /ir.json with read_file.
2. Read /draft.md with read_file.
3. Verify:
   a. No IR block is missing from the markdown (compare by `order`).
   b. Reading order is preserved.
   c. Every image in IR has a caption in markdown at the correct position.
   d. Tables have all rows/cols. Charts have data + description. SmartArt is
      rendered as list or Mermaid as appropriate.
   e. Markdown syntax is valid (CommonMark + GFM tables + Mermaid blocks).
4. If everything checks out → write_file /final.md with /draft.md unchanged.
5. If issues exist → fix them and write_file /final.md with the corrected version.

LANGUAGE RULES (during fixes)
- NEVER translate body text. The source may be multi-language (vi + en).
- NEVER change image captions (captioner already chose the right language).
- For generated descriptions, preserve the original language used by the main agent.

CONSTRAINTS
- Do not hallucinate. Do not add content not present in IR.
- Do not re-caption images.
- Only fix structural / completeness / syntax issues.

Return a short summary of fixes applied (or "no changes needed").
```

Prompts containing `{caption_language}` and `{primary_language}` are `.format()`-substituted at runtime.

## LLM wiring

```python
# converter/llm.py
def build_llm(config: ModelConfig) -> BaseChatModel:
    if config.instance is not None:
        return config.instance
    api_key = os.getenv(config.api_key_env) if config.api_key_env else None
    extras = config.extra_params or {}

    if config.provider == "databricks":
        from databricks_langchain import ChatDatabricks
        return ChatDatabricks(endpoint=config.model, temperature=0, **extras)
    if config.provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=config.model, base_url=config.base_url,
            api_key=api_key, temperature=0, **extras,
        )
    if config.provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=config.model, api_key=api_key, temperature=0, **extras)
    if config.provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=config.model, google_api_key=api_key, temperature=0, **extras,
        )
    if config.provider == "custom":
        raise ValueError("provider='custom' requires `instance` to be set")
    raise ValueError(f"Unknown provider: {config.provider}")
```

Vision message format (LangChain unified, works across all 4 providers):

```python
{"role": "user", "content": [
    {"type": "text", "text": context_text},
    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
]}
```
