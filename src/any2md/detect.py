"""Format detection from extension (and magic bytes when needed)."""
from __future__ import annotations

from pathlib import Path
from typing import Literal


Format = Literal["xlsx", "docx", "pptx", "pdf", "html", "markdown"]


_EXTENSION_MAP: dict[str, Format] = {
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".docx": "docx",
    ".docm": "docx",
    ".pptx": "pptx",
    ".pptm": "pptx",
    ".pdf": "pdf",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
}


class UnsupportedFormatError(ValueError):
    def __init__(self, ext: str, source: Path):
        super().__init__(f"Unsupported format: {ext!r} for {source}")
        self.ext = ext
        self.source = source


def detect_format(source: Path) -> Format:
    ext = source.suffix.lower()
    fmt = _EXTENSION_MAP.get(ext)
    if fmt is None:
        raise UnsupportedFormatError(ext, source)
    return fmt
