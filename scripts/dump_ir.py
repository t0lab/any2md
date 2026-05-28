"""Run extractors on samples/ and dump IR JSON + images to samples/_ir/.

Usage:
    py scripts/dump_ir.py
    py scripts/dump_ir.py samples/specific_file.pptx
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path

# Make src/ importable when running from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from any2md.detect import detect_format, UnsupportedFormatError  # noqa: E402
from any2md.extractors.base import ExtractResult  # noqa: E402
from any2md.extractors.docx import DocxExtractor  # noqa: E402
from any2md.extractors.html import HtmlExtractor  # noqa: E402
from any2md.extractors.markdown import MarkdownExtractor  # noqa: E402
from any2md.extractors.pdf import PdfExtractor  # noqa: E402
from any2md.extractors.pptx import PptxExtractor  # noqa: E402
from any2md.extractors.xlsx import XlsxExtractor  # noqa: E402


EXTRACTORS = {
    "xlsx": XlsxExtractor(),
    "docx": DocxExtractor(),
    "pptx": PptxExtractor(),
    "pdf": PdfExtractor(),
    "html": HtmlExtractor(),
    "markdown": MarkdownExtractor(),
}


def dump_one(source: Path, out_dir: Path) -> None:
    print(f"\n=== {source.name} ===")
    try:
        fmt = detect_format(source)
    except UnsupportedFormatError as e:
        print(f"  SKIP: {e}")
        return

    extractor = EXTRACTORS.get(fmt)
    if extractor is None:
        print(f"  SKIP: no extractor for format {fmt!r}")
        return

    stem = f"{source.stem}.{fmt}"
    sample_out_dir = out_dir / stem
    sample_out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = sample_out_dir / "raw_images"
    images_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    try:
        result: ExtractResult = extractor.extract(source)
    except Exception as e:
        print(f"  FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        return
    duration_ms = (time.perf_counter() - t0) * 1000

    # Dump IR JSON
    ir_path = sample_out_dir / "ir.json"
    ir_path.write_text(
        json.dumps(result.ir, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    # Dump images
    written_images = 0
    for rel, blob in result.images.items():
        # rel is like "raw_images/img_1.png"
        target = sample_out_dir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
        written_images += 1

    # Dump warnings
    if result.warnings:
        warn_path = sample_out_dir / "warnings.txt"
        warn_path.write_text("\n".join(result.warnings), encoding="utf-8")

    # Summary
    ir_size_kb = ir_path.stat().st_size / 1024
    block_count = _count_blocks(result.ir)
    print(f"  OK   format={fmt}  ir.json={ir_size_kb:.1f}KB  blocks={block_count}  "
          f"images={written_images}  warnings={len(result.warnings)}  "
          f"duration={duration_ms:.0f}ms")
    if result.warnings:
        for w in result.warnings[:5]:
            print(f"      ! {w}")
        if len(result.warnings) > 5:
            print(f"      ! ... and {len(result.warnings) - 5} more")


def _count_blocks(ir: dict) -> int:
    fmt = ir.get("format")
    if fmt == "pptx":
        return sum(len(s.get("shapes", [])) for s in ir.get("slides", []))
    if fmt == "xlsx":
        return sum(
            len(s.get("tables", [])) + len(s.get("charts", [])) + len(s.get("images", []))
            for s in ir.get("sheets", [])
        )
    if fmt == "pdf":
        return sum(
            len(p.get("text_blocks", [])) + len(p.get("images_on_page", [])) + len(p.get("tables", []))
            for p in ir.get("pages", [])
        )
    if fmt in ("html", "markdown", "docx"):
        return len(ir.get("blocks", []))
    return 0


def main() -> int:
    samples_dir = REPO_ROOT / "samples"
    out_dir = samples_dir / "_ir"
    out_dir.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1:
        targets = [Path(p) for p in sys.argv[1:]]
    else:
        targets = sorted(
            p for p in samples_dir.iterdir()
            if p.is_file() and not p.name.startswith("_")
        )

    print(f"Extracting {len(targets)} file(s) → {out_dir}")
    for t in targets:
        dump_one(t.resolve(), out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
