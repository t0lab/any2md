"""Main orchestrator — renders one IR chunk to markdown via deepagents.

Backend: bare `StateBackend()` (in-memory, thread-isolated per invoke).
Inputs are seeded via `agent.invoke({"messages": [...], "files": {...}})`;
output is read back from `result["files"][FINAL_PATH]["content"]`.

No filesystem writes happen by default — required so the library can be
imported from a `.whl` on Databricks serverless (CWD is read-only there).
If `ConvertOptions.debug_workspace` is set, the returned files dict is
mirrored to disk after each chunk for inspection.

Agent compilation is expensive (middleware assembly + tool binding); a
module-level cache reuses the compiled graph across chunks/calls keyed
by the fields that affect prompt or topology.

Topology:
  main agent reads /workspace/ir.json + /workspace/captions.json, writes
  /workspace/final.md ONCE. If quality_review enabled, invokes the
  `quality-reviewer` subagent via the built-in `task` tool — reviewer
  applies in-place `edit_file` calls (never `write_file`), avoiding
  stream truncation on long outputs.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent
from deepagents.backends import StateBackend

from ..llm import build_llm
from .postprocess import apply_postprocess
from .prompts import format_main_prompt
from .subagents import quality_cleaner_subagent, quality_reviewer_subagent
from .tools import build_initial_files, dump_state_to_disk, read_final

if TYPE_CHECKING:
    from ..options import ConvertOptions


_AGENT_CACHE: dict[tuple, Any] = {}


def _agent_key(options: "ConvertOptions") -> tuple:
    tm = options.text_model
    model_id = (
        id(tm.instance)
        if tm.instance is not None
        else (tm.provider, tm.model, tm.base_url)
    )
    return (
        model_id,
        options.enable_quality_review,
        options.enable_quality_clean,
        options.caption_language,
        options.primary_language,
    )


def _build_agent(options: "ConvertOptions"):
    key = _agent_key(options)
    cached = _AGENT_CACHE.get(key)
    if cached is not None:
        return cached

    llm = build_llm(options.text_model)
    prompt = format_main_prompt(
        with_review=options.enable_quality_review,
        with_clean=options.enable_quality_clean,
        caption_language=options.caption_language,
        primary_language=options.primary_language,
    )
    subagents = []
    if options.enable_quality_review:
        subagents.append(quality_reviewer_subagent())
    if options.enable_quality_clean:
        subagents.append(quality_cleaner_subagent())
    agent = create_deep_agent(
        model=llm,
        system_prompt=prompt,
        subagents=subagents,
        backend=StateBackend(),
    )
    _AGENT_CACHE[key] = agent
    return agent


async def arender_chunk(
    ir: dict[str, Any],
    *,
    captions: dict[str, str] | None = None,
    previous_tail: str | None = None,
    options: "ConvertOptions",
    debug_workspace: Path | None = None,
) -> str:
    """Render one chunk via the cached agent. Async-native."""
    agent = _build_agent(options)
    files = build_initial_files(ir, captions, previous_tail)
    result = await agent.ainvoke(
        {
            "messages": [{"role": "user", "content": "Render this chunk to markdown."}],
            "files": files,
        },
        config={"recursion_limit": options.recursion_limit},
    )
    out_files = result.get("files") or {}
    if debug_workspace is not None:
        dump_state_to_disk(debug_workspace, out_files)
    return apply_postprocess(read_final(out_files), ir)


def render_chunk(
    ir: dict[str, Any],
    *,
    captions: dict[str, str] | None = None,
    previous_tail: str | None = None,
    options: "ConvertOptions",
    debug_workspace: Path | None = None,
) -> str:
    """Sync wrapper. Safe to call whether or not an event loop is running.

    Inside a running loop (Databricks notebook, IPython, Jupyter), the
    coroutine is dispatched to a worker thread so we don't collide with
    the caller's loop. Outside a loop, plain `asyncio.run()`.
    """
    coro_factory = lambda: arender_chunk(  # noqa: E731
        ir,
        captions=captions,
        previous_tail=previous_tail,
        options=options,
        debug_workspace=debug_workspace,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro_factory())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(lambda: asyncio.run(coro_factory())).result()
