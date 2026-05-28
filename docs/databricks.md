# Running any2md on Databricks

Step-by-step guide for installing and using `any2md` from a Databricks workspace
notebook — Serverless or Classic compute, Unity Catalog Volumes for storage.
The library has zero Databricks-specific runtime dependencies; the same wheel
that runs locally runs unmodified here. What changes is how you reference
files (UC paths) and which LLM endpoint you point at.

## Prerequisites

- Workspace with Unity Catalog enabled.
- Serverless compute (recommended) or an All-Purpose cluster on DBR ≥ 14.3 LTS.
- One of: Foundation Model API access (default workspace entitlement) OR
  credentials for an external provider (LiteLLM proxy, OpenAI, Anthropic, …).

## 1. Install

Pick one of the two patterns. Both end with a Python kernel restart so the
package is importable in the notebook session.

### A. Pin a wheel inside a UC Volume (recommended)

Upload the wheel once, install from there in every notebook. Governance-tracked,
reproducible, no public-internet dependency at install time.

```python
%pip install /Volumes/<catalog>/<schema>/<volume>/any2md-0.0.1-py3-none-any.whl[agent,databricks]
dbutils.library.restartPython()
```

Upload the wheel via the UC Volumes UI, `databricks fs cp`, or your CI release
job. Pin a specific filename so you control upgrade timing.

### B. Direct from GitHub (quick try / dev only)

```python
%pip install "any2md[agent,databricks] @ https://github.com/t0lab/any2md/raw/main/dist/any2md-0.0.1-py3-none-any.whl"
dbutils.library.restartPython()
```

Replace `main` with a commit SHA or tag to pin. Requires public-internet egress
from the workspace.

## 2. Pick the model backend

### Foundation Model API (simplest, no creds needed)

Workspace credentials auto-resolve via `databricks_langchain.ChatDatabricks`.

```python
from any2md.llm import LLMConfig

text   = LLMConfig(provider="databricks", model="databricks-claude-sonnet-4-6")
vision = LLMConfig(provider="databricks", model="databricks-claude-haiku-4-5")
```

Common endpoint names (availability depends on your workspace):

| Endpoint | Use for |
|---|---|
| `databricks-claude-sonnet-4-6` | Main render — balanced quality / cost. |
| `databricks-claude-haiku-4-5` | Image captioner — fast and cheap. |
| `databricks-claude-opus-4-7` | Highest-quality render — slower. |

### External provider (LiteLLM, OpenAI, etc.)

Read credentials from a secret scope, never inline:

```python
import os
os.environ["LITELLM_API_KEY"]  = dbutils.secrets.get(scope="any2md", key="litellm-key")
os.environ["LITELLM_BASE_URL"] = "https://your-proxy.example/v1"

from any2md.llm import litellm_text_model
text = vision = litellm_text_model()
```

> External endpoints require workspace network egress to the proxy host. If
> your workspace is behind PrivateLink with restricted egress, either add the
> proxy domain to the allow list or stay on Foundation Model API.

## 3. File paths — use the UC POSIX form

`any2md` calls `pathlib.Path(source).exists()`. On Databricks Runtime, UC
Volumes are mounted as POSIX paths under `/Volumes/`:

```
/Volumes/<catalog>/<schema>/<volume>/<file>
```

Use that form, **not** `dbfs:/Volumes/...` (URI form is not supported — `Path`
treats `dbfs:` as part of the path and `.exists()` returns `False`).

```python
src = "/Volumes/my_cat/raw/intake/report.pptx"      # canonical UC path
src = "/dbfs/Volumes/my_cat/raw/intake/report.pptx" # also works (FUSE mount)
src = "dbfs:/Volumes/my_cat/raw/intake/report.pptx" # NOT supported
```

If your source lives in S3 / ADLS / GCS, stage it into a Volume first
(`dbutils.fs.cp(...)`); `any2md` itself doesn't fetch remote objects.

## 4. End-to-end notebook cell

