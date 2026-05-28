# 01 — Goals & Scope

[← Index](./README.md)

## Context

Build `any2md` — a Python library and agent that converts office and web documents into structured markdown for a knowledge base. The library is **general-purpose**: it must run on any host with Python 3.11+, accept relative paths for local-dev workflows, and have no external backend server.

It must also run unmodified on **Databricks compute** (one of our deployment targets). Databricks serverless rules out MS Office binaries on Linux and bans `subprocess`/`apt-get`/init scripts, so the entire library is pure-Python. That constraint is what protects the Databricks path while keeping local dev painless — it is not the project's purpose.

## Supported input formats (v1)

- `.xlsx` / `.xlsm` (Excel)
- `.docx` / `.docm` (Word)
- `.pptx` / `.pptm` (PowerPoint)
- `.pdf`
- `.html` / `.htm`
- `.md` / `.markdown`

## Quality goals

1. **Preserve reading order** — top-left → bottom-right per page/slide; never reorder content; never skip blocks.
2. **Preserve image position** — image captions emitted at the exact reading-order position they occupied in the source; captions include traceability metadata (container kind, index, container label).
3. **Caption every image with surrounding context** — captions are 1-2 sentences in the appropriate language (auto-detect or forced), informed by neighbor blocks before/after.
4. **Handle diagrams** — charts → markdown table + description; SmartArt hierarchy/list → nested bullet list; SmartArt cycle/process and connector-grouped shapes → Mermaid flowchart.
5. **Multi-language tolerant** — body text preserved verbatim (vi + en commonly mixed); generated text (captions, descriptions) follows `caption_language` setting.

## Non-goals (v1)

Explicitly out of scope. Revisit when there is concrete demand.

| Non-goal | Reason |
|---|---|
| `.doc`, `.ppt`, `.xls` (legacy binary OLE) | No reliable pure-Python parser; needs LibreOffice. |
| `.rtf`, `.odp`, `.ods`, `.odt` | Low priority for Vietnamese KB. |
| Markdown → other formats (reverse direction) | Different project. |
| Streaming output | Quality review requires full doc. |
| In-memory bytes input | File path API sufficient for v1. |
| Per-image-language mixing within one file | `caption_language` is global. |
| LaTeX equation conversion (OMML → LaTeX) | Complex parser; equations rare in KB. |
| Animations / transitions in pptx | No KB value. |
| Header / footer in docx | Mostly boilerplate. |
| Track changes / comments in docx | Out of scope for KB. |
| PDF form fields | Form data typically extracted separately. |
| OCR confidence scoring | Claude vision does not expose confidence. |
| Multi-modal output (md + json + html) | YAGNI — markdown is the KB target. |
| Custom output templates | IR determines structure; no template engine. |
| GUI / Streamlit app | Library / notebook is sufficient. |
| Caching across `convert()` calls | Caller's responsibility. |
| File-arrival job triggers, Model Serving endpoint, Databricks App | Library is consumed by notebooks / scripts; deployment shapes deferred. |
