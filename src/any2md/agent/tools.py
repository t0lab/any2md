"""Virtual-workspace helpers for the deepagents agent.

The agent sees a virtual filesystem rooted at /workspace/ backed by
StateBackend (LangGraph state, in-memory, thread-scoped per invoke).
Inputs are seeded via the `files=` payload on invoke; output is read
back from `result["files"][FINAL_PATH]["content"]`.

No on-disk I/O happens here. Persistence to a debug directory is the
caller's choice via `dump_state_to_disk`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from deepagents.backends.utils import create_file_data

if TYPE_CHECKING:
    from deepagents.backends.protocol import FileData

# Virtual paths the agent sees (the `/workspace/` prefix is just a
# convention — StateBackend treats them as opaque keys).
WORKSPACE_ROOT = "/workspace"
IR_PATH = f"{WORKSPACE_ROOT}/ir.json"
CAPTIONS_PATH = f"{WORKSPACE_ROOT}/captions.json"
FINAL_PATH = f"{WORKSPACE_ROOT}/final.md"
TAIL_PATH = f"{WORKSPACE_ROOT}/previous_tail.md"


def build_initial_files(
    ir: dict[str, Any],
    captions: dict[str, str] | None = None,
    previous_tail: str | None = None,
) -> dict[str, "FileData"]:
    """Build the `files=` payload for `agent.invoke(...)`.

    Only seeds what the agent actually reads: IR, captions, optional
    previous-chunk tail. Image bytes are NOT seeded — captions are
    pre-computed and embedded verbatim by the renderer.
    """
    files: dict[str, FileData] = {
        IR_PATH: create_file_data(json.dumps(ir, ensure_ascii=False, indent=2)),
        CAPTIONS_PATH: create_file_data(
            json.dumps(captions or {}, ensure_ascii=False, indent=2)
        ),
    }
    if previous_tail:
        files[TAIL_PATH] = create_file_data(previous_tail)
    return files


def read_final(files: dict[str, "FileData"]) -> str:
    """Pull final.md content from a returned agent state."""
    entry = files.get(FINAL_PATH)
    return entry["content"] if entry else ""


def dump_state_to_disk(target: Path, files: dict[str, "FileData"]) -> None:
    """Mirror a returned `result["files"]` dict to a real directory.

    Strips the leading `/workspace/` prefix so paths land relatively
    under `target/`. Skips entries whose content is None.
    """
    target.mkdir(parents=True, exist_ok=True)
    for path, data in files.items():
        if not data or "content" not in data:
            continue
        rel = path.lstrip("/")
        if rel.startswith("workspace/"):
            rel = rel[len("workspace/"):]
        out = target / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(data["content"], encoding="utf-8")
