"""Public configuration dataclasses for the converter.

Spec: docs/superpowers/specs/2026-05-21-databricks-converter/04-api-surface.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

Provider = Literal["databricks", "openai", "anthropic", "google", "custom"]
Format = Literal["xlsx", "docx", "pptx", "pdf", "html", "markdown"]


@dataclass(frozen=True)
class ModelConfig:
    provider: Provider = "databricks"
    model: str = "databricks-claude-sonnet-4-6"
    base_url: str | None = None
    api_key_env: str | None = "DATABRICKS_TOKEN"
    instance: BaseChatModel | None = None
    extra_params: dict[str, Any] | None = None
    supports_vision: bool = True
    # Optional pacing for hosted endpoints with strict tokens-per-minute caps.
    # Applied via langchain InMemoryRateLimiter on the built chat model; covers
    # main agent + subagents + caption pre-pass since they share the model
    # instance. Estimate: rpm ≈ TPM_limit / avg_input_tokens_per_call.
    requests_per_minute: int | None = None


def _default_text_model() -> ModelConfig:
    return ModelConfig(
        provider="databricks",
        model="databricks-claude-sonnet-4-6",
        api_key_env="DATABRICKS_TOKEN",
    )


def _default_vision_model() -> ModelConfig:
    return ModelConfig(
        provider="databricks",
        model="databricks-claude-haiku-4-5",
        api_key_env="DATABRICKS_TOKEN",
        supports_vision=True,
    )


@dataclass(frozen=True)
class ConvertOptions:
    text_model: ModelConfig = field(default_factory=_default_text_model)
    vision_model: ModelConfig = field(default_factory=_default_vision_model)

    max_chunk_tokens: int = 20_000
    recursion_limit: int = 200

    # Sleep (seconds) inserted between consecutive chunk renders in aconvert.
    # 0 = no sleep. Useful when the LLM endpoint has a tokens-per-minute cap
    # and a single large render burns the full budget; sleeping lets the
    # budget reset before the next chunk starts.
    inter_chunk_sleep_seconds: float = 0.0

    # Shortcut: applies to text_model and vision_model if their own
    # ModelConfig.requests_per_minute is None. Set this when both models live
    # behind the same TPM-limited endpoint.
    model_requests_per_minute: int | None = None

    enable_quality_review: bool = True
    enable_quality_clean: bool = True
    enable_image_captions: bool = True
    caption_language: Literal["auto", "vi", "en"] = "auto"
    primary_language: Literal["vi", "en"] = "vi"

    max_concurrent_image_captions: int = 4
    image_caption_requests_per_minute: int = 60

    return_ir: bool = False
    write_to: str | Path | None = None

    # Opt-in: dump the agent's virtual workspace (ir.json, captions.json,
    # final.md, …) to this path after each chunk render. None = no disk I/O
    # at all (required on Databricks serverless where CWD is read-only).
    # Relative paths resolve against tempfile.gettempdir() so they remain
    # portable; pass an absolute path (e.g. a UC Volume) for persistence.
    debug_workspace: str | Path | None = None

    max_file_size_mb: int = 100
    request_timeout_seconds: int = 300

    fetch_remote_images: bool = True
    fetch_timeout_seconds: int = 10


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    source_path: str
    format: Format
    warnings: list[str]
    metadata: dict[str, Any]
    ir: dict[str, Any] | None = None
