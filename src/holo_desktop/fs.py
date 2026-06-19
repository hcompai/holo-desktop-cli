"""Small filesystem helpers shared across CLI and host integrations."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Write+fsync to a sibling temp file, then rename over the target."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        Path(tmp).unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    """Crash-safe JSON metadata write."""
    atomic_write_text(path, json.dumps(payload) + "\n")
