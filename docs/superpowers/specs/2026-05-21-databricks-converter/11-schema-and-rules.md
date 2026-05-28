# 11 — Schema Deltas, Cleanup & Chunking Rules

[← Index](./README.md)

Design-side documentation for the post-extraction pipeline: schema deltas from [05-ir-spec.md](./05-ir-spec.md), per-format cleanup rules, chunking contract, and the running decisions log.

Current pipeline **status** (coverage, sample audit, known gaps, regeneration commands) lives in the repo-root [STATE.md](../../../../STATE.md) and is updated as work progresses. This file holds the **rules** that survive across status snapshots.

- **Date**: 2026-05-22
- **Scope**: design rules + decisions for [`ir.py`](../../../../src/any2md/ir.py), [`ir_clean.py`](../../../../src/any2md/ir_clean.py), [`ir_chunk.py`](../../../../src/any2md/ir_chunk.py)

## 11.1 Schema deviations from [05-ir-spec.md](./05-ir-spec.md)

The implemented schema has evolved during validation against real fixtures. Changes live in [`src/any2md/ir.py`](../../../../src/any2md/ir.py). Summary of deltas vs the original spec:

### Unit standardization (2026-05-22)

All `BBox.unit` and image extents are now **`px` @ 96 DPI** across pptx / xlsx / pdf. Image dimensions (`width_px` / `height_px`) were already in px — bbox is now consistent.

| Source | Native unit | Conversion |
|---|---|---|
| pptx (python-pptx) | EMU | `px = EMU / 9525` |
| xlsx (openpyxl) | EMU | `px = EMU / 9525` |
| pdf (pymupdf) | pt | `px = pt × 4/3` |

`BBox.unit` literal is `"px"` in practice. The schema still accepts `"pt"` / `"emu"` for future flexibility.

### TextShape (pptx)

- ❌ **Removed** `is_title: bool` — was unreliable (placeholder type 14 = BODY was incorrectly treated as title; free-form text boxes never matched). Slide-level `title` string remains; per-shape signal can be re-derived heuristically by the markdown renderer if needed.

### Paragraph (pptx)

- ➕ Added `alignment: Literal["left", "center", "right", "justify"]` — parsed from `<a:pPr algn>`.
- ➕ `list_kind` now actually populated from `<a:buChar>` / `<a:buAutoNum>` (was schema-only previously).

### TableShape (pptx)

- ➕ Added `rows_rich: list[list[TableCell]]` alongside legacy `rows: list[list[str]]`. Each `TableCell` carries `paragraphs` (with runs/bold/italic/hyperlink), `text` (flat fallback), optional `rowspan` / `colspan`.

### Slide (pptx)

- ➕ Added `comments: list[SlideComment]` — parsed from `ppt/commentAuthors.xml` + `ppt/comments/commentN.xml` resolved via slide rels.

### Sheet (xlsx)

- ➕ Added `cell_hyperlinks: list[CellHyperlink]` — `{coordinate, target, display}`.
- ➕ Added `cell_comments: list[CellComment]` — `{coordinate, author, text}`.
- ➕ Added `drawing_shapes: list[DrawingShape]` — non-SmartArt drawing children: `xdr:sp` (text boxes / autoshapes) and `xdr:cxnSp` (connectors). Each carries `{name, anchor_range, geom, text, shape_kind}`.
- ➕ Added `smartart: list[SmartArtShape]` (already added earlier this iteration).

### XlsxImageAnchor

- ➕ Extended from `{image, anchor_cell}` only → adds `anchor_range` (only for `twoCellAnchor`), `anchor_kind` (`one_cell` / `two_cell` / `absolute`), and `extent_px` (`{cx, cy}` for `oneCellAnchor` / `absoluteAnchor`).

### PdfPage / PdfIR

- ➕ Per-page `links: list[PdfLink]` — `{bbox, kind, uri?, target_page?, text?}` covering URI, internal goto, file launch, named destinations.
- ➕ `images_on_page[].bbox` — placement bbox (from `page.get_image_rects(xref)`). Distinct from `width_px` / `height_px` which is the native PNG resolution.
- ➕ Doc-level `metadata: dict` — title / author / subject / keywords / creator / producer / creation/mod dates from `doc.metadata`.
- ➕ Doc-level `outline: list[PdfOutlineEntry]` — bookmarks via `doc.get_toc(simple=True)`.
- One image may emit multiple entries if its xref appears at multiple positions on a page. IDs are suffixed `_1`, `_2`, etc; `relative_path` is shared.

### HTML blocks

- 🐛 **Fixed** schema mismatch: previous code emitted `{"type": "list", ...}` which did not exist in the schema. Lists now expand into per-li `ParagraphBlock` with `list_kind` + `list_level` (matches schema).
- ➕ Added nested list support — inner `<ul>`/`<ol>` increment `list_level`.
- ➕ Added `FigureBlock` (`<figure>` + `<figcaption>`).
- ➕ Added `DividerBlock` (`<hr>`).
- ➕ Added `<dl>` handling — `<dt>` runs marked bold, `<dd>` plain.
- ➕ Preserved `<br>` as `\n` runs inside paragraphs.

### Net-new shared types

`ListBlock`, `FigureBlock`, `DividerBlock`, `TableCell`, `CellHyperlink`, `CellComment`, `DrawingShape`, `SlideComment`, `PdfLink`, `PdfOutlineEntry`.

## 11.2 Decisions log

