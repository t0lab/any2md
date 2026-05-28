# Project State

Living status of **any2md** (document → markdown agent). Update on every meaningful change. Design / schema / rules live in [`docs/superpowers/specs/2026-05-21-databricks-converter/`](docs/superpowers/specs/2026-05-21-databricks-converter/) (the spec dir keeps its original date-stamped name) and remain authoritative; this file is the "where are we" snapshot. User-facing pitch in [README.md](README.md).

- **Last updated:** 2026-05-27
- **Active phase:** Agent backend swapped to **bare `StateBackend()`** (in-memory, no disk writes by default) — required for `.whl` import on Databricks serverless where CWD is read-only. `convert()` now exposes both `aconvert()` (async-native, preferred in notebooks) and `convert()` (sync wrapper that detects a running loop and dispatches to a worker thread). On-disk artifacts moved behind `ConvertOptions.debug_workspace` opt-in. All three system prompts (captioner, main renderer, quality reviewer) rewritten via the prompt-engineering pipeline with XML-grouped sections, positive instructions, and primacy/recency identity restatement. Pyproject pins aligned to LC 1.4 / deepagents 0.6 stack.

## Pipeline (current)

```
source file (xlsx/pptx/pdf/html)
   ↓ extract_and_clean()         src/any2md/pipeline.py
cleaned IR + images dict
   ↓ caption_pass() (async)      src/any2md/agent/captions.py
captions: {image_id: text}     (deduped per image_id — see image_refs.py)
   ↓ chunk_ir()                  src/any2md/ir_chunk.py
list[IRChunk]                  (1 chunk when whole IR fits in max_chunk_tokens)
   ↓ arender_chunk() per chunk   src/any2md/agent/main_agent.py
   │     in-memory seed: files={IR_PATH: …, CAPTIONS_PATH: …, TAIL_PATH: …}
   │     create_deep_agent(backend=StateBackend())   # ← bare, no disk
   │     agent built once at module load, cached by (model, options) key
   │
   ├── main agent  reads /workspace/ir.json + captions.json
   │               writes /workspace/final.md ONCE
   │
   └── task("quality-reviewer") subagent  [only when enable_quality_review]
                   reads final.md + ir.json
                   applies SMALL targeted fixes IN PLACE via edit_file
                   NEVER calls write_file (avoids stream truncation on long outputs)
   ↓
result["files"][FINAL_PATH]["content"]  ← read back from returned state
join chunk markdowns ("\n\n") → final markdown
```

Top-level entry (two flavors):
- `await aconvert(source, options=...)` — async-native, use in notebooks.
- `convert(source, options=...)` — sync wrapper that detects a running
  loop and dispatches to a worker thread when needed.

