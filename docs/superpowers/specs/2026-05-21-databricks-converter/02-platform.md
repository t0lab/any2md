# 02 — Platform Constraints

[← Index](./README.md)

## Databricks compute

Confirmed from Databricks 2026 documentation:

| Capability | Serverless | Classic + init script |
|---|---|---|
| `pip install` arbitrary PyPI | ✓ | ✓ |
| `apt-get` system packages (LibreOffice, Tesseract, Pandoc) | ✗ | ✓ |
| Subprocess of native binaries | ✗ | ✓ |
| MS Office (Linux) | N/A | N/A — not available on Linux |

**Design implication**: library is **pure Python only** — runs on serverless without modification; classic cluster is not required.

## Claude on Databricks

Native Foundation Model API endpoints (no BYO key required):

| Endpoint | Context | Notes |
|---|---|---|
| `databricks-claude-sonnet-4-6` | 200K tokens | text + image; default `text_model` |
| `databricks-claude-opus-4-7` | 1M tokens | text + image; available as override for huge files |
| `databricks-claude-haiku-4-5` | 200K tokens | text + image; cheap; default `vision_model` for caption pre-pass |

- OpenAI-compatible Chat Completions API.
- Preferred client: `databricks_langchain.ChatDatabricks`.
- Image input: PNG / JPEG / GIF / WebP, base64, max 8000×8000 px, up to 100 images per request.
- **PDF native input is NOT supported** — PDFs are processed by rendering each page to PNG and sending image + extracted text.

## Storage

- Canonical: Unity Catalog Volumes — `/Volumes/<cat>/<sch>/<vol>/file.pptx`. Works with standard Python `open()`.
- Also accepted: Workspace files `/Workspace/...`, local absolute, relative paths, `pathlib.Path`.
- DBFS is deprecated and not supported by this library.

## Auth

- **On Databricks runtime**: workspace credentials auto-picked up. `DATABRICKS_TOKEN` env var not required.
- **Local dev**: `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars.
- **Other providers** (OpenAI, Anthropic, Google): API key env var name configurable per `ModelConfig.api_key_env`.