| Date | Decision | Rationale |
|---|---|---|
| 2026-05-22 | Drop `is_title` from `TextShape` | Method (placeholder type check) was buggy + irrelevant for free-form slides. `slide.title` covers the slide-level need; per-shape title detection deferred to agent. |
| 2026-05-22 | Unify all bbox units to `px @ 96 DPI` | EMU produced 7-digit integers; pt was OK but mismatched `width_px` / `height_px` on images. `px` makes bbox directly comparable with image dimensions. |
| 2026-05-22 | Emit per-occurrence IR entries when one PDF image xref appears multiple times on a page | Different bboxes = different placements; reading order needs each one tracked separately. |
| 2026-05-22 | HTML lists become `ParagraphBlock` with `list_kind` + `list_level` instead of a `ListBlock` wrapper | Aligns with schema's existing `ParagraphBlock` fields; downstream markdown renderer is simpler (no special "list" handling). |
| 2026-05-22 | Keep `images: dict[str, bytes]` separate from IR JSON | IR stays text-pure for caching / diffing; bytes go to the agent's virtual FS at `raw_images/<id>.png`. (Already in spec — reaffirmed during implementation.) |
| 2026-05-22 | Cleanup as a **separate pass** (`ir_clean.py`), not inlined into extractors | Raw IR stays maximally verbose for debugging / auditing; cleanup rules will evolve as we wire the agent and learn what it actually needs; can A/B agent quality between full vs cleaned IR. |
| 2026-05-22 | Drop `TableShape.rows` (outer flat list); keep `rows_rich` only | `rows_rich[][].text` is the per-cell flat fallback — consumers get plain text without walking paragraphs. `rows_rich` also carries `rowspan` / `colspan` which `rows` lacks. Saves ~4.4 KB × 2 in the pptx sample. |
| 2026-05-22 | Strip `ImageRef.alt_text` when it matches a filesystem path pattern | The pptx sample leaked `/home/claude/work/images/*.png` paths from its authoring environment. Pattern: starts with `/` or `\\` and ends with image extension. |
| 2026-05-22 | Token-based chunking via `tiktoken.cl100k_base`, default 30K tokens | Char count is faster but doesn't map to context limits. cl100k_base is OpenAI's BPE (not Claude's) — accurate within ~10-15% for our content; sufficient as a budget gate. 30K leaves ~170K headroom on Sonnet/Haiku 200K. |
| 2026-05-22 | Oversize single unit emitted alone with `truncated=True` (no in-unit splitting in phase 1) | Most slides / pages will fit. In-unit splitting (by shape / text_block / table) adds complexity around bbox / reading-order reconstruction; defer until a real sample triggers it. |

## 11.3 IR cleanup ([`src/any2md/ir_clean.py`](../../../../src/any2md/ir_clean.py))

Raw IR keeps everything the extractor knows for debugging / auditing. `clean_ir(ir)` strips redundancy before feeding the agent.

### Rules (per-format)

**Universal:** drop keys whose value is `None` / `""` / `[]` / `{}` after recursion.

**pptx:** drop `bbox.unit`, `TableShape.rows` (duplicate of `rows_rich[][].text`), `Paragraph.alignment` (any value), empty `Paragraph.runs`, `ImageRef.alt_text` when it's a filesystem path (authoring-env leak), `ImageShape.image.bbox` (duplicate of parent shape bbox), `ChartShape.axis_labels` when `{}`, `ConnectorShape` when `from_shape_id` / `to_shape_id` / `label` are all null. Keep `TextShape.bbox` (needed for position correction), `order`, `ImageContainer.label`, `GroupShape` as-is.

**xlsx:** drop `bbox.unit`, `XlsxTable.header_row` (== `rows[0]`), empty arrays (`cell_hyperlinks` / `cell_comments` / `drawing_shapes` / `smartart` / `charts` / `images`). Keep `extent_px`, `anchor_kind`, `standalone_cells[].kind`.

**pdf:** drop `bbox.unit`, `PdfPage.extracted_text` (duplicate of joined `text_blocks[].text`), `PdfTextBlock.is_likely_heading` (both true & false), noise metadata (`creator` / `producer` / `creationDate` / `modDate`), empty `tables` / `links` / `images_on_page`. Keep `text_blocks[].bbox`, `links[].bbox`.

**html:** drop `bbox.unit`, whitespace-only `runs` with no formatting, paragraph blocks that become empty after run cleanup.

Verification results (size reduction per sample) live in [STATE.md](../../../../STATE.md).

## 11.4 Chunking ([`src/any2md/ir_chunk.py`](../../../../src/any2md/ir_chunk.py))

`chunk_ir(ir, max_tokens=30_000, max_images=80)` splits cleaned IR into agent-sized chunks by natural unit.

### Strategy

- **Unit per format:** pptx → slide, pdf → page, xlsx → sheet, html / markdown / docx → top-level block
- **Algorithm:** greedy packing — accumulate units until adding the next would exceed `max_tokens` or `max_images`, then flush and start a new chunk
- **Oversize unit (single slide/page/sheet exceeds caps):** emit alone with `truncated=True` + log a warning. No in-unit splitting in this phase.
- **Token counting:** `tiktoken.cl100k_base` (OpenAI BPE). Not Claude's tokenizer — counts within ~10-15% for typical content. Sufficient as a budget gate; do not use for billing.

### `IRChunk` shape

```python
{
  "chunk_index": int,           # 0-based
  "total_chunks": int,
  "unit_kind": "slide"|"page"|"sheet"|"block",
  "unit_start": int,            # inclusive — native index (1-based for slide/page) or array pos (block)
  "unit_end": int,              # inclusive
  "token_count": int,
  "image_count": int,
  "truncated": bool,
  "ir": dict,                   # valid IR — same `format`, subset of units, top-level metadata preserved
}
```

Verification results (token counts per sample) live in [STATE.md](../../../../STATE.md).
