# 08 — Errors & Observability

[← Index](./README.md)

## Error class hierarchy

```python
class ConverterError(Exception): ...

# Pre-extraction
class UnsupportedFormatError(ConverterError): ...
class FileTooLargeError(ConverterError): ...
class FileNotFoundError_(ConverterError): ...
class PathResolutionError(ConverterError): ...

# Extraction phase
class ExtractionError(ConverterError): ...
class EncryptedFileError(ExtractionError): ...
class CorruptedFileError(ExtractionError): ...

# LLM phase
class LLMError(ConverterError): ...
class LLMRateLimitError(LLMError): ...
class LLMSafetyBlockError(LLMError): ...
class LLMContextOverflowError(LLMError): ...

# Agent phase
class AgentRecursionError(ConverterError): ...
class ConvertTimeoutError(ConverterError): ...
```

Each error carries `source_path` and an optional `cause` for traceback chaining.

## Retry policy

Wrapped via `tenacity` around LLM invocations only — never around extractors.

| Error class | Retry? | Backoff |
|---|---|---|
| `LLMRateLimitError` (429) | 5× | Exponential 2-60s |
| `ConnectionError` / `TimeoutError` | 5× | Exponential 2-60s |
| `LLMSafetyBlockError` | No | — |
| `LLMContextOverflowError` | No | — |
| `ExtractionError` | No | — |
| Image caption failure (per image) | 3× | Linear 1-5s |
| Agent recursion limit | No | — |

## Graceful degradation

Partial success preferred over total failure.

| Failure | Fallback | Surfaced as |
|---|---|---|
| Image caption fails after retries | `alt_text` if present, else `[Image: caption unavailable]` | warning |
| HTML / MD remote image fetch fails | `alt_text`, `fetch_status="failed"` | warning |
| SmartArt XML parse fails | `[SmartArt: parse failed — slide N]` placeholder | warning |
| Chart data extract fails | `[Chart: <type> — data unavailable]` | warning |
| Quality reviewer fails | use `/draft.md` as `/final.md` | warning |
| Single chunk LLM fails | skip chunk, emit `[Chunk N: conversion failed]` | warning |
| PDF page text extract fails (mixed PDF) | fall back to vision-only for that page | warning |

`convert()` raises only when **no meaningful output** can be produced (file corrupt, all extractors fail, etc.).

## Observability

### Logging

- Python `logging`, namespace `converter.*`.
- Default: `INFO` for top-level events; `DEBUG` for per-block detail.
- Structured fields on each record: `source_path`, `format`, `phase` (extract / caption / agent / review / finalize), `duration_ms`, `tokens_in`, `tokens_out`.
- Configure via `logging.getLogger("converter").setLevel(...)`.

### MLflow tracing

Auto-enabled on Databricks runtime; no-op locally. Spans:

```
convert (root)
├── path_resolve
├── extract (per format)
│   ├── extract.parse
│   ├── extract.images
│   └── extract.tables
├── caption_pass
│   └── caption.image_<id>  (per image)
├── chunk_pass (per chunk)
│   ├── agent.invoke
│   └── agent.tool.<name>
├── subagent.quality-reviewer
└── finalize
```

### Metrics — `ConvertResult.metadata`

Always populated:

```python
{
    "format": "pptx",
    "size_bytes": 1234567,
    "extract_duration_ms": 230,
    "caption_pass_duration_ms": 4500,
    "caption_pass_image_count": 12,
    "caption_pass_failures": 0,
    "agent_duration_ms": 8200,
    "agent_chunks": 1,
    "agent_tool_calls": 25,
    "review_duration_ms": 1100,
    "review_fixes_applied": 2,
    "total_duration_ms": 14030,
    "tokens_in_total": 45200,
    "tokens_out_total": 8900,
    "models_used": {"text": "databricks-claude-sonnet-4-6", "vision": "databricks-claude-haiku-4-5"},
}
```

### Warnings — `ConvertResult.warnings`

Non-fatal issues surfaced for caller visibility, e.g.:

```python
[
    "Page 7: scanned, OCR via vision used",
    "Image img_3: caption fetch failed (rate limit after 5 retries), used alt_text",
    "Chunk 2: oversized atomic unit (single slide > 150K tokens), processed alone",
    "Sheet 'Hidden_data': hidden, skipped",
]
```

## Configuration precedence

1. Direct function call `convert(..., options=...)` — strongest
2. Module default override `converter.set_default_options(...)`
3. Env vars (`CONVERTER_TEXT_MODEL`, `CONVERTER_VISION_MODEL`, `CONVERTER_LOG_LEVEL`, plus provider API key env vars)
4. Built-in dataclass defaults — weakest

Explicitly **not supported** in v1: YAML / TOML config files, `.env` auto-load, per-format option overrides.

## Safety caps

Hard-coded to prevent runaway cost:

```python
_MAX_IMAGES_PER_FILE = 500
_MAX_PAGES_PER_PDF = 1000
_MAX_SHEETS_PER_XLSX = 100
_MAX_SLIDES_PER_PPTX = 500
_MAX_IMAGE_PIXELS_BEFORE_RESIZE = 8000 * 8000
_MAX_TOTAL_DURATION_SECONDS = 1800
```

Exceeding caps raises early, before entering the agent loop.

## Caching

- `convert()` does not cache between calls.
- LLM prompt cache (`cache_control: ephemeral`) enabled for system prompts → benefits multi-chunk runs.
- Caption pre-pass cache: in-memory only, within a single call.
