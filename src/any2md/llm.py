"""LLM factory.

Builds a `BaseChatModel` from a `ModelConfig`. Supports four providers plus
a `custom` slot that requires `instance` to be set, and an OpenAI-compatible
branch usable for LiteLLM proxies, vLLM, DashScope, Qwen, etc. (via `base_url`).

Spec: docs/superpowers/specs/2026-05-21-databricks-converter/07-agent.md
      §"LLM wiring"
"""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from .options import ModelConfig


def build_llm(config: ModelConfig) -> BaseChatModel:
    if config.instance is not None:
        return config.instance

    api_key = os.getenv(config.api_key_env) if config.api_key_env else None
    extras = dict(config.extra_params or {})

    if config.provider == "databricks":
        from databricks_langchain import ChatDatabricks
        return ChatDatabricks(endpoint=config.model, temperature=0, **extras)

    if config.provider == "openai":
        from langchain_openai import ChatOpenAI
        # streaming=True keeps Cloudflare-fronted proxies (e.g. LiteLLM) from
        # hitting their 120s origin-response timeout on plain text completions.
        # Tool-call payloads are still buffered by some proxies, so we also bump
        # max_retries — 524 from a transient origin overload is marked retryable.
        return ChatOpenAI(
            model=config.model,
            base_url=config.base_url,
            api_key=api_key,
            temperature=0,
            streaming=True,
            max_retries=5,
            timeout=180,
            **extras,
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
        raise ValueError("provider='custom' requires `instance` to be set on ModelConfig")

    raise ValueError(f"Unknown provider: {config.provider}")


DEFAULT_LITELLM_MODEL = "openai/Qwen/Qwen3.6-35B-A3B"
DEFAULT_LITELLM_BASE_URL = "https://litellm-horseai.everlearners.io/v1"


def litellm_text_model(
    *,
    model: str | None = None,
    base_url: str | None = None,
    api_key_env: str = "LITELLM_API_KEY",
) -> "ModelConfig":
    """Convenience constructor for the project's LiteLLM proxy.

    Reads `LITELLM_MODEL` and `LITELLM_BASE_URL` from the environment with
    package-level defaults as fallback. Explicit kwargs override env.

    The endpoint speaks OpenAI Chat Completions, so we route through
    `langchain_openai.ChatOpenAI` with `base_url` set to the proxy.
    """
    from .options import ModelConfig
    return ModelConfig(
        provider="openai",
        model=model or os.getenv("LITELLM_MODEL") or DEFAULT_LITELLM_MODEL,
        base_url=base_url or os.getenv("LITELLM_BASE_URL") or DEFAULT_LITELLM_BASE_URL,
        api_key_env=api_key_env,
        supports_vision=True,
    )
