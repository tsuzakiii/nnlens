"""Runtime configuration (mostly: where rendered pages are stored)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def store_dir() -> str:
    """Directory where rendered explanation pages are written and served from.

    On first use after the project's renames, an existing legacy store
    (``~/.layerlore/store`` or ``~/.layerlens/store`` — earlier project names) is
    migrated so previously generated explanations keep showing up in the library.
    """
    env = os.environ.get("NNLENS_STORE")
    base = Path(env) if env else Path.home() / ".nnlens" / "store"
    if env is None and not base.exists():
        for legacy_name in (".layerlore", ".layerlens"):
            legacy = Path.home() / legacy_name / "store"
            if legacy.is_dir():
                base.parent.mkdir(parents=True, exist_ok=True)
                try:
                    legacy.rename(base)  # same-volume move
                except OSError:
                    try:
                        shutil.copytree(legacy, base)
                    except OSError:
                        continue  # try the next legacy location
                break
    base.mkdir(parents=True, exist_ok=True)
    return str(base)


def start_port() -> int:
    return int(os.environ.get("NNLENS_PORT", "8787"))
