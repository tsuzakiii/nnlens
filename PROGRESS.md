# layerlens — progress / task board

Working name: **layerlens** (changeable). Goal: MCP server + local renderer that
explains NN components in five linked views, driven by the user's own LLM
subscription (host does inference; server = tools + methodology + renderer).

## Decisions locked
- Form factor: **MCP server + local renderer** (not a hosted site, not CLI-shellout).
- Host = the user's subscription (Claude Desktop / Claude Code / Cursor). Server never calls an LLM.
- On-demand generation only; **no committed content library** (keeps view 5 free of repo-redistribution/license issues).
- Backend not auto-detected — it's simply whichever MCP host the user configures.
- Renderer: Markdown (markdown-it) + Mermaid + KaTeX + `{{term}}` hover tooltips.

## Done (MVP v0.1)
- [x] Project scaffold (pyproject, MIT, gitignore, README, CONTRIBUTING).
- [x] Schema (`models.py`): Explanation → Component → 5 views + concept ledger.
- [x] MCP server (`server.py`): tools `fetch_paper`, `find_official_repo`, `fetch_repo_code`, `run_python`, `render`, `explanation_schema`; `explain` prompt.
- [x] Retrieval (`sources.py`, stdlib only), sandbox (`sandbox.py`).
- [x] Renderer (`template.html`, `build.py`, background static `server.py`).
- [x] Golden example (Transformer/attention) built by `scripts/build_example.py` (runs naive code).
- [x] Tests: models, sandbox, renderer, sources(net-guarded).

## Done (this session, cont.)
- [x] venv + install, build example, pytest green (12 Python + 5 JS).
- [x] Codex review #1 → 11 findings, ALL fixed:
  - Renderer XSS (html:false + texmath math + DOM-walk term wiring + safeHref scheme allowlist).
  - Extracted renderer JS to `viewer.js`; headless-tested via Node+jsdom (`tests/js/viewer.test.cjs`).
  - sandbox: UTF-8 decode, bounded drain threads, process-tree kill on timeout (+regression tests).
  - sources: arXiv via ElementTree (+no_results, old-style ids), capped/quoted repo fetch.
  - static server restricted to `/e/<slug>.html`, no dir listing.
  - prompt `kind` example fixed to a valid literal.
- [x] git init (25 files staged; not yet committed).
- [~] Browser visual check: BLOCKED — browser-scenario profile locked by another process. Renderer verified headlessly instead.

## Done (this session, cont. 2)
- [x] Codex re-review #2: main XSS rewrite / wrapTerms / traversal / sandbox / build escaping all confirmed sound. 3 minor findings, ALL fixed:
  - slug() now ASCII-only (+hash fallback) so Unicode ids don't 404 on the render server.
  - markdown links restricted to http(s)+anchors; images disabled (no external auto-load).
  - arXiv id extraction strips trailing slash.
- [x] Caught+fixed independently: markdown-it-texmath sets no browser global → createMd probes the bare `texmath` identifier (else math would render as raw `$...$` in a real browser).
- [x] Regression tests added (link/image policy, unicode slug, arxiv id variants). Python 14 + JS 6 all green.

## Done (this session, cont. 3)
- [x] Runtime integration tests: render() serves over HTTP (200+content), static server 404s outside /e/<slug>.html, invalid explanation -> validation error. (16 Python tests)
- [x] renderComponent assembly test via jsdom (5 views, ledger, badges, term wiring, safe link). (8 JS tests)
- [x] Built wheel; verified template.html + viewer.js are packaged; fresh-install smoke test renders + MCP imports. `pip install` claim holds.
- [x] 3 local commits (no push).

## Needs the user / external (can't do autonomously)
- [ ] Browser *visual* of mermaid/katex: browser-scenario profile stayed locked all session. Logic verified headlessly; retry when it frees.
- [ ] End-to-end host-driven run: needs the user's own MCP host (Claude Desktop / Claude Code) — add layerlens, run /explain, confirm the round-trip.
- [ ] Naming + PyPI availability before publishing ("layerlens" is a working name).
- [ ] Open design Q: Codex-as-MCP-client support for ChatGPT-sub users (Claude hosts are solid).

## Verified state
- Tests: 16 Python + 8 Node/jsdom, all green. Codex reviewed twice (14 findings, all fixed). Wheel installs and renders.

## Known limitations (documented, not blockers)
- Browser visual of mermaid/katex not yet eyeballed (profile locked all session); graceful fallback implemented.
- `run_python` is a timeout+tree-kill subprocess, not a hardened sandbox (documented in README).
- Renderer needs internet for CDN libs at view time.

## Backlog / open questions
- [ ] Verify the `explain` flow against a real MCP host end-to-end (needs Claude Desktop/Code).
- [ ] Codex-as-MCP-client support? (affects ChatGPT-sub users; Claude hosts are solid.)
- [ ] Architecture decomposition example (full Transformer block → attention/FFN/norm/residual).
- [ ] Optional: offline/vendored CDN assets for the renderer.
- [ ] Optional: `run_python` hardening (no-network mode).
- [ ] Naming / PyPI availability check before publishing.
