# any2md

> Agent that converts office and web documents into structured markdown for knowledge bases.

`any2md` turns `.xlsx` / `.docx` / `.pptx` / `.pdf` / `.html` / `.md` into clean, agent-rendered markdown — preserving reading order, tables, charts, diagrams, and image captions. It is a general-purpose library: it runs on any machine with Python 3.11+, and because every dependency is pure-Python (no `subprocess`, no system binaries), it also runs unmodified on **Databricks serverless compute**.

## Why

Knowledge bases ingest messy office documents. A naive pdf→txt or pptx→html dump loses tables, scrambles reading order, drops images, and produces markdown nobody wants to read. `any2md` does the structural work as a deterministic pre-pass, then uses a small reasoning LLM (any OpenAI-compatible endpoint, Anthropic, Databricks Foundation Models, or Google) to render the markdown — with a quality-reviewer subagent that checks completeness before returning.

## Pipeline

```
source file (.xlsx/.docx/.pptx/.pdf/.html/.md)
        ↓ extract     pure-Python parsers per format
raw IR + image bytes
        ↓ clean       strip redundancy, normalize bbox to px @ 96 DPI
cleaned IR
        ↓ caption     async vision LLM, parallel per image
captions: dict[image_id → text]
        ↓ render      deepagents main agent + quality-reviewer subagent
                      virtual FS at /workspace/ (CompositeBackend)
markdown
```

Top-level entry: `convert(source, options) -> ConvertResult` ([src/any2md/convert.py](src/any2md/convert.py)).

## Supported formats

| Format | Extractor | Status |
|---|---|---|
| `.xlsx` / `.xlsm` | [extractors/xlsx.py](src/any2md/extractors/xlsx.py) | Done |
| `.pptx` / `.pptm` | [extractors/pptx.py](src/any2md/extractors/pptx.py) | Done |
| `.pdf` | [extractors/pdf.py](src/any2md/extractors/pdf.py) | Done |
| `.html` / `.htm` | [extractors/html.py](src/any2md/extractors/html.py) | Done |
| `.docx` / `.docm` | — | Pending |
| `.md` / `.markdown` | — | Pending |

## Install

```powershell
py -m pip install -e ".[agent,openai]"
```

Optional extras:

| Extra | When to install |
|---|---|
| `agent` | Required for the LLM-rendering layer (deepagents + langchain-core + python-dotenv) |
| `openai` | OpenAI-compatible endpoints — LiteLLM proxies, vLLM, DashScope, Qwen |
| `databricks` | `ChatDatabricks` via `databricks_langchain` (auto-picks workspace credentials) |
| `anthropic` / `google` | Direct provider clients |
| `all` | Everything above |
| `dev` | pytest, ruff, mypy |

## Quick start

1. Copy the env template and fill in your model credentials:

   ```powershell
   Copy-Item .env.example .env
   ```

   At minimum set `LITELLM_API_KEY` (or swap `text_model` / `vision_model` for another provider — see [04-api-surface.md](docs/superpowers/specs/2026-05-21-databricks-converter/04-api-surface.md)).

2. Run the end-to-end smoke test:

   ```powershell
   py scripts/run_agent.py samples/test.html             # in-memory only
   py scripts/run_agent.py samples/test.html --debug     # also dump to ./workspace/
   ```

   With `--debug` the agent's virtual workspace is mirrored to disk for
   inspection at `workspace/<stem>/` (or `workspace/<stem>/chunk_NN/` for
   multi-chunk runs):
   ```
   workspace/test/
     ir.json         # cleaned IR fed to the agent
     captions.json   # pre-computed image captions
     final.md        # returned markdown
   ```

3. From a script (sync API, safe in or out of a running loop):

   ```python
   from any2md import convert, ConvertOptions
   from any2md.llm import litellm_text_model

   llm = litellm_text_model()   # reads LITELLM_* env vars
   result = convert(
       "samples/test.html",
       options=ConvertOptions(text_model=llm, vision_model=llm),
   )
   print(result.markdown)
   ```

4. From a notebook / async handler (preferred — no thread hop):

   ```python
   from any2md import aconvert, ConvertOptions
   from any2md.llm import litellm_text_model

   result = await aconvert(
       "samples/test.html",
       options=ConvertOptions(text_model=litellm_text_model()),
   )
   ```

