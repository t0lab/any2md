# AGENTS.md

Project conventions and architecture for **any2md**. Read this first when you open the repo. The user-facing pitch lives in [README.md](README.md).

## What this project does

`any2md` is a pure-Python agent that converts office and web documents (xlsx, docx, pptx, pdf, html, md) to structured markdown for a knowledge base.

It is **not** Databricks-specific. The library runs anywhere Python 3.11+ runs and uses no system binaries — that constraint is what makes it work unmodified on Databricks serverless compute, but Databricks is one supported deployment target, not the goal of the project. When you write or change code, hold the line on the pure-Python constraint so the Databricks path keeps working.

## Pipeline

```
source file (.pptx/.xlsx/.pdf/.html/.docx/.md)
   ↓ extract        src/any2md/extractors/{pptx,xlsx,pdf,html}.py
raw IR + images dict
   ↓ clean          src/any2md/ir_clean.py
cleaned IR
   ↓ chunk          src/any2md/ir_chunk.py  (token-budgeted via tiktoken)
list[IRChunk]
   ↓ caption        src/any2md/agent/captions.py  (async vision LLM, parallel)
   ↓ render         src/any2md/agent/main_agent.py  (deepagents + bare StateBackend)
   ↓ review         src/any2md/agent/subagents/quality_reviewer.py  (in-place edit_file)
markdown
```

Public API:
- `await aconvert(source, options=...)` — async-native, preferred in Databricks notebooks
- `convert(source, options=...)` — sync wrapper, detects a running loop and works in both scripts and notebooks

The agent runs against **bare `StateBackend()`** (in-memory, no disk writes by default). Inputs are seeded via the `files=` payload on `agent.invoke()`; outputs come back through `result["files"][path]["content"]`. Disk dump is opt-in via `ConvertOptions.debug_workspace`.

## Read these first

- [STATE.md](STATE.md) — current pipeline status (done, in progress, pending, known gaps). **Update on every milestone.**
- [docs/superpowers/specs/2026-05-21-databricks-converter/README.md](docs/superpowers/specs/2026-05-21-databricks-converter/README.md) — full design spec, sections 01-11.
- [docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md](docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md) — schema deltas vs spec, cleanup rules per format, chunking contract, **full decisions log**.

## Hard constraints

- **Pure Python only.** No `subprocess`, no system binaries (LibreOffice / Tesseract / Pandoc forbidden), no init scripts. All deps must ship as PyPI wheels. This is what keeps the Databricks-serverless target viable; breaking it breaks deployment.
- **No filesystem writes inside extractor code.** Extractors return `ExtractResult(ir, images, warnings)`; the harness writes.
- **Cross-platform paths.** Dev on Windows (PowerShell), prod often on Linux (Databricks / containers). Use `pathlib.Path`; never hardcode backslashes.

## Conventions

- **Python 3.11+.** Use `from __future__ import annotations`, `TypedDict`, `NotRequired`, `Literal`.
- **Schemas:** all IR types are `TypedDict` in [src/any2md/ir.py](src/any2md/ir.py). Treat as the source of truth for shape; design rationale in §11.1.
- **Bbox unit:** all `BBox` are in `px @ 96 DPI`. Extractors convert from native (pptx/xlsx EMU÷9525, pdf pt×4/3). The `unit` field is dropped during cleanup.
- **Images:** never inline bytes in IR. They live in `images: dict[str, bytes]` keyed by `raw_images/<id>.png`. IR carries only the relative path + dimensions + bbox.
- **Comments:** default to none. Only add when the WHY is non-obvious (hidden constraint, subtle invariant, workaround for a specific bug). Never narrate WHAT.
- **No premature abstraction.** Three similar lines beats a helper that exists for one caller. Add the helper when you have a third use case.
- **Communicate in Vietnamese** unless explicitly switched. The primary user is Vietnamese.
- **No disk writes from the agent path by default.** The library must work as a `.whl` import on Databricks serverless where CWD is read-only. Agent inputs go through `files=` on `agent.invoke()`; outputs come back through `result["files"]`. Disk artifacts are opt-in via `ConvertOptions.debug_workspace` only.
- **Async-first.** `aconvert()` is the canonical entry; `convert()` is a thin sync wrapper that detects a running loop. Never call `asyncio.run()` from library code without the running-loop guard — it blows up inside notebooks.

## Dev workflow

Setup (one time):
```powershell
py -m pip install -e .
py -m pip install -e ".[dev]"
```

Run the pipeline on all samples:
```powershell
py scripts/dump_ir.py     # extract → samples/_ir/<stem>/ir.json + raw_images/
py scripts/audit_ir.py    # cross-check IR vs raw zip / pymupdf → samples/_ir/AUDIT.md
py scripts/clean_ir.py    # cleanup pass → samples/_ir/<stem>/ir.clean.json
py scripts/chunk_ir.py    # chunking → samples/_ir/<stem>/chunks/chunk_NN.json
```

Single file: `py scripts/dump_ir.py samples/specific.pptx`. Custom chunk caps: `py scripts/chunk_ir.py --max-tokens 10000 --max-images 50`.

## Where things live

