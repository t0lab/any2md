# Design — Databricks `.whl` Compatibility & Agent Backend Rewrite

- **Date:** 2026-05-26
- **Status:** Approved, pending implementation plan
- **Scope:** Pure-Python correctness + alignment with `deepagents` 0.6.x recommended patterns + prompt refinement
- **Related:** [01-architecture.md](../2026-05-21-databricks-converter/01-architecture.md), [02-platform.md](../2026-05-21-databricks-converter/02-platform.md), [07-agent.md](../2026-05-21-databricks-converter/07-agent.md)

## 1. Problem

The library must run **100% locally** AND **100% on Databricks serverless** when installed from a `.whl`. Two independent audits surfaced root causes:

### 1.1 deepagents misuse (architecture)
[`main_agent.py`](../../../../src/any2md/agent/main_agent.py) wires a `CompositeBackend(default=StateBackend(), routes={/workspace/: FilesystemBackend(virtual_mode=True)})`. Research of `deepagents` 0.6.3 source confirms this is the wrong pattern:

- `FilesystemBackend` carries an explicit security warning ([`filesystem.py:51-89`](deepagents-install)) — official guidance: CLI/CI only, **not server/API**.
- `virtual_mode=True` is NOT in-memory mode — it is a path-normalization flag for `CompositeBackend`. It still writes disk.
- `BackendContext` is deprecated, removed in 0.7.0.
- The canonical "in-memory with seed inputs" pattern uses bare `StateBackend()` + payload `files={...}` on `invoke()`, with outputs read back via `result["files"][path]["content"]`.

