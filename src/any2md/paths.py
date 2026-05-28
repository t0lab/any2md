"""Path resolution for various source forms (UC Volume / relative / local)."""
from __future__ import annotations

from pathlib import Path


def resolve_source(source: str | Path, *, base: Path | None = None) -> Path:
    """Resolve a source path into an absolute Path.

    Accepts:
      - UC Volume absolute (/Volumes/...)
      - Workspace files (/Workspace/...)
      - Local absolute or relative paths
      - pathlib.Path objects
    """
    p = Path(source) if not isinstance(source, Path) else source
    if not p.is_absolute():
        p = (base or Path.cwd()) / p
    return p.resolve()