Multi-chunk loop lives in [convert.py](src/any2md/convert.py): chunks
the IR, calls `arender_chunk()` per chunk, threads `previous_tail`
(~1000 chars of prior chunk's markdown) so the agent continues numbered
lists / heading hierarchy without duplication.

**No filesystem writes by default.** `ConvertOptions.debug_workspace`
(opt-in) mirrors the agent's virtual state to disk for inspection;
relative paths resolve under `tempfile.gettempdir()`, absolute paths
(e.g. UC Volumes) are honored as-is.

## Completed

- **Extractors (6/6):**
  - [pptx](src/any2md/extractors/pptx.py) — text, table (rich runs + rowspan/colspan), image, chart, SmartArt, connector, group, comments
  - [xlsx](src/any2md/extractors/xlsx.py) — multi-table clustering, charts, images (full anchor), SmartArt, drawing shapes, cell hyperlinks/comments
  - [pdf](src/any2md/extractors/pdf.py) — text blocks w/ bbox, images w/ placement bbox, tables, links (URI/goto/launch), TOC, metadata
  - [html](src/any2md/extractors/html.py) — headings, paragraphs, nested lists, table, code, blockquote, figure+caption, hr, dl, br
  - [docx](src/any2md/extractors/docx.py) — body-XML walk (preserves paragraph/table interleaving), headings (Title/Subtitle/Heading N), runs (bold/italic/underline/hyperlink in order via `iter_inner_content`), lists (direct + style-based numPr → bullet/numbered + level), tables (merged-cell dedup), inline images (normalized PNG + neighbors), SmartArt diagrams (`dgm:relIds` → node tree via shared [_smartart.py](src/any2md/extractors/_smartart.py)), Quote→blockquote, Code styles→code, OMML equations→`[Equation: …]`, floating textboxes→textbox blocks
  - [markdown](src/any2md/extractors/markdown.py) — `markdown-it-py` (CommonMark + table + strikethrough rules; linkify left off to avoid the optional `linkify-it-py` dep) walked via `SyntaxTreeNode`; YAML frontmatter (lightweight key:value, no pyyaml dep) → `ir.frontmatter`; headings, inline runs (bold/italic/code/hyperlink — strikethrough text kept, no TextRun field), nested lists→flat paragraphs w/ list_kind+level, GFM tables, fenced code w/ language, blockquote (nested blocks), `hr`→divider, images (same data-URI/remote/local fetch policy as HTML), inline+block raw HTML preserved
- **Unit standardization** — all bbox in `px @ 96 DPI` (pptx/xlsx EMU/9525, pdf pt × 4/3)
- **IR cleanup pass** ([`ir_clean.py`](src/any2md/ir_clean.py)) — 21.4% size reduction across samples
- **IR chunking** ([`ir_chunk.py`](src/any2md/ir_chunk.py)) — token-based (default 30K tokens / 80 images per chunk)
- **Sample fixture audit** — all 5 samples extract cleanly with 0 warnings; cross-check report at [samples/_ir/AUDIT.md](samples/_ir/AUDIT.md)
- **Databricks parity verified** — pure-Python deps only (`openpyxl`, `python-pptx`, `pymupdf`, `lxml`, `bs4`, `Pillow`, `tiktoken`), no subprocess, no system binaries — runnable on serverless
- **Top-level `convert()` API** ([convert.py](src/any2md/convert.py)) — single entry: `convert(source, options) -> ConvertResult`. Orchestrates `extract_and_clean` → caption pre-pass → `render_chunk` → final markdown.
- **Pipeline glue** ([pipeline.py](src/any2md/pipeline.py)) — `extract_and_clean(source) -> CleanResult` routes by extension and runs `clean_ir` automatically.
- **Caption pre-pass** ([agent/captions.py](src/any2md/agent/captions.py), [image_refs.py](src/any2md/agent/image_refs.py)) — async parallel image captioning via `vision_llm.ainvoke()` with LangChain unified vision format; concurrency cap via `asyncio.Semaphore`, RPM cap via token bucket; 3 retries with exponential backoff; falls back to `alt_text` on persistent failure.
- **Quality reviewer subagent** ([agent/subagents/quality_reviewer.py](src/any2md/agent/subagents/quality_reviewer.py)) — wired via `deepagents` `subagents=[…]`; main agent invokes it through the built-in `task` tool. Reviewer reads `/workspace/ir.json` + `/workspace/final.md` and applies SMALL targeted fixes IN PLACE via `edit_file` — it never calls `write_file` (rewriting a 10KB+ file via streaming output was causing mid-document truncation on Qwen3.6). Verifies completeness, ordering, no-duplication, no-phantom-sections; never re-captions images.
- **Captioner Mode A vs Mode B** ([agent/captions.py](src/any2md/agent/captions.py)) — vision prompt now classifies the image first: NUMERIC DATA TABLE → 1-2 sentence summary (Mode A); EVERYTHING ELSE → full verbatim extraction transcribing all visible text, chart axes/values, diagram nodes/connectors, screenshot UI structure (Mode B). Replaces the prior summary-only behavior that was dropping detail on letters / forms / flowcharts.
- **Multi-chunk loop** ([convert.py](src/any2md/convert.py)) — `convert()` now calls `chunk_ir()` and loops `render_chunk` per chunk. Per-chunk workspace at `workspace/<stem>/chunk_NN/` (or `workspace/<stem>/` for single-chunk case to preserve old layout). Threads last 1000 chars of each chunk's markdown as `previous_tail.md` so the agent continues numbered lists / heading hierarchy across boundaries. Images + captions partitioned per chunk via `collect_image_refs(chunk_ir)`.
- **Image format normalization** ([extractors/_image_utils.py](src/any2md/extractors/_image_utils.py)) — shared `normalize_to_png` / `is_svg` / `image_dimensions`. All extractors funnel image bytes through normalize before storing, so `captions.py` can safely send `data:image/png;base64,...` regardless of original format (JPG/GIF/WEBP/BMP/TIFF → PIL re-encode; SVG → optional `cairosvg` rasterize, else captioner detects and falls back to `alt_text`). Fixes the xlsx case where blob was kept raw but stored under `.png`.
- **Caption dedup** ([image_refs.py](src/any2md/agent/image_refs.py)) — `collect_image_refs` now deduplicates by `image_id`, keeping the first occurrence. Defensive against a single xref placed at multiple rects on one PDF page (avoids wasted vision-API calls).
- **Agent backend: bare `StateBackend()`** ([agent/main_agent.py](src/any2md/agent/main_agent.py), [tools.py](src/any2md/agent/tools.py)) — pure in-memory state, thread-isolated per invoke. Inputs seeded via `agent.invoke({"messages":[…], "files": build_initial_files(ir, captions, previous_tail)})`; output read back from `result["files"][FINAL_PATH]["content"]`. No disk writes unless `ConvertOptions.debug_workspace` is set. Agent compiled once at module load and cached by `(model_id, review_flag, caption_language, primary_language)` so multi-chunk loops reuse it.
- **Dual entrypoint `aconvert()` + `convert()`** ([convert.py](src/any2md/convert.py)) — `aconvert()` is async-native (preferred in Databricks notebooks / FastAPI / any code with a running loop). `convert()` is a sync wrapper that detects a running loop and dispatches the coroutine to a worker thread so it works equally well in plain scripts and inside notebooks. Agent imports are deferred into the body so users on bare wheel (without `[agent]` extras) get an actionable `ImportError` instead of a cryptic `ModuleNotFoundError: deepagents`.
- **Prompts refactored via prompt-engineering pipeline** ([prompts.py](src/any2md/agent/prompts.py), [captions.py](src/any2md/agent/captions.py), [subagents/quality_reviewer.py](src/any2md/agent/subagents/quality_reviewer.py)) — all three prompts restructured with XML-tagged sections (`<task>`, `<image_block_format>`, `<diagram_format>`, `<language>`, `<guardrails>`, `<procedure>`), positive instructions in place of negative-only constraints, an explicit count rule for image blocks, worked examples for the tricky cases (mixed-language diagram extraction, edit_file deletion of trailing duplicates), and identity statement repeated at start AND end of the main prompt (primacy/recency). Quality reviewer output format hard-pinned to a single line: `Reviewed clean.` or `Reviewed: N edits applied: <reasons>`.
- **`.whl`-on-Databricks compat** ([pyproject.toml](pyproject.toml), [convert.py](src/any2md/convert.py)) — pins aligned to LC 1.4 / deepagents 0.6 (the LC ecosystem moved from 0.x to 1.x in late 2025; deepagents 0.6.3 requires `langchain-core>=1.4`). `databricks-langchain` excluded from `all` because DBR ships it. No relative-CWD writes — `debug_workspace` defaults to `None`, relative paths resolve under `tempfile.gettempdir()`. Verified: `convert()` succeeds inside a running asyncio loop (notebook simulation); `workspace/` is NOT created when `debug_workspace` is not set.
- **LLM wiring** ([llm.py](src/any2md/llm.py)) — `build_llm()` supports `databricks` / `openai` / `anthropic` / `google` / `custom`; `litellm_text_model()` helper for OpenAI-compatible proxies (LiteLLM, vLLM, DashScope) reads `LITELLM_MODEL` / `LITELLM_BASE_URL` / `LITELLM_API_KEY` from env (vision enabled — same model handles text + image via the proxy).
- **Options dataclasses** ([options.py](src/any2md/options.py)) — `ModelConfig`, `ConvertOptions`, `ConvertResult` per spec §04.
- **`.env` scaffold** — [.env.example](.env.example) template + auto-load via `python-dotenv` in [scripts/run_agent.py](scripts/run_agent.py); `workspace/` gitignored.
- **LangSmith tracing** — opt-in via `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` + `LANGSMITH_PROJECT` in `.env`. `scripts/run_agent.py` prints the project URL when enabled. Each `convert()` run produces a nested trace tree (main agent → tool calls → subagent invocations) with token counts + latency.
- **Project rebrand** — `pyproject.toml.name = "any2md"`; [README.md](README.md) added; [AGENTS.md](AGENTS.md) + spec headers reframed: any2md is general-purpose, Databricks serverless is one supported deployment target (not the project's purpose). Package directory renamed `src/converter/` → `src/any2md/` on 2026-05-26; all imports updated (`from converter.*` → `from any2md.*`).
- **Smoke tests passed (3 formats, full pipeline)** — `py scripts/run_agent.py <fixture>` against `Qwen3.6-35B-A3B` via LiteLLM proxy:

  | Fixture | Tokens | Images | Captions | Time (review ON) | Time (review OFF) | Output |
  |---|---|---|---|---|---|---|
  | `test.html` | 1.9K | 0 | — | 37.0s | 13.8s | 2.9 KB |
  | `logic_tree_lending.xlsx` | 3.0K | 2 | 2 | 101.8s | — | 5.3 KB |
  | `Naac_appLetter.pdf` | 1.8K | 14 IR refs → 7 unique | 7 | 199.0s | — | 2.3 KB |
  | `logic_tree_lending.docx` | 3.7K | 4 | 4 | 310.3s (review+clean ON) | — | 5.5 KB |

  Verified: tables render as GFM, SmartArt → nested bullet list, image captions inline at correct order position, vi+en mixed text preserved verbatim, caption auto-language picks the right one per surrounding context, `final.md` differs from `draft.md` by ≤1 char (reviewer normalizes, doesn't rewrite). Qwen3.6 vision via the LiteLLM proxy successfully captioned scanned letterhead images (names/dates/organizations read verbatim).

## In progress

_None — between phases._

## Pending (ordered roughly by priority)

1. **Wheel build + clean-venv smoke install** — `py -m build --wheel` then `pip install dist/any2md-0.0.1-py3-none-any.whl[agent,databricks]` inside a fresh venv; verify `from any2md import convert` works and `convert(samples/test.html)` does not create a `workspace/` dir under the install CWD. Deferred from the 2026-05-26 refactor pass.
2. **Multi-chunk merge quality (partially fixed)** — all real samples fit one chunk at the 20K default, so the multi-chunk path stays under-exercised; force it with `run_agent.py … --max-tokens=1500 --debug`. **(a) duplicate H1 title per chunk — FIXED**: the cleaner now runs a "Rule 0 continuation check" (reads `previous_tail.md`; if present, skips title-synthesis + heading-rebaseline), and [convert.py](src/any2md/convert.py) runs a deterministic `collapse_duplicate_h1` over the joined doc as a belt-and-suspenders. Verified on the 3-chunk docx: chunks 1-2 emit no H1, joined doc has exactly one title, heading levels stay consistent (so **(c) heading-level drift** is largely addressed by the same guard). Still open: **(b)** blocks/captions can split across a seam (chunk boundaries fall on raw token budget, not section boundaries — prefer splitting at top-level headings); **(d)** the last small chunk occasionally truncates (render-completeness; non-deterministic — recurred once, not on the verifying run). Also still: `logic_tree_lending.pptx` (15.9K, 1 chunk @ 20K) hits per-call timeouts on Qwen3.6.
3. **docx / markdown `expected.md` + sample fixtures** — `logic_tree_lending.docx` runs the full pipeline (actual in [samples/_md_actual](samples/_md_actual/logic_tree_lending.docx.actual.md)); markdown extractor verified on a synthetic temp doc but `samples/` has no `.md` fixture and neither has a hand-authored `samples/_md/*.expected.md` to diff against
4. **Tests** — pytest pyramid per [09-testing.md](docs/superpowers/specs/2026-05-21-databricks-converter/09-testing.md)

## Known gaps (extractors, low priority)

| Area | Status |
|---|---|
| pptx bullet inheritance from layout/master | Only inline `<a:buChar>` / `<a:buAutoNum>` detected |
| pptx slide-level title heuristic | `slide.title` empty for free-form decks (no placeholder layout) |
| xlsx number formats | Raw `.value` only; `cell.number_format` not applied |
| xlsx chart sheets | `chartsheet` tabs skipped — `wb.worksheets` doesn't include them |
| xlsx `anchor_range` for `oneCellAnchor` | Only `twoCellAnchor` produces a range today |
| Chart `axis_labels` | Schema field present, always `{}` |
| PDF form fields | `page.widgets()` not extracted |
| HTML bare `<div>` / `<section>` / `<article>` text | Lost unless wrapped in `<p>` |
| docx headers / footers / footnotes | Skipped in v1 (spec §6.2) |
| docx track changes / comments | Skipped |
| docx VML textboxes (`<w:pict>`) | Only DrawingML `<w:drawing>` textboxes extracted |
| docx vertical cell merges | Repeat text down the column (horizontal merges deduped) |
| docx content controls (`<w:sdt>`) | Body walk skips `sdt`-wrapped content |

## Sample fixtures

| Sample | Format | Raw IR | Cleaned | Token count | Chunks @ default |
|---|---|---|---|---|---|
| `logic_tree_lending.pptx` | pptx | 165.7 KB | 130.4 KB | 15,939 | 1 |
| `logic_tree_lending.docx` | docx | 16.2 KB | 16.0 KB | 3,678 | 1 |
| `c4611_sample_explain.pdf` | pdf | 29.2 KB | 20.3 KB | 4,422 | 1 |
| `Naac_appLetter.pdf` | pdf | 11.7 KB | 7.8 KB | 1,783 | 1 |
| `logic_tree_lending.xlsx` | xlsx | 18.5 KB | 16.6 KB | 2,987 | 1 |
| `test.html` | html | 9.5 KB | 9.4 KB | 1,866 | 1 |

All samples currently fit in a single 30K-token chunk after cleanup.

## How to reproduce the pipeline

```powershell
py scripts/dump_ir.py        # 1. extract raw IR + images
py scripts/audit_ir.py       # 2. cross-check IR vs raw zip / pymupdf
py scripts/clean_ir.py       # 3. emit ir.clean.json
py scripts/chunk_ir.py       # 4. emit chunks/chunk_NN.json
```

Outputs land under `samples/_ir/<stem>.<fmt>/`. CLI flags on chunker: `--max-tokens N --max-images N`.

## Recent decisions (rolling — full log in [§11.2](docs/superpowers/specs/2026-05-21-databricks-converter/11-schema-and-rules.md#112-decisions-log))

- **2026-05-27** — **Multi-chunk duplicate-title defect fixed via continuation-aware cleaner + deterministic H1 collapse** ([cleaner.py](src/any2md/agent/subagents/cleaner.py), [postprocess.py](src/any2md/agent/postprocess.py), [convert.py](src/any2md/convert.py)). Chunks render + clean independently and join via `"\n\n"`, so the cleaner's title-synthesis was firing on every fragment → multiple `# …` titles in the merged doc. Fix: the cleaner reads the already-seeded `previous_tail.md` (present only on continuation chunks) as "Rule 0" and, when set, skips title-synthesis + heading-rebaseline entirely; `convert.py` then runs `collapse_duplicate_h1` (keep first `# `, demote the rest, skip fenced code) over the joined markdown as a deterministic safety net. Verified on a forced 3-chunk docx: continuation chunks emit no H1, joined doc has exactly one title, heading levels consistent, §7 complete. Added `--max-tokens=` to [run_agent.py](scripts/run_agent.py) to force multi-chunk on small fixtures. Remaining multi-chunk gaps (section-boundary splitting, occasional last-chunk truncation) tracked in pending item 2.
- **2026-05-27** — **markdown extractor landed — extractors now 6/6** ([extractors/markdown.py](src/any2md/extractors/markdown.py)). `markdown-it-py` parsed via `SyntaxTreeNode` (nested tree beats walking the flat token stream). Preset is `MarkdownIt("commonmark").enable(["table","strikethrough"])` — NOT the `gfm-like` preset, which turns on `linkify` and hard-requires the optional `linkify-it-py` package (raises `ModuleNotFoundError` at parse time otherwise). Frontmatter is split off before parsing (else `---` becomes a thematic break) and parsed with a minimal key:value reader rather than adding a pyyaml dep. Reuses the shared `Block` schema + the HTML image-fetch policy (data-URI / remote-if-enabled / local-relative); registered in [pipeline.py](src/any2md/pipeline.py) + [dump_ir.py](scripts/dump_ir.py); `_clean_markdown` and the generalized `_collect_blocks(ir, container_kind)` (shared with docx, also fixed the latent `figure`/wrapper bug) round out the wiring. ir_chunk already routed `markdown` through the blocks packer.
- **2026-05-27** — **docx SmartArt now extracted (was a silent gap)**. `logic_tree_lending.docx` has 5 `<w:drawing>` objects — 4 pictures + 1 SmartArt (`<a:graphicData uri=".../diagram">` → `<dgm:relIds>` → `word/diagrams/data2.xml`). The first cut only handled `<a:blip>`, so the hierarchy diagram in §2 vanished (heading + caption survived, diagram body gone). Fixed by reusing the shared [_smartart.py](src/any2md/extractors/_smartart.py) the pptx path already uses: preload `word/diagrams/{data,layout}*.xml` + `word/_rels/document.xml.rels` from the package zip, resolve `r:dm`/`r:lo` against the doc rels, parse the node tree, emit a `{type: "smartart", layout_kind, nodes}` block (no new schema — renderer's `<diagram_format>` already turns it into nested bullets; chunker treats it as a 0-image block). All 6 `<a:t>` fragments captured, layout_kind=hierarchy. The dgm + math namespaces are referenced by raw URI (not in python-docx's `nsmap`).
- **2026-05-27** — **`**[Image - …]**` markers are an internal scaffold, stripped from final output** ([agent/postprocess.py](src/any2md/agent/postprocess.py)). The marker line lets the agent + quality-reviewer verify completeness (N image refs in IR → N markers emitted), but it's noise in the delivered markdown — the hand-authored `samples/_md/*.expected.md` never use it; they weave the caption/transcription straight into prose + lists under the surrounding heading. New `strip_image_markers` pass deletes every marker LINE (keeping the caption body) as the last image pass, after `strip_decorative_image_blocks` + `dedupe_adjacent_image_markers` which still key off the marker. Side effect: orphan markers (e.g. a cover banner whose caption the renderer dropped as redundant with the H1/metrics) disappear cleanly. Applies to ALL formats — the stale pdf/xlsx/html `*.actual.md` will shed their markers on next re-run. Verified on `logic_tree_lending.docx`: 4 markers → 0, all 3 chart/flowchart captions remain as inline content.
- **2026-05-27** — **Caption pre-pass was silently no-op for docx** ([agent/image_refs.py](src/any2md/agent/image_refs.py)). `collect_image_refs` had no `docx` branch, so `caption_pass` got `[]` and the renderer fell back to alt_text (raw filenames like `cover_image.png`) for all 4 images in `logic_tree_lending.docx`. Added `_collect_docx` (recurses into textbox/blockquote nests, pulls `context_text` from each image's `neighbors.before/after_text`). Also fixed a latent twin bug in `_collect_html`: the `type=="image"` branch passed the wrapper block instead of `blk["image"]`, yielding empty `relative_path`/`id` — never tripped because the only HTML fixture has no images. After the fix `logic_tree_lending.docx` captions all 4 images (cover banner, decision flowchart with Yes/No edges, doughnut + bar charts with full data values).
- **2026-05-27** — **docx extractor landed** ([extractors/docx.py](src/any2md/extractors/docx.py)). Iterates `doc.element.body` at the XML level (wrapping `CT_P`/`CT_Tbl` back into `Paragraph`/`Table`) because `doc.paragraphs` and `doc.tables` are separate lists that lose interleaving order. Run-level fidelity uses `Paragraph.iter_inner_content()` (python-docx ≥1.1) so hyperlinks keep their reading-order position — `paragraph.runs` omits hyperlink runs entirely. List detection checks direct `pPr/numPr` AND the paragraph style's `numPr` (named styles like "List Bullet"/"List Number" carry numbering on the style, not the paragraph); numId→numFmt resolved from the numbering part to classify bullet vs numbered. OMML equations searched via the raw math namespace URI (`m:` isn't in python-docx's `nsmap`, so `qn("m:…")` would KeyError) and emitted as `[Equation: …]` placeholders. `_clean_docx` mirrors `_clean_html` (drops whitespace-only runs, recurses into textbox/blockquote nests). Verified end-to-end on a synthetic fixture covering all branches; registered in [pipeline.py](src/any2md/pipeline.py) + [scripts/dump_ir.py](scripts/dump_ir.py).
- **2026-05-26** — **Agent backend switched from `CompositeBackend(+FilesystemBackend)` to bare `StateBackend()`**. The old wiring mounted a real disk directory at `/workspace/` via `FilesystemBackend(virtual_mode=True)`. Research of `deepagents` 0.6.3 source confirmed this misuses `virtual_mode` (it's a CompositeBackend path-normalization flag, NOT an in-memory mode) and `FilesystemBackend` carries an explicit security warning recommending CLI/CI only. Pattern fixed by seeding inputs via the `files=` payload on `invoke()` and reading outputs back from `result["files"][path]["content"]`. Side effect: removes the only hard blocker for `.whl` import on Databricks serverless (CWD is read-only there).
- **2026-05-26** — **`convert()` split into `aconvert()` (async-native) + sync wrapper**. `asyncio.run()` inside the sync `convert()` raises `RuntimeError` when called from a notebook cell whose kernel already has an event loop running. New wrapper detects a running loop and dispatches the coroutine to a `ThreadPoolExecutor` worker (which creates its own fresh loop). Notebook users get a recommended path: `await aconvert(...)`. Local script users keep the original sync API.
- **2026-05-26** — **Agent imports deferred into `aconvert()` body**, not at module top. Bare-wheel users (without `[agent]` extras) now get `ImportError: any2md.convert needs the agent extras. Install with: pip install 'any2md[agent]'` at call time, instead of an opaque `ModuleNotFoundError: deepagents` at `import any2md.convert`. Trade-off accepted: the error surfaces only when `convert()` is actually called, but that's also when it's actionable.
- **2026-05-26** — **`debug_workspace` opt-in, relative paths resolve under `tempfile.gettempdir()`**. Default `None` means zero disk I/O — required for Databricks notebook CWD which is `/Workspace/Users/<email>/` and read-only. When set as relative path, the lib reroutes to tempdir so portable defaults stay safe. Absolute paths (UC Volumes, dev workstation) are honored as-is. Returned in `result.metadata["debug_workspace"]` when populated.
- **2026-05-26** — **Reading order is spatial, not array index, for pptx/pdf.** The first prompt rewrite told the agent "walk in ascending `order`", which was wrong: pptx and pdf are 2D layouts with no inherent reading sequence. Designers use card stacks (header / body / footer), 2x2 grids, multi-column flows — array-order walks scramble these into garbage. Fix: new `<reading_order>` section in the main prompt instructs the agent to walk by `bbox` (px @ 96 DPI) for pptx/pdf — group visually-related shapes, then top-down + left-to-right within and between groups. html and xlsx keep linear walks (DOM order / cell coordinate). Quality reviewer gained a parallel "Group B - Spatial Reading Order" verification step that reorders via `edit_file` when the main agent walked by array order. This is the design reason `bbox` is preserved in cleaned IR rather than stripped.
- **2026-05-26** — **All three system prompts rewritten via the prompt-engineering pipeline** ([captioner](src/any2md/agent/captions.py), [main renderer](src/any2md/agent/prompts.py), [quality reviewer](src/any2md/agent/subagents/quality_reviewer.py)). Common changes: XML-tagged section grouping, positive instructions in place of negative-only constraints ("Render EXACTLY N image blocks where N = #image refs in IR" beats "do NOT loop and re-emit"), 1-2 worked examples per prompt, identity statement repeated at start AND end of the main prompt (primacy/recency). Captioner gained a mixed-vi+en flowchart example; reviewer's output format pinned to a single-line summary so downstream parsing is trivial. Stale references to `/workspace/raw_images/*.png` and `draft.md` removed (the in-memory backend doesn't seed image bytes, and `draft.md` was retired in the 2026-05-25 reviewer rewrite). No legacy-prompt fallback — forward-only.
- **2026-05-26** — **Pyproject pins aligned to LC 1.4 / deepagents 0.6**. The earlier `langchain-core>=0.3,<0.4` cap predated the LangChain 0.x→1.x migration in late 2025. `deepagents 0.6.3` requires `langchain-core>=1.4,<2`, so the cap had to move. Provider extras (`langchain-openai`, `langchain-anthropic`, `langchain-google-genai`) bumped to their 1.x/4.x equivalents. `databricks-langchain` removed from `all` because DBR ships it pre-installed and a second install can downgrade the runtime's curated version. Description string updated: "No subprocess, no system binaries; installs from manylinux wheels" replaces the inaccurate "Pure-Python" claim (pymupdf is a C extension that *ships* as a manylinux wheel).
- **2026-05-26** — **Package directory renamed** `src/converter/` → `src/any2md/`. The PyPI name was already `any2md` since 2026-05-22; only the on-disk import path lagged. Renamed in one pass: 10 package files + 5 scripts updated from `from converter.*` to `from any2md.*`; spec doc `2026-05-21-databricks-converter/` directory name preserved to keep deep links stable (the spec doesn't share the package's name). Editable install reseated via `pip install -e .`.
- **2026-05-26** — **Image format normalization centralized** in [extractors/_image_utils.py](src/any2md/extractors/_image_utils.py). xlsx was the offender: it stored raw blob (could be JPG/GIF/WEBP/EMF) under a `.png` path while captioner hardcoded MIME `image/png`. Fix funnels ALL extractor image bytes through a shared `normalize_to_png` (PIL re-encode) + `is_svg` detection + optional `cairosvg` for SVG. captions.py short-circuits raw SVG to `alt_text` so we don't burn 3 vision-API retries waiting to fail.
- **2026-05-26** — **Caption dedup at collection time**, not on the metric side. `collect_image_refs` now drops duplicates by `image_id` keeping the first occurrence. Earlier behavior was "correct but wasteful": same xref placed at multiple rects on one PDF page would produce N refs and N caption attempts that overwrote each other. STATE.md's "14 → 7" note was actually conflating `page_image` + `images_on_page` counts, not duplicates — but the dedup is still useful as defense against future fixtures that exhibit the real case.
- **2026-05-26** — **Multi-chunk loop** lives in [convert.py](src/any2md/convert.py), not in `render_chunk`. The agent stays single-chunk per invocation (one workspace, one final.md); `convert()` owns chunking, per-chunk workspace dirs, image/caption partitioning, and `previous_tail` threading. Chunks joined by `"\n\n"`. Per-chunk workspaces under `workspace/<stem>/chunk_NN/` only when `len(chunks) > 1`; single-chunk keeps the old `workspace/<stem>/` layout so existing debugging muscle memory stays valid.
- **2026-05-25** — **Quality reviewer rewritten as in-place editor**. Old reviewer read `draft.md` and wrote a fresh `final.md` via `write_file(full_content)`. On a 10KB+ PDF render, streaming output truncated mid-document and dropped pages 4-7. New design: main agent writes `final.md` directly (skipping `draft.md`), reviewer only applies targeted `edit_file` calls (find/replace, never full rewrite). Reviewer prompt explicitly forbids `write_file` on final.md.
- **2026-05-25** — **Captioner split into Mode A / Mode B**. Old prompt produced 1-2 sentence summaries unconditionally, which destroyed detail on letters/forms/diagrams. New prompt classifies: NUMERIC DATA TABLE → summary (Mode A, ranges + trends); everything else → full verbatim transcription (Mode B). "Numeric data table" = grid dominated by numeric cells, no surrounding chart/diagram/screenshot/logo.
- **2026-05-25** — **Anti-loop CONSTRAINT in main prompt**: "Render EACH IR block EXACTLY ONCE. When you reach the last IR block, STOP." Qwen3.6 has a tendency to re-emit the trailing 1-3 sections at end-of-document; counting-based phrasing (`N image blocks in IR → N markers in output`) gives the reviewer a verifiable check.
- **2026-05-22** — Project rebranded to **`any2md`** (was framed as "Databricks document converter"). Pure-Python constraint kept as hard rule precisely because it makes the Databricks-serverless path viable, but the project no longer presents itself as Databricks-specific. Spec dir name (`2026-05-21-databricks-converter/`) preserved to keep deep links stable; package directory rename (`src/any2md/` → `src/any2md/`) deferred.
- **2026-05-22** — **Two main-agent prompt variants** (`MAIN_PROMPT_WITH_REVIEW`, `MAIN_PROMPT_NO_REVIEW`) instead of one prompt that always mentions the reviewer. Earlier test ran reviewer-off in 117s because the prompt told the agent to call `task(reviewer)` then "stop after reviewer writes final.md" — with no reviewer registered, the agent fell into an extra rewrite pass. With branched prompts, no-review on `test.html` drops to 13.8s.
- **2026-05-22** — **CompositeBackend with `FilesystemBackend(root_dir=workspace, virtual_mode=True)`** mounted at `/workspace/`, default StateBackend for the rest. `virtual_mode=True` is required so CompositeBackend route prefixes get stripped correctly; without it, absolute paths bypass `root_dir`. On-disk workspace at `./workspace/<stem>/` keeps artifacts inspectable between runs.
- **2026-05-22** — **`streaming=True` on `ChatOpenAI`** (any2md → LiteLLM via langchain-openai). Cloudflare-fronted proxies enforce a 120s origin-response timeout; small open-source models (Qwen3.6-35B-A3B in our case) easily exceed that for long generations. Streaming keeps bytes flowing so Cloudflare's 524 doesn't fire.
- **2026-05-22** — Agent base uses **pure FS via `FilesystemMiddleware`** (built into `create_deep_agent`). IR + captions seeded as `/workspace/ir.json` + `/workspace/captions.json` through `seed_workspace()` writing to the on-disk root; agent reads/writes with built-in `read_file` / `write_file`. Matches spec §07 virtual FS layout and removes the need to maintain parallel custom tools. Trade-off accepted: 9 built-in tools (`ls`/`read_file`/`write_file`/`edit_file`/`glob`/`grep`/`execute`/`write_todos`/`task`) are visible to the model but the prompts constrain the procedure to read_file + write_file + (optionally) `task`.
- **2026-05-22** — `litellm_text_model()` helper added: any OpenAI-compatible proxy (LiteLLM, vLLM, DashScope, local model server) routes through `langchain_openai.ChatOpenAI` with `base_url`. Env vars `LITELLM_MODEL` / `LITELLM_BASE_URL` / `LITELLM_API_KEY` drive defaults so model + endpoint can be swapped without code changes.
- **2026-05-22** — Cleanup as a separate pass (not inlined into extractors) so raw IR stays debuggable; can A/B agent quality between full and cleaned IR.
- **2026-05-22** — Token-based chunking via `tiktoken.cl100k_base`; default 30K tokens. Not Claude's tokenizer but accurate within ~10-15% for our content — sufficient as a budget gate.
- **2026-05-22** — Oversize single unit emitted alone with `truncated=True` rather than splitting inside slide/page. Phase-1 simplification; revisit if a real sample triggers it.
- **2026-05-22** — All bbox standardized to `px @ 96 DPI` for consistency with `width_px` / `height_px` on images.
- **2026-05-22** — Dropped `TextShape.is_title` (placeholder-type detection was buggy + irrelevant for free-form decks).
