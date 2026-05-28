"""End-to-end smoke test: file -> extract -> clean -> caption -> agent -> markdown.

Usage:
    py scripts/run_agent.py                       # default: samples/test.html
    py scripts/run_agent.py samples/foo.pptx      # any supported source
    py scripts/run_agent.py --no-review           # skip quality reviewer subagent
    py scripts/run_agent.py --no-captions         # skip caption pre-pass

Env:
    LITELLM_API_KEY                  required
    LITELLM_BASE_URL / LITELLM_MODEL optional overrides (see .env.example)

Outputs final markdown to stdout. With --debug, also dumps the agent's
virtual workspace to `<repo>/workspace/<stem>/` (or `<stem>/chunk_NN/`
for multi-chunk runs) for inspection.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from any2md.convert import convert  # noqa: E402
from any2md.llm import litellm_text_model  # noqa: E402
from any2md.options import ConvertOptions  # noqa: E402

DEFAULT_SOURCE = ROOT / "samples" / "test.html"


def main() -> int:
    if not os.getenv("LITELLM_API_KEY"):
        print("error: LITELLM_API_KEY env var not set", file=sys.stderr)
        return 2

    args = list(sys.argv[1:])
    no_review = "--no-review" in args
    no_clean = "--no-clean" in args
    no_captions = "--no-captions" in args
    debug = "--debug" in args
    max_tokens: int | None = None
    rpm: int | None = None
    sleep: float | None = None
    for a in args:
        if a.startswith("--max-tokens="):
            max_tokens = int(a.split("=", 1)[1])
        elif a.startswith("--rpm="):
            rpm = int(a.split("=", 1)[1])
        elif a.startswith("--sleep="):
            sleep = float(a.split("=", 1)[1])
    positional = [a for a in args if not a.startswith("--")]
    source = Path(positional[0]).resolve() if positional else DEFAULT_SOURCE
    if not source.exists():
        print(f"error: source not found: {source}", file=sys.stderr)
        return 2

    print(
        f"[smoke] source={source.relative_to(ROOT)} "
        f"review={'off' if no_review else 'on'} "
        f"clean={'off' if no_clean else 'on'} "
        f"captions={'off' if no_captions else 'on'} "
        f"max_tokens={max_tokens if max_tokens else 'default'} "
        f"rpm={rpm if rpm else 'unlimited'} sleep={sleep if sleep else 0} "
        f"debug={'on' if debug else 'off'}",
        file=sys.stderr,
    )
    if os.getenv("LANGSMITH_TRACING", "").lower() == "true":
        project = os.getenv("LANGSMITH_PROJECT", "default").strip('"')
        print(
            f"[smoke] langsmith tracing -> project={project} "
            f"(https://smith.langchain.com/o/-/projects/p/{project})",
            file=sys.stderr,
        )

    llm = litellm_text_model()
    options = ConvertOptions(
        text_model=llm,
        vision_model=llm,
        enable_quality_review=not no_review,
        enable_quality_clean=not no_clean,
        enable_image_captions=not no_captions,
        debug_workspace=(ROOT / "workspace") if debug else None,
        **({"max_chunk_tokens": max_tokens} if max_tokens else {}),
        **({"model_requests_per_minute": rpm} if rpm else {}),
        **({"inter_chunk_sleep_seconds": sleep} if sleep else {}),
    )

    t0 = time.perf_counter()
    result = convert(source, options=options)
    dur = time.perf_counter() - t0

    print(
        f"[smoke] format={result.format} images={result.metadata['image_count']} "
        f"captions={result.metadata['caption_count']} "
        f"chunks={result.metadata['chunk_count']} "
        f"output={len(result.markdown)} chars in {dur:.1f}s",
        file=sys.stderr,
    )
    if "debug_workspace" in result.metadata:
        ws = Path(result.metadata["debug_workspace"])
        try:
            ws_rel = ws.relative_to(ROOT)
            print(f"[smoke] debug_workspace={ws_rel}", file=sys.stderr)
        except ValueError:
            print(f"[smoke] debug_workspace={ws}", file=sys.stderr)
    if result.warnings:
        for w in result.warnings[:5]:
            print(f"[smoke] warn: {w}", file=sys.stderr)

    print(result.markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