### 1.2 Databricks notebook-runtime blockers
- [`convert.py:56`](../../../../src/any2md/convert.py#L56) calls `asyncio.run()`. Databricks notebook cells already have a running event loop → `RuntimeError`.
- [`convert.py:25`](../../../../src/any2md/convert.py#L25) defaults workspace root to relative `Path("workspace")`. Notebook CWD is `/Workspace/Users/<email>/` which is **read-only** → `PermissionError`.
- [`pyproject.toml`](../../../../pyproject.toml) has unpinned `databricks-langchain` + LC providers → version drift can clash with DBR-curated `langchain-core`.
- [`convert.py`](../../../../src/any2md/convert.py) hard-imports `agent.captions` / `agent.main_agent` at module top → `ImportError: deepagents` for users on bare wheel.

### 1.3 Prompt drift
Current prompts reference paths (`/workspace/raw_images/*.png`) that won't exist after the backend rewrite; mix concerns (rules + workspace layout + procedure in one block); rely heavily on negative constraints ("do NOT loop"); don't use XML structuring that improves parsing on Qwen / Sonnet.

## 2. Goals & non-goals

**Goals**
- Library import + `convert()` call succeed in both `python` (local CLI) and a Databricks notebook cell installed from `.whl`.
- Zero on-disk side effects by default. Debug-on-disk is opt-in via `ConvertOptions.debug_workspace`.
- Conform to deepagents 0.6.x best-practice (StateBackend + payload `files=`).
- Rewrite agent prompts using the `prompt-engineering` 4-step pipeline (Analyze → Architect → Generate → Critique).

**Non-goals**
- New extractors (docx, md) — separate spec.
- New providers — out of scope.
- Backwards-compatibility shims for the deleted on-disk seeding helpers. We rewrite cleanly; no `prompts_legacy.py`.

## 3. Design

### 3.1 Agent backend rewrite

[`agent/main_agent.py`](../../../../src/any2md/agent/main_agent.py) becomes:

```python
from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from deepagents.backends.utils import create_file_data

_AGENT_CACHE: dict[tuple, "CompiledStateGraph"] = {}

def _agent_key(options: ConvertOptions) -> tuple:
    tm = options.text_model
    # Identifying fields of the model config. `instance` (pre-built BaseChatModel)
    # is identified by `id(...)` so two ConvertOptions sharing the same instance
    # share the cached agent.
    model_id = id(tm.instance) if tm.instance is not None else (tm.provider, tm.model, tm.base_url)
    return (
        model_id,
        options.enable_quality_review,
        options.caption_language,
        options.primary_language,
    )

def _build_agent(options: ConvertOptions):
    key = _agent_key(options)
    cached = _AGENT_CACHE.get(key)
    if cached is not None:
        return cached
    llm = build_llm(options.text_model)
    prompt = format_main_prompt(
        with_review=options.enable_quality_review,
        caption_language=options.caption_language,
        primary_language=options.primary_language,
    )
    subagents = [quality_reviewer_subagent()] if options.enable_quality_review else []
    agent = create_deep_agent(
        model=llm,
        system_prompt=prompt,
        subagents=subagents,
        backend=StateBackend(),  # pure in-memory, thread-isolated per-invoke
    )
    _AGENT_CACHE[key] = agent
    return agent

async def arender_chunk(
    ir: dict[str, Any], *,
    captions: dict[str, str] | None = None,
    previous_tail: str | None = None,
    options: ConvertOptions,
    debug_workspace: Path | None = None,
) -> str:
    agent = _build_agent(options)
    files = build_initial_files(ir, captions, previous_tail)
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": "Render this chunk to markdown."}],
         "files": files},
        config={"recursion_limit": options.recursion_limit},
    )
    final = result["files"].get(FINAL_PATH)
    md = final["content"] if final else ""
    if debug_workspace:
        _dump_state_to_disk(debug_workspace, result["files"])
    return md

def render_chunk(...) -> str:
    # sync wrapper for non-async callers — uses _run_sync helper
    return _run_sync(arender_chunk(...))
```

[`agent/tools.py`](../../../../src/any2md/agent/tools.py) is reduced to:

```python
WORKSPACE_ROOT = "/workspace"
IR_PATH       = f"{WORKSPACE_ROOT}/ir.json"
CAPTIONS_PATH = f"{WORKSPACE_ROOT}/captions.json"
FINAL_PATH    = f"{WORKSPACE_ROOT}/final.md"
TAIL_PATH     = f"{WORKSPACE_ROOT}/previous_tail.md"

def build_initial_files(ir, captions, previous_tail) -> dict[str, dict]:
    files = {
        IR_PATH: create_file_data(json.dumps(ir, ensure_ascii=False, indent=2)),
        CAPTIONS_PATH: create_file_data(json.dumps(captions or {}, ensure_ascii=False, indent=2)),
    }
    if previous_tail:
        files[TAIL_PATH] = create_file_data(previous_tail)
    return files

def _dump_state_to_disk(target: Path, files: dict[str, dict]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for path, data in files.items():
        rel = path.lstrip("/").removeprefix("workspace/")
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data["content"], encoding="utf-8")
```

`raw_images/*.png` is **no longer seeded** into the virtual FS — captions are pre-computed and embedded verbatim, agent does not need the image bytes.

### 3.2 Databricks notebook compat — `aconvert()` + `convert()` dual entry

[`convert.py`](../../../../src/any2md/convert.py):

```python
import asyncio
import concurrent.futures

async def aconvert(source, *, options=None, workspace_root=None) -> ConvertResult:
    # full pipeline — async-native — used directly in notebooks
    options = options or ConvertOptions()
    src = Path(source).resolve()
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")

    # defer agent imports → bare-wheel users get a clear error here, not at module load
    try:
        from .agent.captions import caption_pass
        from .agent.image_refs import collect_image_refs
        from .agent.main_agent import arender_chunk
    except ImportError as e:
        raise ImportError(
            "any2md.convert() needs the agent extras. "
            "Install with: pip install 'any2md[agent,databricks]'"
        ) from e

    cleaned = extract_and_clean(src)

    captions: dict[str, str] = {}
    if options.enable_image_captions and collect_image_refs(cleaned.ir):
        vision_llm = build_llm(options.vision_model)
        captions = await caption_pass(cleaned.ir, cleaned.images, vision_llm, options)

    chunks = chunk_ir(cleaned.ir, max_tokens=options.max_chunk_tokens)
    parts: list[str] = []
    previous_tail = None
    for chunk in chunks:
        chunk_refs = collect_image_refs(chunk["ir"])
        chunk_captions = {r["id"]: captions[r["id"]] for r in chunk_refs if r["id"] in captions}
        debug_ws = _resolve_debug_workspace(options, src, chunk, multi=len(chunks) > 1)
        md = await arender_chunk(
            chunk["ir"],
            captions=chunk_captions,
            previous_tail=previous_tail,
            options=options,
            debug_workspace=debug_ws,
        )
        parts.append(md)
        previous_tail = md[-1000:] if md else None

    markdown = "\n\n".join(p for p in parts if p)
    # write_to / return result as before
    return ConvertResult(...)


def convert(source, *, options=None, workspace_root=None) -> ConvertResult:
    """Sync wrapper. Works whether or not a loop is already running."""
    coro = aconvert(source, options=options, workspace_root=workspace_root)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already inside a loop (Databricks notebook, IPython, Jupyter) → off-thread
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


def _resolve_debug_workspace(options, src, chunk, multi):
    if options.debug_workspace is None:
        return None
    base = Path(options.debug_workspace)
    if not base.is_absolute():
        base = Path(tempfile.gettempdir()) / base
    stem_dir = base / src.stem
    return stem_dir / f"chunk_{chunk['chunk_index']:02d}" if multi else stem_dir
```

### 3.3 `pyproject.toml` pins

```toml
[project]
description = "any2md — converts office and web documents (xlsx/docx/pptx/pdf/html/md) into structured markdown. No subprocess, no system binaries; installs from manylinux wheels — runs anywhere Python 3.11+ runs, including Databricks serverless."

dependencies = [
    "openpyxl>=3.1,<4",
    "python-docx>=1.1,<2",
    "python-pptx>=1.0,<2",
    "pymupdf>=1.24.10,<2",   # 1.24.10+ has manylinux_2_28_aarch64
    "lxml>=5.0,<6",
    "beautifulsoup4>=4.12,<5",
    "markdown-it-py>=3.0,<4",
    "Pillow>=10.0,<12",
    "tiktoken>=0.7,<1",
]

[project.optional-dependencies]
agent      = ["langchain-core>=0.3,<0.4", "deepagents>=0.6,<0.7", "tenacity", "python-dotenv>=1.0"]
databricks = ["databricks-langchain>=0.5,<0.7"]
openai     = ["langchain-openai>=0.2,<0.4"]
anthropic  = ["langchain-anthropic>=0.2,<0.4"]
google     = ["langchain-google-genai>=2,<3"]
# `all` deliberately excludes databricks-langchain — serverless already has it
all        = ["langchain-core>=0.3,<0.4", "deepagents>=0.6,<0.7", "tenacity", "python-dotenv>=1.0",
              "langchain-openai>=0.2,<0.4", "langchain-anthropic>=0.2,<0.4", "langchain-google-genai>=2,<3"]
dev        = ["pytest>=8.0", "pytest-asyncio", "syrupy", "ruff", "mypy", "build"]
```

### 3.4 Prompt refinement

Apply the `prompt-engineering` 4-step pipeline (Analyze → Architect → Generate → Critique) to each prompt. Architectures selected:

| Prompt | Architecture | File |
|---|---|---|
| Main agent (with-review / no-review) | Tool-Using Agent | [`agent/prompts.py`](../../../../src/any2md/agent/prompts.py) |
| Image captioner | Multi-Step Reasoning | [`agent/captions.py`](../../../../src/any2md/agent/captions.py) |
| Quality reviewer | Pipeline Agent | [`agent/subagents/quality_reviewer.py`](../../../../src/any2md/agent/subagents/quality_reviewer.py) |

**Structural changes applied to all three:**

1. **XML tags** group rules: `<identity>`, `<rules>`, `<procedure>`, `<output_format>`, `<guardrails>`. Improves parsing on Qwen / Claude / GPT alike.
2. **Identity at start AND end** (primacy/recency) — repeat the one-line mission as the closing line.
3. **Positive instructions over negative**: replace "do NOT loop" with "Render EXACTLY N image blocks where N = number of image references in IR" + a worked counting example.
4. **Stale paths removed** — no more `/workspace/raw_images/*.png` references; no more `draft.md` references.
5. **1-2 worked examples per prompt** with `[placeholders]` for variable parts.
6. **Output format pinned** — especially for the quality reviewer: exact format `Reviewed N edits applied: <reason>; …` or `Reviewed clean.`

Each prompt is re-evaluated against the 10-point rubric in `references/evaluation.md` before commit:
- Clarity, completeness, specificity
- No contradictions, reasoning-before-conclusions
- Explicit output format
- Guardrails present
- Examples present where outputs are complex
- Shortest correct length
- Testable instructions

### 3.5 File layout summary

| File | Change kind |
|---|---|
| `agent/main_agent.py` | Rewrite — StateBackend, agent cache, `arender_chunk` async-native + sync wrapper |
| `agent/tools.py` | Slim down — keep virtual path constants; replace `seed_workspace` with `build_initial_files`; add `_dump_state_to_disk` |
| `agent/prompts.py` | Rewrite via prompt-engineering pipeline |
| `agent/captions.py` | Prompt-only edit (XML wrap, example) |
| `agent/subagents/quality_reviewer.py` | Prompt-only edit (3 verify groups, edit_file example, output format) |
| `convert.py` | Split into `aconvert` + `convert` wrapper; defer agent imports; `_resolve_debug_workspace` |
| `options.py` | Add `debug_workspace: Path | None = None` |
| `pyproject.toml` | Pin LC stack, fix description, bump pymupdf min |
| `agent/__init__.py` | Re-export `arender_chunk` |
| `__init__.py` (top) | Add `aconvert` to public API |

## 4. Verification

### 4.1 Local — sync path
```powershell
py scripts/run_agent.py samples/test.html
py scripts/run_agent.py samples/logic_tree_lending.pptx
```
Expect: `final.md` written to `result.markdown`, no `workspace/` dir created in CWD (unless `--debug-workspace` flag).

### 4.2 Local — async + sync coexistence (notebook simulation)
```python
# tests/manual/test_notebook_loop.py
import asyncio
from any2md.convert import aconvert, convert

async def main():
    r1 = convert("samples/test.html")          # sync wrapper inside loop → thread hop
    r2 = await aconvert("samples/test.html")   # native async
    assert r1.markdown == r2.markdown
    assert r1.metadata == r2.metadata

asyncio.run(main())
```
Expect: both paths succeed, outputs match.

### 4.3 Wheel + clean-venv install
```powershell
py -m build --wheel
py -m venv .venv-smoke; .venv-smoke\Scripts\activate
pip install dist\any2md-0.0.1-py3-none-any.whl[agent,databricks]
cd $env:TEMP
py -c "from any2md.convert import convert; print(convert('d:/converter/samples/test.html').markdown[:200])"
```
Expect: succeeds, no `workspace/` created under `$env:TEMP`.

### 4.4 No-FS guarantee
```powershell
py -c "
import os, any2md.convert
any2md.convert.convert('samples/test.html')
assert not os.path.exists('workspace'), 'should not create dir by default'
print('OK: no workspace dir')
"
```

### 4.5 Bare-wheel ImportError clarity
```powershell
py -m venv .venv-bare; .venv-bare\Scripts\activate
pip install dist\any2md-0.0.1-py3-none-any.whl    # no extras
py -c "from any2md.convert import convert; convert('samples/test.html')"
```
Expect: `ImportError` mentioning `pip install 'any2md[agent,databricks]'`, NOT a raw `ModuleNotFoundError: deepagents`.

### 4.6 Prompt regression on samples
After prompt rewrite, run `run_agent.py samples/test.html` (3 images) and `run_agent.py samples/logic_tree_lending.pptx` (multi-chunk capable). Verify:
- `#image-blocks` in final.md == `#image refs` in IR
- No trailing duplicate sections
- No phantom headings (every heading traces to an IR block)
- Captions unchanged from `captions.json` (reviewer must not rewrite them)

## 5. Risks & trade-offs

| Risk | Mitigation |
|---|---|
| LC pin ranges too tight, blocks future LC releases | Lift cap when a new LC minor lands and is verified locally + on a Databricks test cluster |
| Sync `convert()` thread-hop wrapper adds ~50ms overhead in notebooks | Document `aconvert()` as preferred path in notebooks |
| Module-level agent cache leaks if user mutates `ConvertOptions` mid-process | Cache key includes the fields that affect prompt/middleware; mutating other fields is safe |
| Prompt rewrite regresses output quality on edge cases not in sample set | Run both sample files end-to-end pre-merge; quality reviewer subagent acts as safety net |
| Subagent file propagation in deepagents 0.6.3 untested with StateBackend | Verify during implementation step 2 (StateBackend swap); rollback to CompositeBackend if it breaks |

## 6. Rollout

Single feature branch, commits scoped per area so each can be reverted independently:

1. **Pin pyproject.toml** — no behavioral risk
2. **Refactor `tools.py` + `main_agent.py`** — StateBackend swap; verify samples pass
3. **Split `convert.py` into `aconvert` + `convert`** — notebook-simulation test
4. **Rewrite 3 prompts** via prompt-engineering pipeline — verify quality on samples
5. **Build wheel + smoke install** in clean venv
6. **Update STATE.md + AGENTS.md** documenting the new pattern

No legacy fallback. No `prompts_legacy.py`. Forward-only.

## 7. Open questions

None at design-time. Implementation may surface:
- Exact `result["files"]` schema after `ainvoke` (verify on first sample run; the deepagents source describes `{"content": str, ...}` but field set might differ in 0.6.3).
- Whether `task` tool invocation propagates a `files` mutation back to the parent's `result` (expected yes since it's all LangGraph state). If not, fall back to having the reviewer return the final markdown in its message text and have the parent extract it.
