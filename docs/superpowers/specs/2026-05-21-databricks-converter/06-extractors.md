# 06 — Extractors

[← Index](./README.md)

Every extractor implements:

```python
class Extractor(Protocol):
    format: ClassVar[str]
    def extract(self, source: Path) -> ExtractResult: ...

@dataclass
class ExtractResult:
    ir: dict
    images: dict[str, bytes]             # {"raw_images/img_1.png": b"..."}
    warnings: list[str]
```

IR schemas: see [05-ir-spec.md](./05-ir-spec.md).

## 6.1 `extractors/xlsx.py`

**Library**: `openpyxl` (`data_only=True` → formulas surface as cached values).

**Logic**
- Iterate `wb.worksheets`; for each sheet detect contiguous tables via flood-fill heuristic. Remaining cells go to `standalone_cells`.
- Charts via `ws._charts`: extract `chart_type`, `title`, `categories`, `series`.
- Drawings via `ws._images` and parsing `xl/drawings/drawing*.xml` directly with `zipfile + lxml` for non-image shapes.
- Merged cells: expand value to all covered cells.

**Edge cases**
- Formula cells with `data_only=True` may surface `None` if file was never opened in Excel — surface as warning.
- Hidden sheets / rows / columns: skipped + warning.
- Pivot tables: emitted as regular tables (data already pivoted).

**`detect_tables` heuristic**
1. Find contiguous non-empty regions (flood-fill from each non-empty cell).
2. A region becomes a table if: ≥ 2 rows, ≥ 2 cols, AND top row is styled (bold / fill) OR per-column data types are homogeneous.
3. Non-matching regions → `standalone_cells`.

## 6.2 `extractors/docx.py`

**Library**: `python-docx`.

**Critical detail**: `doc.paragraphs` and `doc.tables` are separate lists — order is lost. Iterate `doc.element.body` at the XML level to preserve interleaving of paragraphs / tables / drawings.

**Logic**
- Walk body XML children in order; dispatch by tag (`w:p`, `w:tbl`, `w:drawing`).
- Headings: `paragraph.style.name in ("Heading 1", ...)` → `HeadingBlock(level=N)`.
- Lists: `numPr` element → `list_level` + `list_kind`.
- Inline images: `run._r.findall('.//pic:pic')` → blob from `image.part.blob`.
- Floating textboxes: `<w:txbxContent>` → recursive extraction into `TextBoxBlock.blocks`.
- Code-styled paragraphs → `CodeBlock`.

**Edge cases**
- Headers / footers: skipped in v1.
- Track changes / comments: skipped.
- Equations (OMML): `[Equation: <raw text>]` placeholder; LaTeX conversion deferred.

## 6.3 `extractors/pptx.py`

**Library**: `python-pptx`.

**Logic**
- For each slide, iterate `slide.shapes`; dispatch on `shape.has_chart`, `shape.shape_type`, `shape.has_table`, `shape.has_text_frame`, `MSO_SHAPE_TYPE.GROUP`, `is_connector(shape)`.
- After per-slide collection, sort by `(bbox.top, bbox.left)` → reading order.
- Speaker notes captured separately on slide.

**SmartArt** (python-pptx has no first-class support):
- SmartArt = `<dgm:relIds>` referencing `diagrams/data{N}.xml` inside the zip.
- Open pptx as zip, parse `diagrams/data{N}.xml` with lxml.
- Build node tree from `<dgm:ptLst>` + `<dgm:cxnLst>`.
- Map `layout_kind` from `diagrams/layout{N}.xml` `<dgm:layoutNode name="...">`.

**Connector detection**:
- `shape.shape_type == MSO_SHAPE_TYPE.LINE` and connector subtypes.
- `shape.begin_connection_shape_id` / `end_connection_shape_id` for endpoints.

**`detect_flowchart(children)`**: returns `"flowchart"` if `len(connectors) >= 2` and all connectors have both endpoints resolved; else `"none"`.

**Edge cases**
- Animations / transitions: skipped.
- Hidden slides: skipped + warning.
- Master / layout unfilled placeholders: skipped.

## 6.4 `extractors/pdf.py`

**Library**: `pymupdf` (a.k.a. `fitz`) — pure Python via pre-built native wheel; works on Databricks serverless.

**Logic per page**
- Render full page → PNG at 150 dpi → `pages[i].page_image` (used by vision when text is sparse).
- `page.get_text("dict")` → text blocks with bbox; sort blocks by reading order (pymupdf provides this).
- `page.get_images()` → cropped embedded images.
- `page.find_tables()` → detected tables.
- Heading heuristic: font size > median per page.

**Scanned detection**: per-page text density (chars per page area). If `< 50 chars` average → mark page `is_scanned=True`; agent relies on `page_image` for OCR via vision model.

**Edge cases**
- Encrypted PDF: raise `EncryptedFileError`.
- Rotated pages: pymupdf handles rotation automatically.
- Mixed scanned + text: per-page detection, not whole-doc.

## 6.5 `extractors/html.py`

**Library**: `lxml.html` + `beautifulsoup4`.

**Logic**
- Strip `<script>`, `<style>`, `<noscript>`, comments.
- Walk `body` in document order, emit `Block`s by tag (`h1..h6`, `p`, `ul`/`ol`, `table`, `img`, `pre`, `blockquote`).
- For `<img>`: handle three `src` forms per §6.5.1.

### 6.5.1 Image src handling

| Form | Behavior |
|---|---|
| `data:image/...;base64,...` | Decode directly |
| Relative (`./img.png`, `images/foo.jpg`) | Resolve vs HTML file location → read from disk |
| Absolute URL (`https://...`) | HTTP GET with `fetch_timeout_seconds`, 1 retry. Disabled if `fetch_remote_images=False`. |

On fetch failure: keep `ImageRef` with `fetch_status="failed"` + fallback `alt_text`; agent emits `[Image: <alt_text> — source unavailable]`. Warning recorded.

**Edge cases**
- CSS-positioned content (absolute / flex): document order used, not visual order (documented limitation).
- Embedded SVG: serialize as `.svg`; passed to vision model.
- `<iframe>`: skipped + warning.
- MathML: text placeholder.
- Encoding: auto-detect via meta charset, fallback `chardet`.

## 6.6 `extractors/markdown.py`

**Library**: `markdown-it-py` with `table` and `strikethrough` plugins.

**Logic**
- Parse with GFM-like options.
- Extract frontmatter (YAML between `---` markers) into `ir["frontmatter"]`.
- Walk tokens → emit `HeadingBlock`, `ParagraphBlock`, `ImageBlock`, `TableBlock`, `CodeBlock`, `BlockquoteBlock`, `RawHtmlBlock` (for inline HTML).
- Image refs use same fetch policy as HTML (§6.5.1), resolved vs `source.parent`.
- Link references resolved.

The markdown extractor's job is **lossless representation** — IR mirrors source structure so the agent can keep most things verbatim. The agent's role on markdown is normalization + image-caption replacement, not generation; see [`MAIN_PROMPT_MARKDOWN`](./07-agent.md#main_prompt_markdown).

## 6.7 Image normalization

All extracted image bytes are normalized to PNG before storage in IR `images` dict. Images larger than 2048×2048 are resized down with PIL/Pillow to balance vision-OCR quality with token cost.
