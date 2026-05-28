# 05 — IR Specification

[← Index](./README.md)

IR (intermediate representation) is the contract between extractors ([06](./06-extractors.md)) and the agent ([07](./07-agent.md)). JSON-serializable. Use `TypedDict` (or `pydantic.BaseModel` for runtime validation).

Every block / shape has an `order: int` field. Agent walks in ascending `order`; extractors are responsible for sorting.

## Shared types

```python
class ImageRef(TypedDict):
    id: str                              # "img_1", "img_p3_2"
    relative_path: str                   # "raw_images/img_1.png"
    width_px: int
    height_px: int
    alt_text: NotRequired[str]
    bbox: NotRequired[BBox]
    container: ImageContainer
    neighbors: ImageNeighbors
    fetch_status: NotRequired[Literal["ok", "failed", "skipped"]]
    fetch_error: NotRequired[str]

class BBox(TypedDict):
    left: float
    top: float
    width: float
    height: float
    unit: Literal["pt", "px", "emu"]

class ImageContainer(TypedDict):
    kind: Literal["pdf_page", "pptx_slide", "xlsx_sheet", "docx_section", "html_section", "md_section"]
    index: int
    label: str | None                    # slide title, sheet name, heading text

class ImageNeighbors(TypedDict):
    before_text: str                     # ~200 chars
    after_text: str
    before_kind: str | None              # "heading_h2", "paragraph", "table", ...
    after_kind: str | None

class TextRun(TypedDict):
    text: str
    bold: NotRequired[bool]
    italic: NotRequired[bool]
    underline: NotRequired[bool]
    code: NotRequired[bool]
    hyperlink: NotRequired[str]
```

## Common block types (used by docx, html, markdown)

```python
class HeadingBlock(TypedDict):
    order: int
    type: Literal["heading"]
    level: int                           # 1-6
    runs: list[TextRun]

class ParagraphBlock(TypedDict):
    order: int
    type: Literal["paragraph"]
    style: NotRequired[str]
    list_level: NotRequired[int]
    list_kind: NotRequired[Literal["bullet", "numbered"]]
    runs: list[TextRun]

class TableBlock(TypedDict):
    order: int
    type: Literal["table"]
    rows: list[list[Cell]]               # Cell = str | int | float | None | dict (rich content)

class ImageBlock(TypedDict):
    order: int
    type: Literal["image"]
    image: ImageRef

class CodeBlock(TypedDict):
    order: int
    type: Literal["code"]
    language: str | None
    content: str

class BlockquoteBlock(TypedDict):
    order: int
    type: Literal["blockquote"]
    blocks: list[Block]                  # nested

class TextBoxBlock(TypedDict):
    order: int
    type: Literal["textbox"]
    bbox: NotRequired[BBox]
    blocks: list[Block]

class PageBreakBlock(TypedDict):
    order: int
    type: Literal["page_break"]

class RawHtmlBlock(TypedDict):
    order: int
    type: Literal["raw_html"]
    content: str                         # preserved verbatim (markdown only)
```

## PPTX

```python
class PptxIR(TypedDict):
    format: Literal["pptx"]
    source: str
    slide_count: int
    slides: list[Slide]

class Slide(TypedDict):
    index: int                           # 1-based
    title: str | None
    shapes: list[Shape]                  # sorted by (top, left)
    notes: str | None

# Shape = union dispatched by `type`
class TextShape(TypedDict):
    order: int
    type: Literal["text"]
    bbox: BBox
    is_title: bool
    paragraphs: list[Paragraph]          # list of {runs, level, list_kind}

class ImageShape(TypedDict):
    order: int
    type: Literal["image"]
    bbox: BBox
    image: ImageRef

class TableShape(TypedDict):
    order: int
    type: Literal["table"]
    bbox: BBox
    rows: list[list[Cell]]

class ChartShape(TypedDict):
    order: int
    type: Literal["chart"]
    bbox: BBox
    chart_type: Literal["bar", "column", "line", "pie", "scatter", "area", "doughnut", "other"]
    title: str | None
    axis_labels: dict
    categories: list[str]
    series: list[ChartSeries]            # [{"name": "...", "values": [...]}]

class SmartArtShape(TypedDict):
    order: int
    type: Literal["smartart"]
    bbox: BBox
    layout_kind: Literal["hierarchy", "cycle", "process", "list", "matrix", "other"]
    nodes: list[SmartArtNode]            # tree: {text, level, children}

class ConnectorShape(TypedDict):
    order: int
    type: Literal["connector"]
    bbox: BBox
    from_shape_id: str | None
    to_shape_id: str | None
    arrow_kind: Literal["straight", "elbow", "curved"]
    label: str | None

class GroupShape(TypedDict):
    order: int
    type: Literal["group"]
    bbox: BBox
    children: list[Shape]
    diagram_hint: Literal["flowchart", "none"]
```

## DOCX

```python
class DocxIR(TypedDict):
    format: Literal["docx"]
    source: str
    blocks: list[Block]                  # flat, reading order
```

Block types: any of the common block types above.

## XLSX

```python
class XlsxIR(TypedDict):
    format: Literal["xlsx"]
    source: str
    sheets: list[Sheet]

class Sheet(TypedDict):
    name: str
    index: int
    used_range: str                      # "A1:F200"
    tables: list[XlsxTable]              # auto-detected contiguous regions
    standalone_cells: list[XlsxCell]
    charts: list[ChartShape]
    images: list[XlsxImageAnchor]        # {image: ImageRef, anchor_cell: "B5"}

class XlsxTable(TypedDict):
    range: str                           # "A1:D20"
    header_row: list[str] | None
    rows: list[list[Cell]]
```

## PDF

```python
class PdfIR(TypedDict):
    format: Literal["pdf"]
    source: str
    page_count: int
    is_scanned: bool
    pages: list[PdfPage]

class PdfPage(TypedDict):
    index: int                           # 1-based
    page_image: ImageRef                 # full-page render PNG
    extracted_text: str
    text_blocks: list[PdfTextBlock]      # {order, bbox, text, is_likely_heading}
    images_on_page: list[ImageRef]
    tables: list[PdfTable]               # {bbox, rows}
```

## HTML

```python
class HtmlIR(TypedDict):
    format: Literal["html"]
    source: str
    title: str | None
    base_url: str | None
    blocks: list[Block]
```

## Markdown

```python
class MarkdownIR(TypedDict):
    format: Literal["markdown"]
    source: str
    frontmatter: dict | None
    base_dir: str | None
    blocks: list[Block]
```

## Key invariants

1. `order` is the source of truth for reading order. Extractor sorts; agent never re-sorts.
2. Image bytes never live inside IR; only `ImageRef.relative_path`. Bytes are written to the agent's virtual FS at `raw_images/<id>.png`.
3. Text formatting is preserved as `TextRun` flags. Agent decides whether to render `**bold**`, `*italic*`, `` `code` ``, `[link](url)`.
4. Merged cells in tables are resolved by **expanding** the value into all covered cells.
5. pptx group / SmartArt nested children stay nested; agent walks recursively.

## Token estimation

```python
def estimate_ir_tokens(ir: dict) -> int:
    return len(json.dumps(ir, ensure_ascii=False)) // 4
```

Used by the chunker to decide split points; also surfaced in `ConvertResult.metadata`.
