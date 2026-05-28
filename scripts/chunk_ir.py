"""Chunk every samples/_ir/<stem>/ir.clean.json and report sizes.

Reads cleaned IRs (output of scripts/clean_ir.py), runs `chunk_ir`, and writes
each chunk to samples/_ir/<stem>/chunks/chunk_<idx>.json.

Usage:
    py scripts/chunk_ir.py
    py scripts/chunk_ir.py --max-tokens 10000 --max-images 50
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from any2md.ir_chunk import chunk_ir, DEFAULT_MAX_TOKENS, DEFAULT_MAX_IMAGES  # noqa: E402


def run(max_tokens: int, max_images: int) -> int:
    ir_root = REPO_ROOT / "samples" / "_ir"
    if not ir_root.exists():
        print("No samples/_ir/. Run scripts/dump_ir.py + scripts/clean_ir.py first.")
        return 1

    print(f"max_tokens={max_tokens}  max_images={max_images}")
    print(f"{'Sample':<40} {'Units':>6} {'Chunks':>7} {'Tokens / chunk':<32} {'Trunc?':>6}")
    print("-" * 100)

    for sample_dir in sorted(ir_root.iterdir()):
        if not sample_dir.is_dir():
            continue
        src = sample_dir / "ir.clean.json"
        if not src.exists():
            src = sample_dir / "ir.json"
            if not src.exists():
                continue
        ir = json.loads(src.read_text(encoding="utf-8"))
        chunks = chunk_ir(ir, max_tokens=max_tokens, max_images=max_images)

        chunks_dir = sample_dir / "chunks"
        if chunks_dir.exists():
            for old in chunks_dir.glob("chunk_*.json"):
                old.unlink()
        else:
            chunks_dir.mkdir(parents=True, exist_ok=True)

        for c in chunks:
            (chunks_dir / f"chunk_{c['chunk_index']:02d}.json").write_text(
                json.dumps(c, ensure_ascii=False, indent=2, default=str),
                encoding="utf-8",
            )

        units = _count_units(ir)
        sizes = ",".join(str(c["token_count"]) for c in chunks)
        truncated = any(c["truncated"] for c in chunks)
        print(
            f"{sample_dir.name:<40} {units:>6} {len(chunks):>7} "
            f"{sizes:<32} {'YES' if truncated else '-':>6}"
        )
    return 0


def _count_units(ir: dict) -> int:
    fmt = ir.get("format")
    if fmt == "pptx":  return len(ir.get("slides", []))
    if fmt == "pdf":   return len(ir.get("pages", []))
    if fmt == "xlsx":  return len(ir.get("sheets", []))
    return len(ir.get("blocks", []))


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    p.add_argument("--max-images", type=int, default=DEFAULT_MAX_IMAGES)
    args = p.parse_args()
    return run(args.max_tokens, args.max_images)


if __name__ == "__main__":
    raise SystemExit(main())
