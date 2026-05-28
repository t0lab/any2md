"""Extractor protocol and shared types."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Protocol


@dataclass
class ExtractResult:
    ir: dict
    images: dict[str, bytes] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class Extractor(Protocol):
    format: ClassVar[str]

    def extract(self, source: Path) -> ExtractResult: ...
