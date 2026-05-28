"""Top-level `convert()` / `aconvert()` API — file → markdown.

Two public entry points:

* `aconvert(source, options=...)` — async-native. Use this inside
  Databricks notebooks, FastAPI handlers, or any code already running
  on an event loop. Awaits the caption pre-pass + per-chunk render
  directly.

* `convert(source, options=...)` — sync wrapper. Safe to call from
  plain scripts (no loop running) AND from notebooks (loop running).
  Detects the loop state and dispatches to a worker thread when
  necessary so it never raises `asyncio.run() cannot be called from
  a running event loop`.

By default no filesystem writes happen anywhere except `options.write_to`
(an explicit output path). Pass `options.debug_workspace` to mirror
the agent's virtual state (ir.json, captions.json, final.md per chunk)
to disk for inspection.

Spec: docs/superpowers/specs/2026-05-26-databricks-compat-and-agent-rewrite/design.md
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .options import ConvertOptions, ConvertResult
from .pipeline import extract_and_clean

if TYPE_CHECKING:
    pass

_TAIL_CHARS = 1000


def _resolve_debug_workspace(
    options: ConvertOptions,
    source_stem: str,
    chunk_index: int,
    multi: bool,
) -> Path | None:
    """Resolve `options.debug_workspace` to an absolute per-chunk dir.

    None → None (no disk I/O).
    Relative path → resolved under `tempfile.gettempdir()` so callers
        don't accidentally land on a read-only CWD (Databricks notebooks).
    Absolute path → used as-is (typical for UC Volumes).

    Single-chunk runs land in `<base>/<stem>/`; multi-chunk runs split
    into `<base>/<stem>/chunk_NN/`.
    """
    if options.debug_workspace is None:
        return None
    base = Path(options.debug_workspace)
    if not base.is_absolute():
        base = Path(tempfile.gettempdir()) / base
    stem_dir = base / source_stem
    return stem_dir / f"chunk_{chunk_index:02d}" if multi else stem_dir


async def aconvert(
    source: str | Path,
    *,
    options: ConvertOptions | None = None,
) -> ConvertResult:
    """End-to-end async: load file, extract, caption, render → markdown."""
    options = options or ConvertOptions()
    src = Path(source).resolve()
    if not src.exists():
        raise FileNotFoundError(f"source not found: {src}")

    # Defer agent imports — bare-wheel users (without [agent] extras)
    # get a clear, actionable error here instead of a cryptic
    # `ModuleNotFoundError: deepagents` at import time.
    try:
        from .agent.captions import caption_pass
        from .agent.image_refs import collect_image_refs
        from .agent.main_agent import arender_chunk
        from .agent.postprocess import collapse_duplicate_h1
        from .ir_chunk import chunk_ir
        from .llm import build_llm
    except ImportError as e:
        raise ImportError(
            "any2md.convert/aconvert needs the agent extras. "
            "Install with: pip install 'any2md[agent]' "
            "(add [databricks] / [openai] / [anthropic] / [google] for your provider)."
        ) from e

    cleaned = extract_and_clean(src)

    captions: dict[str, str] = {}
    if options.enable_image_captions and collect_image_refs(cleaned.ir):
        vision_llm = build_llm(options.vision_model)
        captions = await caption_pass(
            cleaned.ir, cleaned.images, vision_llm, options
        )

    chunks = chunk_ir(cleaned.ir, max_tokens=options.max_chunk_tokens)
    multi = len(chunks) > 1

    parts: list[str] = []
    previous_tail: str | None = None
    for chunk in chunks:
        chunk_refs = collect_image_refs(chunk["ir"])
        chunk_image_ids = {r["id"] for r in chunk_refs}
        chunk_captions = {
            i: c for i, c in captions.items() if i in chunk_image_ids
        }
        debug_ws = _resolve_debug_workspace(
            options, src.stem, chunk["chunk_index"], multi
        )
        md = await arender_chunk(
            chunk["ir"],
            captions=chunk_captions,
            previous_tail=previous_tail,
            options=options,
            debug_workspace=debug_ws,
        )
        parts.append(md)
        previous_tail = md[-_TAIL_CHARS:] if md else None

    markdown = "\n\n".join(p for p in parts if p)
    if multi:
        # Continuation chunks can still slip a synthesized title past the
        # cleaner; collapse any extra H1s in the joined document.
        markdown = collapse_duplicate_h1(markdown)

    if options.write_to:
        out = Path(options.write_to)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(markdown, encoding="utf-8")

    metadata: dict[str, Any] = {
        "image_count": len(cleaned.images),
        "caption_count": len(captions),
        "chunk_count": len(chunks),
    }
    if options.debug_workspace is not None:
        base = Path(options.debug_workspace)
        if not base.is_absolute():
            base = Path(tempfile.gettempdir()) / base
        metadata["debug_workspace"] = str(base / src.stem)

    return ConvertResult(
        markdown=markdown,
        source_path=str(src),
        format=cleaned.format,  # type: ignore[arg-type]
        warnings=cleaned.warnings,
        metadata=metadata,
        ir=cleaned.ir if options.return_ir else None,
    )


def convert(
    source: str | Path,
    *,
    options: ConvertOptions | None = None,
) -> ConvertResult:
    """Sync wrapper for `aconvert`. Works inside or outside a running loop.

    In a plain script: uses `asyncio.run()`.
    Inside a notebook / IPython / Jupyter / FastAPI handler that already
    has a loop: dispatches the coroutine to a worker thread (which gets
    its own fresh loop) so we don't raise `RuntimeError: asyncio.run()
    cannot be called from a running event loop`.
    """
    coro_factory = lambda: aconvert(source, options=options)  # noqa: E731
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro_factory())).result()
