"""Launcher for the LangSmith MCP server, used by .mcp.json.

Loads project .env (LANGSMITH_API_KEY / LANGSMITH_ENDPOINT / LANGSMITH_PROJECT
live in one place — the same file the python pipeline reads) and then hands
stdio off to the langsmith-mcp-server binary. The server runs in pipx's
isolated venv so it does not pollute the project's site-packages.

Cross-platform discovery — no hardcoded paths:
  1. `shutil.which("langsmith-mcp-server")` — works when pipx's bin dir is on
     PATH (true after `pipx ensurepath`).
  2. Ask pipx for its venv root and probe `Scripts/` (Windows) or `bin/` (POSIX).
  3. If not found, run `pipx install langsmith-mcp-server` and retry.

Prereqs: Python with pipx (any modern install). Manual smoke test:
    py scripts/langsmith_mcp.py     # waits on stdin for JSON-RPC, Ctrl-C exits
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

if not os.getenv("LANGSMITH_API_KEY"):
    sys.exit("langsmith_mcp: LANGSMITH_API_KEY not set (expected in .env)")

PKG = "langsmith-mcp-server"
EXE = "langsmith-mcp-server"  # pipx exposes the same name on every OS


def _from_pipx_venv() -> str | None:
    """Locate the exe inside pipx's persistent venv across platforms."""
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pipx", "environment", "--value", "PIPX_LOCAL_VENVS"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    venvs = Path(proc.stdout.strip())
    for subdir, suffix in (("Scripts", ".exe"), ("bin", "")):
        cand = venvs / PKG / subdir / f"{EXE}{suffix}"
        if cand.exists():
            return str(cand)
    return None


def _find_binary() -> str | None:
    return shutil.which(EXE) or _from_pipx_venv()


binary = _find_binary()
if binary is None:
    print(f"langsmith_mcp: installing {PKG} via pipx (one-time)...", file=sys.stderr)
    try:
        subprocess.run(
            [sys.executable, "-m", "pipx", "install", PKG],
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        sys.exit(
            f"langsmith_mcp: pipx install failed ({e}). "
            "Install pipx (`py -m pip install --user pipx && py -m pipx ensurepath`) "
            f"then re-run, or install {PKG} manually."
        )
    binary = _find_binary()
    if binary is None:
        sys.exit(f"langsmith_mcp: {EXE} not found after install — pipx PATH not wired?")

result = subprocess.run([binary], check=False)
sys.exit(result.returncode)
