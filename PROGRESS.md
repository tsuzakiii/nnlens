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

## Done (this session, cont. 4) — real-usage feedback + visual polish
- [x] **Bug (from real use): `run_python` hung on trivial `print(2+2)` over MCP stdio.** Root-caused empirically (not `sys.executable` — the child inherited the parent's MCP-pipe stdin and deadlocked on Windows). Fix: spawn snippets with `stdin=DEVNULL`. Added an **E2E regression test** (`tests/test_mcp_stdio.py`) that launches the server over real stdio (normal pytest can't reproduce it). Also added a defensive `_python_interpreter()` resolver.
- [x] **`fetch_paper` now surfaces `repos`** (github URLs from the abstract/links) so view 5 survives find_official_repo name collisions (e.g. PRISM → gpr-prism/prism).
- [x] **Renderer full-width**: dropped `main { max-width: 900px }` → content uses the whole window (was wasting ~40% on wide screens). Verified visually via Playwright (before/after screenshots): Mermaid, KaTeX, syntax highlight, term hover, run badge, source link all render correctly.
- [x] Feature scoping: in-page "Claude toolbox" (select-to-explain / revise) researched (workflow) — MCP sampling unsupported by Desktop/Code today; only viable via a separate warm-`claude`-CLI daemon. User declined the feature for now.

## Done (2026-07-02) — cross-links between explanations
- [x] Design doc `docs/DESIGN_related_links.md`; implemented by a Sonnet-5(high) subagent, reviewed + hardened here.
- [x] `Explanation.related` (RelatedRef: slug/label/relation×4) + `[[slug|text]]` wikilinks in prose; header chips; two-stage pending→link/missing upgrade against the library index (missing = 「まだ生成されていません」= what to generate next).
- [x] New MCP tool `list_library` so the host knows existing slugs before linking; prompt updated.
- [x] Codex review #4 (4 findings, all fixed): prototype-pollution-safe slug map (Object.create(null)+hasOwnProperty), upgradeLinks reconciles in BOTH directions (deleted target downgrades a live link), slug allowlist unified with the server URL regex across RelatedRef/isSafeSlug/_clean_entry, list_library never raises. No XSS path found.
- [x] Verified in-browser: attention↔layer-norm mutual chips click through both ways.

## Done (2026-07-02, cont.) — template updates now reach old pages
- [x] Pages are stamped with a template hash (`<meta name="layerlens-template">`; sha1 of template.html+viewer.js).
- [x] `rebuild_store`: pages whose stamp differs (or is missing = legacy) are re-rendered losslessly from their embedded Explanation JSON; unparseable pages skipped untouched. Runs automatically at `ensure_server` startup.
- [x] Proven on the real store: the PRISM page (stuck on the old max-width:900px CSS) auto-upgraded to the current layout + wikilink viewer on server restart.
- [x] `write_explanation` atomic (temp+os.replace). Codex review #5 (2 findings, fixed): renders win over rebuilds via mtime guard (`_replace_if_unchanged`), fixed short temp prefix (Windows path limits), per-page failure isolation, rebuild/reconcile guarded separately at startup.

## Done (2026-07-02, cont. 2) — render() lints the cross-view contract
- [x] New `lint.py`: render() returns non-blocking `warnings` — ledger terms actually marked in prose, marks resolve to a ledger entry, words view symbol-free ($/non-ASCII symbols; single ASCII letters skipped), math view has notation, optimized view cites a source or declares self-impl, naive run verified (run_ok).
- [x] Codex review #6 (3 findings, all fixed): lint now mirrors the RENDERER — code/math regions stripped before analysis (`` `{{x}}` `` doesn't count as wired; `` `$PATH` `` doesn't flag), and mark resolution is global across components (matches viewer.js's merged ledgerMap).
- [x] Prompt: host is told to fix warnings and re-render. Dogfood test: bundled fixtures are lint-clean.

## Verified state
- Tests: 59 Python + 16 Node/jsdom, all green. Codex reviewed 6 times (23 findings, all fixed). Wheel installs and renders. Rendered page + cross-links visually verified in-browser; legacy-page auto-rebuild verified on the real store.

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
- [ ] **Naming: `layerlens` is TAKEN** (PyPI 200; GitHub has a LayerLens org, 276★ repo). Must rename before publishing. Checked AVAILABLE on PyPI (2026-07-02): layerscope, nnlens, layerwise-explain, explayn, layerlore, fivelens. → user's pick.
