# any2md — Design Spec

- **Status**: Draft, awaiting user review
- **Date**: 2026-05-21 (spec dir name kept for stable links)
- **Owner**: nqt068@gmail.com
- **Deployment targets**: any Python 3.11+ host; Databricks serverless is a first-class supported target (the pure-Python constraint enables it).

`any2md` is a Python library + agent that converts office and web documents (xlsx, docx, pptx, pdf, html, md) into structured markdown for a knowledge base. It is general-purpose — not a Databricks-only project — but every dependency stays pure-Python so the Databricks serverless path works unmodified.

Hybrid architecture: deterministic pure-Python extractors emit an intermediate representation (IR), then a deepagent orchestrates rendering with subagent-isolated quality review and a parallelized image-captioning pre-pass. User-facing summary in [../../../../README.md](../../../../README.md).

## Index

| # | File | Topic |
|---|---|---|
| 01 | [Goals & Scope](./01-goals-and-scope.md) | Context, supported formats, quality goals, **non-goals** |
| 02 | [Platform Constraints](./02-platform.md) | Databricks compute + native Claude endpoints |
| 03 | [Architecture & Repo Layout](./03-architecture.md) | High-level data flow, invariants, repo structure, dependencies |
| 04 | [API Surface](./04-api-surface.md) | `convert()`, `ConvertOptions`, `ModelConfig`, `ConvertResult`, errors, usage examples |
| 05 | [IR Specification](./05-ir-spec.md) | TypedDict schemas per format + shared types |
| 06 | [Extractors](./06-extractors.md) | Per-format extractor logic + edge cases |
| 07 | [Agent](./07-agent.md) | Topology, virtual FS, caption pre-pass, chunking, tools, subagent, prompts, LLM wiring |
| 08 | [Errors & Observability](./08-errors-and-observability.md) | Error hierarchy, retry, degradation, logging, metrics, caching, safety caps |
| 09 | [Testing](./09-testing.md) | Pyramid, fixtures, CI, benchmarks |
| 10 | [Open Questions & Approval](./10-open-questions.md) | Unresolved items + sign-off gate |
| 11 | [Schema Deltas, Cleanup & Chunking Rules](./11-schema-and-rules.md) | Schema deviations vs §05, cleanup rules per format, chunking contract, decisions log. (Live status snapshot → repo-root [STATE.md](../../../../STATE.md)) |

## Reading order

For first review: read 01 → 02 → 03 → 04 → 07 → 05 → 06 → 08 → 09 → 10.

For implementation (after approval): 03 (repo layout) → 05 (IR) → 06 (extractors, one at a time) → 07 (agent) → 08 (errors) → 09 (testing).

## Next step

Once approved, transition to `writing-plans` skill to produce a phased implementation plan referencing these files.
