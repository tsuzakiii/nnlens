"""Render the bundled example explanation and print (optionally open) its URL.

Usage:
    python scripts/demo_render.py            # render + print URL, keep serving
    python scripts/demo_render.py --open     # also open it in the browser
    python scripts/demo_render.py --once     # render to a file and exit (no server)
"""

from __future__ import annotations

import json
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from layerlens import config  # noqa: E402
from layerlens.models import Explanation  # noqa: E402
from layerlens.renderer import build_html, ensure_server, write_explanation  # noqa: E402


def main() -> None:
    args = set(sys.argv[1:])
    data = json.loads((ROOT / "examples" / "transformer_attention.json").read_text(encoding="utf-8"))
    ex = Explanation.model_validate(data)

    if "--once" in args:
        out = ROOT / "examples" / "transformer_attention.rendered.html"
        out.write_text(build_html(ex.model_dump()), encoding="utf-8")
        print(f"wrote {out}")
        return

    store = config.store_dir()
    write_explanation(ex.model_dump(), store, ex.slug())
    port = ensure_server(store, start_port=config.start_port())
    url = f"http://127.0.0.1:{port}/e/{ex.slug()}.html"
    print(f"serving: {url}")
    if "--open" in args:
        webbrowser.open(url)
    print("Ctrl-C to stop.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
