# 10 — Open Questions & Approval

[← Index](./README.md)

## Open questions

To resolve during implementation, not blocking design approval.

1. **SmartArt XML schema variation**: PowerPoint version differences in `dgm:` schema. Test with pptx exported from PowerPoint 2016+, M365, Keynote, Google Slides.
2. **PDF table detection accuracy on Vietnamese forms**: pymupdf `find_tables()` may underperform; `pdfplumber.find_tables()` as fallback.
3. **Mermaid syntax escaping**: shape text containing `[`, `]`, `"`, `<`, `>` must be escaped per Mermaid grammar; define helper in agent prompt or tool wrapper.
4. **Quality reviewer hallucination**: monitor whether reviewer adds content not present in IR despite prompt guards. Add an automated post-check that compares output block count vs IR block count.
5. **Chunk-to-chunk continuity**: validate `previous_tail.md` approach on 200+ slide decks for duplicate-heading prevention.
6. **Prompt cache effectiveness**: verify token savings when chunks share system prompt but IR varies.

## Approval gate

Once the user approves this spec set, the next step is the `writing-plans` skill to produce a phased implementation plan referencing these files. Suggested phases (to be refined by `writing-plans`):

1. **Phase 0 — Scaffolding**: pyproject, repo skeleton, base extractor protocol, errors, IR types, paths/detect, llm factory, fixture build script.
2. **Phase 1 — Extractors**: one extractor per increment (xlsx → docx → pptx → pdf → html → md), each with unit + golden tests, no LLM dependency.
3. **Phase 2 — Caption pre-pass & chunking**: pure-Python infrastructure (rate limiter, chunker) with unit tests.
4. **Phase 3 — Agent**: tools, prompts, orchestrator, quality reviewer subagent, with mocked-LLM unit tests.
5. **Phase 4 — End-to-end**: integration tests with real Databricks endpoint, smoke pass, benchmark baseline.
