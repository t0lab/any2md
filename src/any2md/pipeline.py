"""End-to-end pipeline helpers — extract + clean.

Routes a source path to the right extractor by extension, runs the extractor,
then applies `clean_ir`. Returns the cleaned IR + images + warnings without
touching the filesystem (callers persist if they want).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .detect import detect_format
from .extractors.base import Extractor, ExtractResult
from .extractors.docx import DocxExtractor
from .extractors.html import HtmlExtractor
from .extractors.markdown import MarkdownExtractor
from .extractors.pdf import PdfExtractor
from .extractors.pptx import PptxExtractor
from .extractors.xlsx import XlsxExtractor
from .ir_clean import clean_ir

_EXTRACTORS: dict[str, Extractor] = {
    "xlsx": XlsxExtractor(),
    "docx": DocxExtractor(),
    "pptx": PptxExtractor(),
    "pdf": PdfExtractor(),
    "html": HtmlExtractor(),
    "markdown": MarkdownExtractor(),
}


@dataclass
class CleanResult:
    """Output of `extract_and_clean` — cleaned IR + images + warnings + format."""

    ir: dict[str, Any]
    images: dict[str, bytes] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    format: str = ""


def extract_and_clean(source: Path) -> CleanResult:
    fmt = detect_format(source)
    extractor = _EXTRACTORS.get(fmt)
    if extractor is None:
        raise NotImplementedError(f"No extractor wired for format {fmt!r} (source={source})")
    raw: ExtractResult = extractor.extract(source)
    cleaned = clean_ir(raw.ir)
    return CleanResult(ir=cleaned, images=raw.images, warnings=raw.warnings, format=fmt)