```python
from any2md import convert, ConvertOptions
from any2md.llm import LLMConfig

text   = LLMConfig(provider="databricks", model="databricks-claude-sonnet-4-6")
vision = LLMConfig(provider="databricks", model="databricks-claude-haiku-4-5")

result = convert(
    "/Volumes/my_cat/raw/intake/report.pptx",
    options=ConvertOptions(
        text_model=text,
        vision_model=vision,
        write_to="/Volumes/my_cat/curated/markdown/report.md",
        # For large pptx / pdf, force multi-chunk to bound per-call prefill:
        max_chunk_tokens=8000,
    ),
)

print("chunks:",  result.metadata["chunk_count"])
print("images:",  result.metadata["image_count"])
print("captions:", result.metadata["caption_count"])
print(result.markdown[:500])
```

`convert()` is the sync wrapper — safe to call from a notebook cell that is
already inside an event loop. It detects the loop and dispatches to a worker
thread under the hood. For fully async code use `aconvert()`:

```python
from any2md import aconvert
result = await aconvert("/Volumes/.../report.pptx", options=...)
```

## 5. Where to write output

| Destination | `options.write_to` pattern | Notes |
|---|---|---|
| UC Volume | `/Volumes/<cat>/<sch>/<vol>/out.md` | Requires `WRITE VOLUME`. |
| Local scratch | `/tmp/out.md` | Lost on cluster restart — debug only. |
| Delta table | (post-process) | Read `result.markdown` and INSERT via Spark; `convert()` does not write Delta directly. |

`options.debug_workspace=Path("debug")` mirrors the agent's virtual workspace
(`ir.json`, `captions.json`, per-chunk `final.md`) under `/tmp/debug/<stem>/`
on the cluster. Useful when chasing why a single chunk renders poorly.

## 6. Caveats and troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FileNotFoundError: source not found: /Volumes/...` | Path typo or passed `dbfs:/...` URI form | Use the canonical `/Volumes/<cat>/<sch>/<vol>/file` path |
| `ImportError: any2md.convert/aconvert needs the agent extras` | Installed bare wheel without `[agent]` | Reinstall with `[agent,databricks]` extras |
| `PermissionError` on write | No WRITE on target UC Volume | Grant `MODIFY VOLUME`, or write to `/tmp/` and copy with `dbutils.fs.cp` |
| Run hangs 5+ minutes on one chunk | LLM endpoint slow on large prefill | Lower `max_chunk_tokens` (e.g. 8000), or set `enable_quality_review=False` + `enable_quality_clean=False` (deterministic post-process still cleans) |
| `openai.InternalServerError: 524` | Cloudflare-fronted proxy timed out origin | Switch to Foundation Model API endpoint, or use a non-Cloudflare proxy |
| Missing slides / truncated output | Single chunk too large for the model | Reduce `max_chunk_tokens` so the doc splits into more chunks; rerun |
| Image captions empty / look like filenames | `enable_image_captions=False`, OR vision endpoint unreachable | Re-enable captions and verify `vision_model` resolves; check egress |

**Per-call concurrency.** Each `convert()` invocation holds its own event
loop. To process many files in parallel from one notebook, use `aconvert()`
inside `asyncio.gather(...)` rather than calling sync `convert()` in a thread
pool.

**Cost.** Captions run one vision call per image. A pptx with 30 images
triggers 30 vision requests; budget accordingly. Set `enable_image_captions=False`
to fall back to alt-text and skip the vision pre-pass entirely.

## See also

- [README.md](../README.md) — library overview, formats, configuration.
- [STATE.md](../STATE.md) — current pipeline state and known gaps.
- [src/any2md/options.py](../src/any2md/options.py) — full `ConvertOptions` reference.
- [docs/superpowers/specs/2026-05-26-databricks-compat-and-agent-rewrite/design.md](superpowers/specs/2026-05-26-databricks-compat-and-agent-rewrite/design.md) — design rationale.
