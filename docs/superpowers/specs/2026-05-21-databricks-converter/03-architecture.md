# 03 — Architecture & Repo Layout

[← Index](./README.md)

## High-level data flow

```
┌────────────────────────────────────────────────────────────────────────┐
│  Notebook / local dev                                                  │
│  from converter import convert                                         │
│  result = convert("./sample/test.pptx")                                │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
                                  ▼
        ┌─────────────────────────────────────────────────┐
        │  1. Path resolver (UC Volume / relative / local)│
        │  2. Format detector (extension + magic bytes)   │
        └──────────────────────┬──────────────────────────┘
                               │
       ┌───────┬───────┬───────┼───────┬───────┬────────┐
       ▼       ▼       ▼       ▼       ▼       ▼        ▼
    xlsx    docx    pptx     pdf    html     md    (future)
   extractor extractor extractor extractor extractor extractor
       │       │       │       │       │       │
       └───────┴───────┴───────┴───────┴───────┘
                       │
                       ▼  (pure Python, no LLM)
        ┌──────────────────────────────────────────┐
        │  IR JSON + raw image bytes               │
        │  - blocks/shapes in reading order        │
        │  - image refs with container & neighbors │
        │  - tables, charts, smartart, connectors  │
        └──────────────────┬───────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────┐
        │  Caption pre-pass (parallel, rate-limited)   │
        │  vision_model captions every image           │
        │  → /captions.json                            │
        └──────────────────┬───────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────┐
        │  Chunker (atomic-unit boundary: page/slide/   │
        │           sheet/section — never split mid)    │
        └──────────────────┬───────────────────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────────────┐
        │  Deepagent (per chunk)                        │
        │  ──────────────────────                       │
        │  Virtual FS: /ir.json, /captions.json,        │
        │              /raw_images/, /draft.md,         │
        │              /previous_tail.md                │
        │  Tools: read_ir, caption_image (lookup),      │
        │         write_markdown, finalize              │
        │  Subagent: quality-reviewer (final pass)      │
        └──────────────────┬───────────────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │  ConvertResult          │
              │  - markdown             │
              │  - warnings             │
              │  - metadata             │
              │  - ir (if requested)    │
              └─────────────────────────┘
```

## Invariants

- Extractors are pure-Python, **never call an LLM**.
- Image captioning happens **once, in parallel, before the agent runs** — agent only does lookup.
- Chunks honor atomic-unit boundaries; agent processes chunks sequentially with `previous_tail` for continuity.
- Quality reviewer is a single final pass on the concatenated draft, not per-chunk.
- Image bytes never live inside IR; only `ImageRef.relative_path`. Bytes are written to virtual FS at `raw_images/<id>.png` when the agent initializes.
- `order` field is the source of truth for reading order. Extractor sorts; agent never re-sorts.

## Repo Layout

```
converter/
├── README.md
├── pyproject.toml
├── src/
│   └── converter/
│       ├── __init__.py            # exports: convert, batch_convert, ConvertResult, ConvertOptions, ModelConfig
│       ├── api.py                 # public API
│       ├── paths.py               # path resolution
│       ├── detect.py              # format detection
│       ├── ir.py                  # IR TypedDict schemas
│       ├── llm.py                 # build_llm factory
│       ├── errors.py
│       │
│       ├── extractors/
│       │   ├── __init__.py
│       │   ├── base.py            # Extractor protocol, ExtractResult
│       │   ├── xlsx.py
│       │   ├── docx.py
│       │   ├── pptx.py
│       │   ├── pdf.py
│       │   ├── html.py
│       │   └── markdown.py
│       │
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── orchestrator.py    # build_deep_agent, run_agent, caption_pass, chunk loop
│       │   ├── prompts.py         # MAIN_PROMPT_DEFAULT, MAIN_PROMPT_MARKDOWN, IMAGE_CAPTIONER_PROMPT, QUALITY_REVIEWER_PROMPT
│       │   ├── tools.py
│       │   ├── chunking.py        # chunk_ir by atomic units
│       │   ├── captioning.py      # parallel batch with rate limiter
│       │   └── subagents/
│       │       └── quality_reviewer.py
│       │
│       └── utils/
│           ├── logging.py
│           ├── tokens.py          # estimate_tokens
│           └── rate_limit.py      # token bucket
│
├── tests/
│   ├── fixtures/                  # tiny sample files (<50KB each)
│   │   ├── build_fixtures.py
│   │   ├── simple.{xlsx,docx,pptx,pdf,html,md}
│   │   ├── with_chart.pptx
│   │   ├── smartart_hierarchy.pptx
│   │   ├── flowchart_grouped.pptx
│   │   ├── merged_cells.xlsx
│   │   ├── complex.docx
│   │   ├── scanned.pdf
│   │   ├── mixed.pdf
│   │   ├── encrypted.pptx
│   │   ├── multi_lang.pptx
│   │   └── multi_lang_image.pdf
│   ├── golden/                    # JSON snapshots for IR
│   ├── unit/
│   │   ├── test_paths.py
│   │   ├── test_detect.py
│   │   ├── test_extractors_xlsx.py
│   │   ├── test_extractors_docx.py
│   │   ├── test_extractors_pptx.py
│   │   ├── test_extractors_pdf.py
│   │   ├── test_extractors_html.py
│   │   ├── test_extractors_md.py
│   │   ├── test_chunking.py
│   │   └── test_agent_tools.py    # mocked LLM (FakeListChatModel)
│   └── integration/
│       └── test_convert_end_to_end.py  # real LLM, gated by CONVERTER_INTEGRATION_TESTS
│
└── docs/
    └── superpowers/specs/2026-05-21-databricks-converter/
        ├── README.md
        ├── 01-goals-and-scope.md
        ├── 02-platform.md
        ├── 03-architecture.md
        ├── 04-api-surface.md
        ├── 05-ir-spec.md
        ├── 06-extractors.md
        ├── 07-agent.md
        ├── 08-errors-and-observability.md
        ├── 09-testing.md
        └── 10-open-questions.md
```

Notebooks intentionally omitted from v1; will be added in a later phase. Repo packaged as a pip-installable wheel.

## Dependencies (`pyproject.toml`)

```toml
[project]
dependencies = [
    "langchain-core>=0.3",
    "deepagents",
    "openpyxl",
    "python-docx",
    "python-pptx",
    "pymupdf",
    "lxml",
    "beautifulsoup4",
    "markdown-it-py",
    "tenacity",
    "pydantic>=2",
]

[project.optional-dependencies]
databricks = ["databricks-langchain"]
openai     = ["langchain-openai"]
anthropic  = ["langchain-anthropic"]
google     = ["langchain-google-genai"]
all        = ["databricks-langchain", "langchain-openai", "langchain-anthropic", "langchain-google-genai"]
dev        = ["pytest", "pytest-asyncio", "syrupy", "ruff", "mypy"]
```

Install patterns:
- Local dev with Gemini: `pip install -e ".[google,dev]"`
- Local dev with Qwen / OpenAI-compatible: `pip install -e ".[openai,dev]"`
- Databricks production: `pip install converter[databricks]`
- All providers: `pip install converter[all]`
