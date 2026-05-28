"""IR (Intermediate Representation) TypedDict schemas.

See docs/superpowers/specs/2026-05-21-databricks-converter/05-ir-spec.md
"""
from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict


# ---------- Shared types ----------

class BBox(TypedDict):
    left: float
    top: float
    width: float
    height: float
    unit: Literal["pt", "px", "emu"]


class ImageContainer(TypedDict):
    kind: Literal["pdf_page", "pptx_slide", "xlsx_sheet", "docx_section", "html_section", "md_section"]
    index: int
    label: str | None


class ImageNeighbors(TypedDict):
    before_text: str
    after_text: str
    before_kind: str | None
    after_kind: str | None


class ImageRef(TypedDict):
    id: str
    relative_path: str
    width_px: int
    height_px: int
    alt_text: NotRequired[str]
    bbox: NotRequired[BBox]
    container: ImageContainer
    neighbors: ImageNeighbors
    fetch_status: NotRequired[Literal["ok", "failed", "skipped"]]
    fetch_error: NotRequired[str]


class TextRun(TypedDict):
    text: str
    bold: NotRequired[bool]
    italic: NotRequired[bool]
    underline: NotRequired[bool]
    code: NotRequired[bool]
    hyperlink: NotRequired[str]


# ---------- Common block types (docx, html, markdown) ----------

class HeadingBlock(TypedDict):
    order: int
    type: Literal["heading"]
    level: int
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
    rows: list[list[Any]]


class ListBlock(TypedDict):
    order: int
    type: Literal["list"]
    list_kind: Literal["bullet", "numbered"]
    list_level: int
    items: list[list[TextRun]]                       # each item = list of runs


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
    blocks: list[Any]


class TextBoxBlock(TypedDict):
    order: int
    type: Literal["textbox"]
    bbox: NotRequired[BBox]
    blocks: list[Any]


class PageBreakBlock(TypedDict):
    order: int
    type: Literal["page_break"]


class RawHtmlBlock(TypedDict):
    order: int
    type: Literal["raw_html"]
    content: str


class FigureBlock(TypedDict):
    order: int
    type: Literal["figure"]
    image: ImageRef
    caption: NotRequired[list[TextRun]]              # from <figcaption>


class DividerBlock(TypedDict):
    order: int
    type: Literal["divider"]                         # <hr> / thematic break


# Block = union of any of the above. Kept as Any in TypedDict context.
Block = dict[str, Any]


# ---------- PPTX-specific shapes ----------

class Paragraph(TypedDict):
    runs: list[TextRun]
    level: NotRequired[int]              # bullet depth
    list_kind: NotRequired[Literal["bullet", "numbered"]]
    alignment: NotRequired[Literal["left", "center", "right", "justify"]]


class TableCell(TypedDict):
    paragraphs: list[Paragraph]
    text: str                           # flat fallback for markdown export
    rowspan: NotRequired[int]
    colspan: NotRequired[int]


class TextShape(TypedDict):
    order: int
    type: Literal["text"]
    bbox: BBox
    paragraphs: list[Paragraph]


class ImageShape(TypedDict):
    order: int
    type: Literal["image"]
    bbox: BBox
    image: ImageRef


class TableShape(TypedDict):
    order: int
    type: Literal["table"]
    bbox: BBox
    rows: list[list[Any]]                # legacy flat strings
    rows_rich: NotRequired[list[list[TableCell]]]   # per-cell paragraphs/runs


class ChartSeries(TypedDict):
    name: str | None
    values: list[Any]


class ChartShape(TypedDict):
    order: int
    type: Literal["chart"]
    bbox: BBox
    chart_type: Literal["bar", "column", "line", "pie", "scatter", "area", "doughnut", "other"]
    title: str | None
    axis_labels: dict[str, str]
    categories: list[str]
    series: list[ChartSeries]


class SmartArtNode(TypedDict):
    text: str
    level: int
    children: list[Any]                  # list[SmartArtNode]


class SmartArtShape(TypedDict):
    order: int
    type: Literal["smartart"]
    bbox: BBox
    layout_kind: Literal["hierarchy", "cycle", "process", "list", "matrix", "other"]
    nodes: list[SmartArtNode]


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
    children: list[Any]                  # list[Shape]
    diagram_hint: Literal["flowchart", "none"]


