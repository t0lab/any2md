# 04 — API Surface

[← Index](./README.md)

## Entry points

```python
def convert(
    source: str | Path,
    *,
    options: ConvertOptions | None = None,
) -> ConvertResult: ...

def batch_convert(
    sources: Iterable[str | Path],
    *,
    options: ConvertOptions | None = None,
    max_workers: int = 4,
) -> list[ConvertResult | Exception]: ...
```

Path forms accepted:
- UC Volume absolute: `/Volumes/<cat>/<sch>/<vol>/file.pptx`
- Workspace files: `/Workspace/Users/.../file.pptx`
- Relative: `./samples/test.pptx`
- Local absolute: `/tmp/...`, `C:\...`
- `pathlib.Path`

`batch_convert()` returns `ConvertResult | Exception` per item (does not raise on per-item failures); order preserved.

## `ModelConfig`

```python
@dataclass(frozen=True)
class ModelConfig:
    provider: Literal["databricks", "openai", "anthropic", "google", "custom"] = "databricks"
    model: str = "databricks-claude-sonnet-4-6"
    base_url: str | None = None           # for OpenAI-compatible custom endpoints
    api_key_env: str | None = "DATABRICKS_TOKEN"
    instance: BaseChatModel | None = None # if set, all other fields ignored
    extra_params: dict | None = None
    supports_vision: bool = True
```

Three usage patterns:
1. **Provider string-based** (default — Databricks)
2. **OpenAI-compatible custom endpoint** (Qwen, vLLM, DashScope, local model server)
3. **Pre-built `BaseChatModel` instance** for full control

## `ConvertOptions`

```python
@dataclass(frozen=True)
class ConvertOptions:
    # Models
    text_model: ModelConfig = field(default_factory=lambda: ModelConfig(
        provider="databricks", model="databricks-claude-sonnet-4-6",
        api_key_env="DATABRICKS_TOKEN",
    ))
    vision_model: ModelConfig = field(default_factory=lambda: ModelConfig(
        provider="databricks", model="databricks-claude-haiku-4-5",
        api_key_env="DATABRICKS_TOKEN", supports_vision=True,
    ))

    # Chunking / agent
    max_chunk_tokens: int = 150_000
    recursion_limit: int = 200

    # Behavior
    enable_quality_review: bool = True
    enable_image_captions: bool = True
    caption_language: Literal["auto", "vi", "en"] = "auto"
    primary_language: Literal["vi", "en"] = "vi"

    # Image captioning rate limiting
    max_concurrent_image_captions: int = 4
    image_caption_requests_per_minute: int = 60

    # Output
    return_ir: bool = False
    write_to: str | Path | None = None

    # Limits
    max_file_size_mb: int = 100
    request_timeout_seconds: int = 300

    # HTML / markdown remote images
    fetch_remote_images: bool = True
    fetch_timeout_seconds: int = 10
```

## `ConvertResult`

```python
@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    source_path: str                       # resolved absolute path
    format: Literal["xlsx", "docx", "pptx", "pdf", "html", "markdown"]
    warnings: list[str]
    metadata: dict                         # see 08-errors-and-observability.md §metrics
    ir: dict | None = None                 # if options.return_ir
```

## Error model (summary)

All errors inherit `ConverterError(Exception)`. Full hierarchy in [08-errors-and-observability.md](./08-errors-and-observability.md#error-class-hierarchy).

`convert()` raises on fatal errors. `batch_convert()` captures per-item exceptions into the result list.

## Usage examples

```python
# Production Databricks (default)
result = convert("./samples/test.pptx")

# Write to UC Volume
result = convert(
    "/Volumes/cat/sch/raw/report.pdf",
    options=ConvertOptions(write_to="/Volumes/cat/sch/kb/report.md"),
)

# Local dev with Gemini Flash
result = convert("./samples/test.pptx", options=ConvertOptions(
    text_model=ModelConfig(provider="google", model="gemini-2.5-flash", api_key_env="GOOGLE_API_KEY"),
    vision_model=ModelConfig(provider="google", model="gemini-2.5-flash", api_key_env="GOOGLE_API_KEY"),
))

# Local dev with Qwen via DashScope (OpenAI-compatible)
result = convert("./samples/test.pptx", options=ConvertOptions(
    text_model=ModelConfig(
        provider="openai", model="qwen2.5-72b-instruct",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
    ),
    vision_model=ModelConfig(
        provider="openai", model="qwen2.5-vl-72b-instruct",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key_env="DASHSCOPE_API_KEY",
    ),
))

# Batch
results = batch_convert(
    Path("./samples").glob("*.pptx"),
    options=ConvertOptions(max_concurrent_image_captions=2),
    max_workers=8,
)

# Debug — return IR, skip quality review
result = convert("./samples/test.docx",
                 options=ConvertOptions(return_ir=True, enable_quality_review=False))
```