## Configuration

All knobs live on `ConvertOptions` ([src/any2md/options.py](src/any2md/options.py)):

| Knob | Default | Effect |
|---|---|---|
| `text_model` | Databricks Claude Sonnet 4.6 | Main rendering LLM |
| `vision_model` | Databricks Claude Haiku 4.5 | Image captioner |
| `enable_image_captions` | `True` | Skip pre-pass to use only `alt_text` |
| `enable_quality_review` | `True` | Skip reviewer subagent to halve LLM calls |
| `caption_language` | `"auto"` | `"vi"` / `"en"` to force |
| `max_chunk_tokens` | `30_000` | Budget gate via `tiktoken.cl100k_base` |
| `max_concurrent_image_captions` | `4` | `asyncio.Semaphore` cap |
| `image_caption_requests_per_minute` | `60` | Token-bucket rate limit |
| `return_ir` | `False` | Include cleaned IR in `ConvertResult` |
| `write_to` | `None` | Path to also write final markdown |
| `debug_workspace` | `None` | Opt-in: mirror agent virtual state to disk (relative paths resolve under `tempfile.gettempdir()`; absolute paths honored) |

`ModelConfig` supports 5 providers (`databricks`, `openai`, `anthropic`, `google`, `custom`) plus a pre-built `BaseChatModel` instance. Any OpenAI-compatible endpoint (LiteLLM, vLLM, DashScope, Ollama, Qwen) works via `provider="openai"` with a custom `base_url`.

## Running on Databricks

The library has no Databricks runtime dependency — installing the same wheel that runs locally works on serverless and classic clusters alike. Specifics:

- **Compute**: Serverless ✓ (recommended). Classic ✓. No init script, no `apt-get`, no `LibreOffice`/`Tesseract`/`Pandoc` — all dependencies are PyPI manylinux wheels.
- **Storage**: Unity Catalog Volumes (`/Volumes/<cat>/<sch>/<vol>/file.pptx`). DBFS is deprecated and unsupported.
- **Auth**: On the cluster, workspace credentials are auto-picked. Locally, set `DATABRICKS_HOST` + `DATABRICKS_TOKEN`.
- **Models**: Built-in support for Foundation Model API endpoints (`databricks-claude-sonnet-4-6`, `databricks-claude-haiku-4-5`, `databricks-claude-opus-4-7`) via `databricks_langchain.ChatDatabricks`. Other providers work just as well — `convert()` doesn't care where the model lives.

Constraints documented in [02-platform.md](docs/superpowers/specs/2026-05-21-databricks-converter/02-platform.md).

## Observability

If `LANGSMITH_TRACING=true` is set in `.env`, every agent run produces a full trace tree (main agent steps → tool calls → subagent invocations → token counts → latency) at https://smith.langchain.com under the project name configured in `LANGSMITH_PROJECT`.

## Repository layout

| Path | Purpose |
|---|---|
| [src/any2md/](src/any2md/) | Library code |
| [src/any2md/extractors/](src/any2md/extractors/) | Per-format pure-Python parsers |
| [src/any2md/ir_clean.py](src/any2md/ir_clean.py) | Post-extraction cleanup pass |
| [src/any2md/ir_chunk.py](src/any2md/ir_chunk.py) | Token-budgeted chunking |
| [src/any2md/agent/](src/any2md/agent/) | Caption pre-pass, main agent, subagents |
| [src/any2md/convert.py](src/any2md/convert.py) | `convert()` API |
| [scripts/](scripts/) | Pipeline driver scripts (dump_ir, clean_ir, chunk_ir, run_agent) |
| [samples/](samples/) | Source fixtures |
| [docs/superpowers/specs/](docs/superpowers/specs/) | Design spec (numbered 01-11) |
| [AGENTS.md](AGENTS.md) | Conventions for any agent (human or AI) editing this repo |
| [STATE.md](STATE.md) | Living status snapshot — updated on every milestone |

## Status

See [STATE.md](STATE.md) for the current pipeline state, completed items, and pending work. Full design rationale and decision log live in [docs/superpowers/specs/2026-05-21-databricks-converter/](docs/superpowers/specs/2026-05-21-databricks-converter/).

## License

TBD.
