# Contributing to layerlens

## Dev setup

```bash
py -3.12 -m venv .venv
.venv/Scripts/python -m pip install -e ".[dev]" numpy
.venv/Scripts/python -m pytest
```

`numpy` isn't a runtime dependency of layerlens itself — it's only needed to run
the bundled example's naive view (view 4).

The renderer JS (`viewer.js`) has its own headless test suite (Node + jsdom),
which covers the security-critical transforms (HTML escaping, math handling,
`{{term}}` wiring, link/image policy):

```bash
cd tests/js
npm install
npm test        # node --test
```

## Layout

```
src/layerlens/
  server.py        # MCP server: tools + the `explain` prompt
  models.py        # the Explanation schema (pydantic)
  sources.py       # arXiv + GitHub retrieval (stdlib only)
  sandbox.py       # run_python (subprocess + timeout)
  prompts.py       # the `explain` methodology prompt
  renderer/
    build.py       # explanation dict -> self-contained HTML
    server.py      # background localhost static server
    template.html  # the viewer (markdown-it + mermaid + katex + hover terms)
examples/          # golden explanation fixtures
scripts/           # build_example.py, demo_render.py
tests/
```

## Adding an example

Explanations are generated on demand by your host — they are **not** committed as a
content library (that keeps view 5 free of any repo-redistribution concerns). The
one checked-in example exists as a schema fixture and a format reference.

If you improve the format, regenerate the fixture:

```bash
python scripts/build_example.py
```

It runs the naive code through the sandbox, so `run_ok` / `run_stdout` stay real.

## Changing the schema

Edit `models.py`, then update `prompts.py` (the JSON shape shown to the host) and
`examples/transformer_attention.json` together — `tests/test_models.py` validates
the fixture against the schema and will fail if they drift.

## Changing the renderer

`template.html` is plain HTML/JS with CDN libs; open the output of
`python scripts/demo_render.py --once` in a browser to iterate. Keep the
`{{plain-word}}` → hover-tooltip wiring working (`tests/test_renderer.py` checks
the data is embedded and the token replaced).

## Before you push

- `python -m pytest` is green.
- If you touched the renderer JS, `cd tests/js && npm test` is green.
- If you touched anything with logic, run a Codex review over the diff.