# Shape = union of pptx shape types. Kept as Any.
Shape = dict[str, Any]


# ---------- Per-format IR ----------

class SlideComment(TypedDict):
    author: str | None
    text: str
    created: NotRequired[str]


class Slide(TypedDict):
    index: int
    title: str | None
    shapes: list[Shape]
    notes: str | None
    comments: NotRequired[list[SlideComment]]


class PptxIR(TypedDict):
    format: Literal["pptx"]
    source: str
    slide_count: int
    slides: list[Slide]


class DocxIR(TypedDict):
    format: Literal["docx"]
    source: str
    blocks: list[Block]


class XlsxTable(TypedDict):
    range: str
    header_row: list[str] | None
    rows: list[list[Any]]


class XlsxImageAnchor(TypedDict):
    image: ImageRef
    anchor_cell: str                                  # "from" cell, e.g. "B4"
    anchor_range: NotRequired[str]                    # "B4:F10" for twoCellAnchor
    anchor_kind: NotRequired[Literal["one_cell", "two_cell", "absolute"]]
    extent_pt: NotRequired[dict[str, float]]          # {cx, cy} in points


class CellHyperlink(TypedDict):
    coordinate: str                                  # e.g. "B12"
    target: str                                      # url, file path, or sheet anchor
    display: NotRequired[str]                        # cell text


class CellComment(TypedDict):
    coordinate: str
    author: str | None
    text: str


class DrawingShape(TypedDict):
    name: str
    anchor_range: str | None
    geom: str | None                                  # prstGeom name (rect, ellipse, arrow, etc.)
    text: str | None
    shape_kind: Literal["textbox", "arrow", "connector", "other"]


class Sheet(TypedDict):
    name: str
    index: int
    used_range: str
    tables: list[XlsxTable]
    standalone_cells: list[Any]
    charts: list[ChartShape]
    images: list[XlsxImageAnchor]
    smartart: list[SmartArtShape]                    # SmartArt diagrams anchored on this sheet
    cell_hyperlinks: NotRequired[list[CellHyperlink]]
    cell_comments: NotRequired[list[CellComment]]
    drawing_shapes: NotRequired[list[DrawingShape]]  # text boxes / arrows / connectors


class XlsxIR(TypedDict):
    format: Literal["xlsx"]
    source: str
    sheets: list[Sheet]


class PdfTextBlock(TypedDict):
    order: int
    bbox: BBox
    text: str
    is_likely_heading: bool


class PdfTable(TypedDict):
    bbox: BBox
    rows: list[list[Any]]


class PdfLink(TypedDict):
    bbox: BBox
    kind: Literal["uri", "goto", "launch", "named", "other"]
    uri: NotRequired[str]                            # for kind="uri"
    target_page: NotRequired[int]                    # for kind="goto", 1-based
    text: NotRequired[str]                           # text overlapping the link rect


class PdfOutlineEntry(TypedDict):
    level: int
    title: str
    page: int                                        # 1-based, -1 if unknown


class PdfPage(TypedDict):
    index: int
    page_image: ImageRef
    extracted_text: str
    text_blocks: list[PdfTextBlock]
    images_on_page: list[ImageRef]
    tables: list[PdfTable]
    links: NotRequired[list[PdfLink]]                # URI / goto / launch annotations


class PdfIR(TypedDict):
    format: Literal["pdf"]
    source: str
    page_count: int
    is_scanned: bool
    pages: list[PdfPage]
    metadata: NotRequired[dict[str, Any]]            # title, author, subject, keywords, producer
    outline: NotRequired[list[PdfOutlineEntry]]      # bookmarks / TOC


class HtmlIR(TypedDict):
    format: Literal["html"]
    source: str
    title: str | None
    base_url: str | None
    blocks: list[Block]


class MarkdownIR(TypedDict):
    format: Literal["markdown"]
    source: str
    frontmatter: dict[str, Any] | None
    base_dir: str | None
    blocks: list[Block]


IR = PptxIR | DocxIR | XlsxIR | PdfIR | HtmlIR | MarkdownIR
