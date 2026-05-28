"""Apply ir_clean to every samples/_ir/<stem>/ir.json and report size delta.

Reads samples/_ir/<stem>/ir.json (output of dump_ir.py), writes ir.clean.json
next to it, and prints before/after sizes.

Usage:
    py scripts/clean_ir.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from any2md.ir_clean import clean_ir  # noqa: E402


def main() -> int:
    ir_root = REPO_ROOT / "samples" / "_ir"
    if not ir_root.exists():
        print(f"No samples/_ir/ found. Run scripts/dump_ir.py first.")
        return 1

    rows: list[tuple[str, int, int]] = []
    for sample_dir in sorted(ir_root.iterdir()):
        if not sample_dir.is_dir():
            continue
        src = sample_dir / "ir.json"
        if not src.exists():
            continue
        raw = json.loads(src.read_text(encoding="utf-8"))
        cleaned = clean_ir(raw)
        dst = sample_dir / "ir.clean.json"
        dst.write_text(
            json.dumps(cleaned, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        rows.append((sample_dir.name, src.stat().st_size, dst.stat().st_size))

    print(f"{'Sample':<40} {'Raw':>10} {'Cleaned':>10} {'Δ':>10}  Reduction")
    print("-" * 90)
    total_raw = total_clean = 0
    for name, raw_b, clean_b in rows:
        delta = raw_b - clean_b
        pct = (delta / raw_b * 100) if raw_b else 0
        total_raw += raw_b
        total_clean += clean_b
        print(
            f"{name:<40} {raw_b/1024:>8.1f}KB {clean_b/1024:>8.1f}KB "
            f"{delta/1024:>8.1f}KB  {pct:>5.1f}%"
        )
    print("-" * 90)
    total_delta = total_raw - total_clean
    total_pct = (total_delta / total_raw * 100) if total_raw else 0
    print(
        f"{'TOTAL':<40} {total_raw/1024:>8.1f}KB {total_clean/1024:>8.1f}KB "
        f"{total_delta/1024:>8.1f}KB  {total_pct:>5.1f}%"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