| Path | Purpose |
|---|---|
| [src/any2md/ir.py](src/any2md/ir.py) | IR `TypedDict` schemas |
| [src/any2md/extractors/](src/any2md/extractors/) | Per-format extractors (`pptx.py`, `xlsx.py`, `pdf.py`, `html.py`) |
| [src/any2md/extractors/_smartart.py](src/any2md/extractors/_smartart.py) | Shared SmartArt parsing (pptx + xlsx) |
| [src/any2md/ir_clean.py](src/any2md/ir_clean.py) | Post-extraction cleanup (strips redundancy) |
| [src/any2md/ir_chunk.py](src/any2md/ir_chunk.py) | Token-budgeted chunking |
| [samples/](samples/) | Source fixtures (pptx / xlsx / pdf / html) |
| [samples/_ir/](samples/_ir/) | Per-fixture IR + cleaned IR + chunks + extracted images |
| [scripts/](scripts/) | Pipeline driver scripts |
| [docs/superpowers/specs/2026-05-21-databricks-converter/](docs/superpowers/specs/2026-05-21-databricks-converter/) | Design spec (numbered 01-11) |
| [STATE.md](STATE.md) | Living status snapshot (update on every milestone) |

## Decisions to respect

Full log with rationale: [§11.2 decisions log](docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md#112-decisions-log). Highlights:

- **Agent backend = bare `StateBackend()`** (deepagents 0.6.x). `FilesystemBackend` is officially CLI/CI only — using it for an importable library breaks Databricks serverless. Seed inputs via `agent.invoke({"files": {...}})`; read output via `result["files"][path]["content"]`.
- **Agent compiled once, cached by `(model_id, review_flag, caption_language, primary_language)`**. Multi-chunk loops reuse the same `CompiledStateGraph`; per-invoke isolation comes from StateBackend.
- **Prompts use XML-grouped sections** (`<reading_order>`, `<task>`, `<image_block_format>`, `<diagram_format>`, `<language>`, `<guardrails>`, `<procedure>`), positive instructions, and identity repeated at start AND end. Stale path references (e.g. `/workspace/raw_images/`, `draft.md`) must not creep back in — the in-memory backend doesn't seed image bytes and `draft.md` is retired.
- **Reading order = spatial, not array index** for pptx/pdf. The IR's `order` field is the raw extraction sequence (XML parse / page object list), NOT reading order. Designers compose 2D layouts: card stacks (header / body / footer), 2x2 grids, multi-column flows — agent renderer must group visually-related shapes by `bbox` and walk top-down then left-right. `bbox` is preserved in cleaned IR specifically for this — do not strip it from cleanup. html (`order` == DOM order) and xlsx (cell coordinate) keep linear walks.
- **Cleanup is a separate pass** ([ir_clean.py](src/any2md/ir_clean.py)), not inlined into extractors. Raw IR stays maximally verbose for debugging / auditing.
- **Chunking uses `tiktoken.cl100k_base`** as a budget gate. Not Claude's tokenizer — within ~10-15% for our content; sufficient as a gate.
- **Oversize units emit alone** with `truncated=True`; no in-unit splitting in phase 1.
- **`TableShape.rows` dropped during cleanup**; `rows_rich` is the source of truth (also carries `rowspan` / `colspan`).
- **`is_title` removed from `TextShape`** — placeholder-type detection was buggy + useless for free-form decks.

## Gotchas

- **`pymupdf` stderr noise:** prints "Consider using pymupdf_layout..." on every PDF open. Harmless. Silence with `pymupdf.TOOLS.mupdf_display_errors(False)` if it gets in the way.
- **`python-pptx` can't infer `slide.title`** if the deck uses free-form text boxes (no placeholder layout). The fixture `logic_tree_lending.pptx` is such a deck — all 14 slides have `title=None`. Not a bug; agent layer will apply a heuristic.
- **`openpyxl` skips chartsheet tabs** through `wb.worksheets`. Known gap.
- **HTML remote-image fetch** needs outbound HTTPS; fails gracefully (`fetch_status: "failed"`) on serverless workspaces with egress restrictions.
- **pptx images may have leaked `alt_text`** containing the authoring environment's filesystem path (e.g. `/home/.../image.png`). Cleanup strips these.
- **`asyncio.run()` from a notebook cell** raises `RuntimeError: asyncio.run() cannot be called from a running event loop`. The sync `convert()` wrapper guards against this by detecting a running loop and dispatching to a `ThreadPoolExecutor`. Never reintroduce a bare `asyncio.run(...)` in library code.
- **`debug_workspace` resolves relative paths under `tempfile.gettempdir()`**. If you pass `Path("workspace")`, it lands in `%TEMP%/workspace/<stem>/`, not in CWD. Use an absolute path (or a UC Volume on Databricks) for predictable persistence.

## When you finish a milestone

Update [STATE.md](STATE.md):
- Bump `Last updated`.
- Move items from "Pending" → "Completed".
- Add a one-line entry to "Recent decisions (rolling)" if a non-obvious call was made.
- For canonical design-side decisions, also append to [§11.2 decisions log](docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md#112-decisions-log).

Do not auto-create planning / progress / analysis docs unless asked. STATE.md is the one living doc; everything else in [docs/](docs/) is design spec.
