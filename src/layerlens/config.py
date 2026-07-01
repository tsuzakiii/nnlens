"""Runtime configuration (mostly: where rendered pages are stored)."""

from __future__ import annotations

import os
from pathlib import Path


def store_dir() -> str:
    """Directory where rendered explanation pages are written and served from."""
    env = os.environ.get("LAYERLENS_STORE")
    base = Path(env) if env else Path.home() / ".layerlens" / "store"
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def start_port() -> int:
    return int(os.environ.get("LAYERLENS_PORT", "8787"))
