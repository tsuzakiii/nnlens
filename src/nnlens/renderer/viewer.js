/*
 * nnlens viewer — assembles the five-view page from the embedded Explanation JSON.
 *
 * Safety model (see the Codex review that motivated this design):
 *  - markdown-it runs with html:false, so any HTML in LLM/web-sourced prose is escaped.
 *  - Math is rendered by markdown-it-texmath -> KaTeX *inside* markdown, so no raw HTML
 *    is ever re-injected and code fences are never mutated.
 *  - {{term}} marks are wired by walking text nodes (skipping code / katex / mermaid),
 *    never by string-injecting HTML.
 *  - Links are built with createElement + a scheme allowlist (http/https only).
 *
 * The file runs in the browser (reads globals + the #data script tag) and is also
 * importable in Node for tests (module.exports), where dependencies are injected.
 */
(function () {
  "use strict";

  function escHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  // Return a safe href (http/https absolute URL) or null.
  function safeHref(u) {
    if (!u) return null;
    try {
      const url = new URL(String(u));
      return url.protocol === "http:" || url.protocol === "https:" ? url.href : null;
    } catch (e) {
      return null;
    }
  }

  // Build a markdown-it instance with math support, from injected deps or globals.
  // Note: markdown-it-texmath's browser script defines a bare `texmath` binding but
  // does NOT set window.texmath, so we must also probe the bare identifier.
  function createMd(deps) {
    deps = deps || {};
    const mdFactory = deps.markdownit
      || (typeof markdownit !== "undefined" ? markdownit : null)
      || (typeof window !== "undefined" ? window.markdownit : null);
    const katexLib = deps.katex
      || (typeof katex !== "undefined" ? katex : null)
      || (typeof window !== "undefined" ? window.katex : null);
    const texmathPlugin = deps.texmath
      || (typeof texmath !== "undefined" ? texmath : null)
      || (typeof window !== "undefined" ? window.texmath : null);
    if (!mdFactory) throw new Error("markdown-it is required");
    const md = mdFactory({ html: false, linkify: true, breaks: false });
    // Link/image policy: allow only http(s) links and in-page anchors, and never
    // auto-load images (external <img> from untrusted prose is a tracking vector).
    md.validateLink = (href) => {
      if (typeof href === "string" && href.charAt(0) === "#") return true;
      try {
        const u = new URL(href, "http://nnlens.local/");
        return u.protocol === "http:" || u.protocol === "https:";
      } catch (e) {
        return false;
      }
    };
    try { md.disable("image"); } catch (e) { /* rule may not exist in older md */ }
    if (texmathPlugin && katexLib) {
      md.use(texmathPlugin, {
        engine: katexLib,
        delimiters: "dollars",
        katexOptions: { throwOnError: false },
      });
    }
    return md;
  }

  function renderProseHTML(src, md) {
    return md.render(src || "");
  }

  // Wrap {{term}} occurrences in a subtree with <span class="term"> via DOM text walking,
  // skipping code, pre, katex and existing term/mermaid nodes so nothing gets corrupted.
  function wrapTerms(root) {
    const doc = root.ownerDocument;
    const NF = (typeof NodeFilter !== "undefined") ? NodeFilter
      : { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 };
    const skip = (el) => {
      const tag = el.nodeName;
      if (tag === "CODE" || tag === "PRE" || tag === "SCRIPT" || tag === "STYLE") return true;
      if (el.classList && (el.classList.contains("katex") || el.classList.contains("mermaid")
        || el.classList.contains("term"))) return true;
      return false;
    };
    const walker = doc.createTreeWalker(root, NF.SHOW_TEXT, {
      acceptNode(node) {
        for (let p = node.parentNode; p && p !== root.parentNode; p = p.parentNode) {
          if (p.nodeType === 1 && skip(p)) return NF.FILTER_REJECT;
        }
        return /\{\{[^}]+\}\}/.test(node.nodeValue) ? NF.FILTER_ACCEPT : NF.FILTER_REJECT;
      },
    });
    const targets = [];
    let n;
    while ((n = walker.nextNode())) targets.push(n);
    targets.forEach((node) => replaceTermsInTextNode(node, doc));
  }

  function replaceTermsInTextNode(node, doc) {
    const text = node.nodeValue;
    const re = /\{\{([^}]+)\}\}/g;
    let last = 0, m, any = false;
    const frag = doc.createDocumentFragment();
    while ((m = re.exec(text))) {
      any = true;
      if (m.index > last) frag.appendChild(doc.createTextNode(text.slice(last, m.index)));
      const term = m[1].trim();
      const span = doc.createElement("span");
      span.className = "term";
      span.setAttribute("data-term", term);
      span.textContent = term;
      frag.appendChild(span);
      last = re.lastIndex;
    }
    if (any) {
      if (last < text.length) frag.appendChild(doc.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    }
  }

  // ---- related / wikilink cross-links ----
  //
  // `related` (a per-explanation list) and inline `[[slug]]` / `[[slug|text]]`
  // wikilinks both render as a "pending" <span class="wikilink pending"> first —
  // never a live link — because we don't yet know whether `slug` exists in the
  // library (and on a file:// page, we never will). Once (if) the index loads,
  // `upgradeLinks` turns the ones that resolve into real <a> tags in place, and
  // marks the rest `missing` (still not a link, just styled differently).

  // ---- UI language ----
  // The prose language is chosen by the host (Explanation.language); the viewer's
  // chrome follows it. Pages without the field (pre-i18n) default to Japanese.
  const STRINGS = {
    ja: {
      views: { structure: "構造", words: "言葉での説明", math: "数式", naive: "素の実装", optimized: "最適化された実装" },
      relations: { contains: "含む", "part-of": "一部", "builds-on": "基づく", related: "関連" },
      ledgerHead: ["平易な呼び名", "記号", "正式名", "直感"],
      runOk: "実行成功", runFail: "実行失敗",
      source: "出典: ", selfImpl: "公式実装が見つからなかったため自前実装",
      library: "ライブラリ", missing: "まだ生成されていません",
      del: "削除",
      confirmDel: (t) => "「" + t + "」を削除しますか？（ファイルも消えます）",
      delFailed: "削除に失敗しました",
      diagramError: "（この構造図は描画できませんでした）",
      paper: "📄 論文", repo: "💻 リポジトリ",
    },
    en: {
      views: { structure: "Structure", words: "In plain words", math: "The math", naive: "Naive implementation", optimized: "Optimized implementation" },
      relations: { contains: "contains", "part-of": "part of", "builds-on": "builds on", related: "related" },
      ledgerHead: ["Plain name", "Symbol", "Formal name", "Intuition"],
      runOk: "run verified", runFail: "run failed",
      source: "Source: ", selfImpl: "No official implementation found — written from scratch",
      library: "Library", missing: "Not generated yet",
      del: "Delete",
      confirmDel: (t) => 'Delete "' + t + '"? (also removes the file)',
      delFailed: "Delete failed",
      diagramError: "(this structure diagram could not be rendered)",
      paper: "📄 Paper", repo: "💻 Repository",
    },
  };

  function strings(lang) {
    const key = String(lang || "ja").toLowerCase().slice(0, 2);
    return STRINGS[key] || STRINGS.en;
  }

  // The built-in tables are only FALLBACKS (ja/en). The host — which knows the
  // user's language — can localize every chrome string via DATA.ui_labels, so any
  // language works without the viewer hardcoding it. Values are plain strings
  // rendered via textContent only; bogus keys/types are ignored.
  function buildL(lang, overrides) {
    const base = strings(lang);
    const out = {
      views: Object.assign({}, base.views),
      relations: Object.assign({}, base.relations),
      ledgerHead: base.ledgerHead.slice(),
      runOk: base.runOk, runFail: base.runFail,
      source: base.source, selfImpl: base.selfImpl,
      library: base.library, missing: base.missing,
      del: base.del, confirmDel: base.confirmDel, delFailed: base.delFailed,
      diagramError: base.diagramError, paper: base.paper, repo: base.repo,
    };
    if (overrides && typeof overrides === "object") {
      const str = (v) => (typeof v === "string" && v.length > 0 && v.length <= 120 ? v : null);
      const apply = {
        structure: (v) => { out.views.structure = v; },
        words: (v) => { out.views.words = v; },
        math: (v) => { out.views.math = v; },
        naive: (v) => { out.views.naive = v; },
        optimized: (v) => { out.views.optimized = v; },
        ledger_plain: (v) => { out.ledgerHead[0] = v; },
        ledger_symbol: (v) => { out.ledgerHead[1] = v; },
        ledger_formal: (v) => { out.ledgerHead[2] = v; },
        ledger_intuition: (v) => { out.ledgerHead[3] = v; },
        relation_contains: (v) => { out.relations.contains = v; },
        relation_part_of: (v) => { out.relations["part-of"] = v; },
        relation_builds_on: (v) => { out.relations["builds-on"] = v; },
        relation_related: (v) => { out.relations.related = v; },
        run_ok: (v) => { out.runOk = v; },
        run_fail: (v) => { out.runFail = v; },
        source: (v) => { out.source = v; },
        self_impl: (v) => { out.selfImpl = v; },
        library: (v) => { out.library = v; },
        missing: (v) => { out.missing = v; },
        "delete": (v) => { out.del = v; },
        delete_failed: (v) => { out.delFailed = v; },
        confirm_delete: (v) => {
          out.confirmDel = (t) => (v.indexOf("{title}") !== -1 ? v.split("{title}").join(t) : v + " — " + t);
        },
        diagram_error: (v) => { out.diagramError = v; },
        paper: (v) => { out.paper = v; },
        repo: (v) => { out.repo = v; },
      };
      Object.keys(apply).forEach((k) => {
        const v = str(overrides[k]);
        if (v !== null) apply[k](v);
      });
    }
    return out;
  }

  let L = buildL("ja"); // module default; main()/setLanguage() switch it per page

  function setLanguage(lang, uiLabels) {
    L = buildL(lang, uiLabels);
    return L;
  }

  const WIKILINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/;

  // A slug is only trusted to build a same-origin link path. Mirror the local
  // server's URL allowlist ([A-Za-z0-9_.-]+) — anything else would 404 anyway —
  // which also excludes path separators and traversal.
  function isSafeSlug(slug) {
    return typeof slug === "string"
      && /^[A-Za-z0-9_.\-]+$/.test(slug) && slug.indexOf("..") === -1;
  }

  function wikilinkSpan(doc, slug, label) {
    const span = doc.createElement("span");
    span.className = "wikilink pending";
    span.setAttribute("data-slug", slug);
    span.setAttribute("data-label", label || "");
    span.textContent = label || slug;
    return span;
  }

  // Wrap `[[slug]]` / `[[slug|text]]` occurrences in a subtree via DOM text walking
  // (same approach as wrapTerms — never innerHTML). Skips code/pre/script/style,
  // katex/mermaid/term/wikilink nodes, and existing <a> links so nothing already
  // rendered gets corrupted. An unsafe slug (path separators / `..`) is left as
  // literal text, not linkified.
  function wrapWikilinks(root) {
    const doc = root.ownerDocument;
    const NF = (typeof NodeFilter !== "undefined") ? NodeFilter
      : { SHOW_TEXT: 4, FILTER_ACCEPT: 1, FILTER_REJECT: 2 };
    const skip = (elNode) => {
      const tag = elNode.nodeName;
      if (tag === "CODE" || tag === "PRE" || tag === "SCRIPT" || tag === "STYLE" || tag === "A") return true;
      if (elNode.classList && (elNode.classList.contains("katex") || elNode.classList.contains("mermaid")
        || elNode.classList.contains("term") || elNode.classList.contains("wikilink"))) return true;
      return false;
    };
    const walker = doc.createTreeWalker(root, NF.SHOW_TEXT, {
      acceptNode(node) {
        for (let p = node.parentNode; p && p !== root.parentNode; p = p.parentNode) {
          if (p.nodeType === 1 && skip(p)) return NF.FILTER_REJECT;
        }
        return WIKILINK_RE.test(node.nodeValue) ? NF.FILTER_ACCEPT : NF.FILTER_REJECT;
      },
    });
    const targets = [];
    let n;
    while ((n = walker.nextNode())) targets.push(n);
    targets.forEach((node) => replaceWikilinksInTextNode(node, doc));
  }

  function replaceWikilinksInTextNode(node, doc) {
    const text = node.nodeValue;
    const re = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g;
    let last = 0, m, any = false;
    const frag = doc.createDocumentFragment();
    while ((m = re.exec(text))) {
      const slug = m[1].trim();
      const label = m[2] ? m[2].trim() : "";
      if (!isSafeSlug(slug)) continue; // leave this occurrence as literal text
      any = true;
      if (m.index > last) frag.appendChild(doc.createTextNode(text.slice(last, m.index)));
      frag.appendChild(wikilinkSpan(doc, slug, label));
      last = re.lastIndex;
    }
    if (any) {
      if (last < text.length) frag.appendChild(doc.createTextNode(text.slice(last)));
      node.parentNode.replaceChild(frag, node);
    }
  }

  // Header chip row for `DATA.related`. Same pending-span mechanism as inline
  // wikilinks so a single `upgradeLinks` pass resolves both.
  function renderRelatedRow(doc, related) {
    if (!Array.isArray(related) || !related.length) return null;
    const row = el(doc, "div", "related-row");
    related.forEach((ref) => {
      if (!ref || !isSafeSlug(ref.slug)) return;
      const chip = el(doc, "span", "chip");
      const relSpan = el(doc, "span", "rel");
      relSpan.textContent = L.relations[ref.relation] || L.relations.related;
      chip.appendChild(relSpan);
      chip.appendChild(wikilinkSpan(doc, ref.slug, ref.label || ""));
      row.appendChild(chip);
    });
    return row.childNodes.length ? row : null;
  }

  // Reconcile every `.wikilink` node against the library index: known slugs become
  // real <a href="./<slug>.html"> links, unknown ones become `.missing` spans.
  // Runs on every index refresh and works in both directions (a link whose target
  // was deleted downgrades back to `.missing`), so it must be idempotent.
  function upgradeLinks(doc, indexEntries) {
    // Object.create(null): a plain {} would make prototype keys ("__proto__",
    // "toString", ...) look like existing slugs and upgrade to live links.
    const bySlug = Object.create(null);
    (Array.isArray(indexEntries) ? indexEntries : []).forEach((e) => {
      if (e && typeof e.slug === "string") bySlug[e.slug] = e;
    });
    doc.querySelectorAll(".wikilink").forEach((node) => {
      const slug = node.getAttribute("data-slug") || "";
      const label = node.getAttribute("data-label") || "";
      if (!isSafeSlug(slug)) return;
      const entry = Object.prototype.hasOwnProperty.call(bySlug, slug) ? bySlug[slug] : null;
      if (entry && node.tagName !== "A") {
        const a = doc.createElement("a");
        a.className = "wikilink";
        a.setAttribute("data-slug", slug);
        a.setAttribute("data-label", label);
        a.href = "./" + encodeURIComponent(slug) + ".html";
        a.textContent = label || entry.title || slug;
        node.parentNode.replaceChild(a, node);
      } else if (!entry && node.tagName === "A") {
        const span = wikilinkSpan(doc, slug, label);
        span.className = "wikilink missing";
        span.setAttribute("title", L.missing);
        node.parentNode.replaceChild(span, node);
      } else if (!entry) {
        node.classList.remove("pending");
        node.classList.add("missing");
        node.setAttribute("title", L.missing);
      }
    });
  }

  // ---- browser-only rendering below ----

  function el(doc, tag, cls) {
    const e = doc.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function proseEl(doc, md, src) {
    const div = el(doc, "div", "prose");
    div.innerHTML = renderProseHTML(src, md);
    wrapTerms(div);
    wrapWikilinks(div);
    return div;
  }

  function codeBlock(doc, code, lang) {
    const pre = el(doc, "pre");
    const c = el(doc, "code");
    if (lang) c.className = "language-" + lang;
    c.textContent = code || "";
    pre.appendChild(c);
    return pre;
  }

  function anchor(doc, href, label) {
    const safe = safeHref(href);
    if (!safe) return null;
    const a = doc.createElement("a");
    a.href = safe;
    a.target = "_blank";
    a.rel = "noopener noreferrer";
    a.textContent = label;
    return a;
  }

  function viewBlock(doc, num, key, nodes) {
    const v = el(doc, "div", "view");
    const h = el(doc, "h3");
    const badge = el(doc, "span", "num");
    badge.textContent = num;
    h.appendChild(badge);
    h.appendChild(doc.createTextNode(" " + L.views[key]));
    v.appendChild(h);
    (Array.isArray(nodes) ? nodes : [nodes]).forEach((nd) => nd && v.appendChild(nd));
    return v;
  }

  function ledgerTable(doc, md, ledger) {
    if (!ledger || !ledger.length) return null;
    const t = el(doc, "table", "ledger");
    const head = el(doc, "thead");
    const hr = el(doc, "tr");
    L.ledgerHead.forEach((label) => {
      const th = el(doc, "th");
      th.textContent = label;
      hr.appendChild(th);
    });
    head.appendChild(hr);
    t.appendChild(head);
    const tb = el(doc, "tbody");
    ledger.forEach((e) => {
      const tr = el(doc, "tr");
      const td0 = el(doc, "td");
      const span = el(doc, "span", "term");
      span.setAttribute("data-term", e.plain);
      span.textContent = e.plain;
      td0.appendChild(span);
      const td1 = el(doc, "td"); td1.textContent = e.symbol || "";
      const td2 = el(doc, "td"); td2.textContent = e.formal || "";
      const td3 = el(doc, "td"); td3.textContent = e.intuition || "";
      [td0, td1, td2, td3].forEach((td) => tr.appendChild(td));
      tb.appendChild(tr);
    });
    t.appendChild(tb);
    return t;
  }

  function renderComponent(doc, md, comp, idx, ledgerMap) {
    (comp.ledger || []).forEach((e) => { ledgerMap[e.plain] = e; });
    const sec = el(doc, "section", "component");
    sec.id = "c-" + (comp.id || idx);
    const h2 = el(doc, "h2"); h2.textContent = comp.name; sec.appendChild(h2);
    const lt = ledgerTable(doc, md, comp.ledger);
    if (lt) sec.appendChild(lt);

    // (1) structure
    const st = comp.structure || {};
    const mer = el(doc, "div", "mermaid");
    mer.textContent = st.diagram_mermaid || "";
    const stNodes = [mer];
    if (st.note) stNodes.push(proseEl(doc, md, st.note));
    sec.appendChild(viewBlock(doc, 1, "structure", stNodes));

    // (2) words, (3) math
    sec.appendChild(viewBlock(doc, 2, "words", proseEl(doc, md, comp.words)));
    sec.appendChild(viewBlock(doc, 3, "math", proseEl(doc, md, comp.math)));

    // (4) naive
    const nv = comp.naive || {};
    const nvNodes = [codeBlock(doc, nv.code, nv.language || "python")];
    if (nv.run_stdout || nv.run_ok != null) {
      const ok = nv.run_ok !== false;
      const run = el(doc, "div", "run" + (ok ? "" : " fail"));
      const badge = el(doc, "span", "badge " + (ok ? "ok" : "fail"));
      badge.textContent = ok ? L.runOk : L.runFail;
      run.appendChild(badge);
      if (nv.run_stdout) run.appendChild(codeBlock(doc, nv.run_stdout, null));
      nvNodes.push(run);
    }
    sec.appendChild(viewBlock(doc, 4, "naive", nvNodes));

    // (5) optimized
    const op = comp.optimized || {};
    const opNodes = [];
    if (op.source && (op.source.url || op.source.repo)) {
      const label = (op.source.repo || "") + (op.source.path ? "/" + op.source.path : "");
      const a = anchor(doc, op.source.url || ("https://github.com/" + op.source.repo), label || "source");
      const line = el(doc, "div", "src-link");
      line.appendChild(doc.createTextNode(L.source));
      if (a) line.appendChild(a); else { const s = el(doc, "span"); s.textContent = label; line.appendChild(s); }
      opNodes.push(line);
    } else if (op.is_self_impl) {
      const note = el(doc, "div", "note");
      note.textContent = L.selfImpl;
      opNodes.push(note);
    }
    opNodes.push(codeBlock(doc, op.code, op.language || "python"));
    if (op.note) opNodes.push(proseEl(doc, md, op.note));
    sec.appendChild(viewBlock(doc, 5, "optimized", opNodes));

    return sec;
  }

  function currentSlug() {
    const file = (typeof location !== "undefined" ? location.pathname : "").split("/").pop() || "";
    return file.replace(/\.html$/, "");
  }

  // Management (delete) is only possible when served over http, not for a file:// page.
  function canManage() {
    return typeof fetch === "function" && !(typeof location !== "undefined" && location.protocol === "file:");
  }

  function withCurrent(list, DATA) {
    const slug = currentSlug() || DATA.id || "";
    if (!list.some((e) => e && e.slug === slug)) {
      return list.concat([{ slug: slug, title: DATA.title, kind: DATA.kind, current: true }]);
    }
    return list;
  }

  function renderLibrary(doc, DATA, list) {
    const toc = doc.getElementById("toc");
    toc.textContent = "";
    const label = el(doc, "div", "lib-label");
    label.textContent = L.library;
    toc.appendChild(label);
    const slug = currentSlug();
    const manage = canManage();
    list.forEach((it) => {
      const isCurrent = it.current || it.slug === slug;
      const row = el(doc, "div", "lib-row");
      const a = el(doc, "a", "lib" + (isCurrent ? " current" : ""));
      a.href = isCurrent ? "#" : "./" + encodeURIComponent(it.slug) + ".html";
      a.textContent = it.title || it.slug;
      row.appendChild(a);
      if (manage) {
        const del = el(doc, "button", "del");
        del.type = "button";
        del.title = L.del;
        del.textContent = "✕";
        del.addEventListener("click", (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          deleteEntry(doc, DATA, it.slug, it.title || it.slug, isCurrent);
        });
        row.appendChild(del);
      }
      toc.appendChild(row);
      if (isCurrent) {
        (DATA.components || []).forEach((c, i) => {
          const sa = el(doc, "a", "sub");
          sa.href = "#c-" + (c.id || i);
          sa.textContent = c.name;
          toc.appendChild(sa);
        });
      }
    });
  }

  function refreshLibrary(doc, DATA) {
    return fetch("../index.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (!data || !Array.isArray(data.explanations)) return;
        renderLibrary(doc, DATA, withCurrent(data.explanations, DATA));
        upgradeLinks(doc, data.explanations);
      })
      .catch(() => {});
  }

  function deleteEntry(doc, DATA, slug, title, isCurrent) {
    if (!window.confirm(L.confirmDel(title))) return;
    fetch("./" + encodeURIComponent(slug) + ".html", { method: "DELETE" })
      .then((r) => {
        if (!(r.ok || r.status === 204)) throw new Error("delete failed");
        if (!isCurrent) return refreshLibrary(doc, DATA);
        // Deleting the page you're on: jump to another explanation, or reload if none left.
        return fetch("../index.json", { cache: "no-store" })
          .then((x) => (x.ok ? x.json() : { explanations: [] }))
          .then((data) => {
            const others = (data.explanations || []).filter((e) => e && e.slug !== slug);
            if (others.length) location.href = "./" + encodeURIComponent(others[0].slug) + ".html";
            else location.reload();
          });
      })
      .catch(() => window.alert(L.delFailed));
  }

  // Show the current explanation immediately; when served over http, pull the full
  // library (index.json, rebuilt from disk) so every explanation appears in the sidebar.
  function buildLibrary(doc, DATA) {
    const slug = currentSlug() || DATA.id || "";
    renderLibrary(doc, DATA, [{ slug: slug, title: DATA.title, kind: DATA.kind, current: true }]);
    if (canManage()) refreshLibrary(doc, DATA);
  }

  function attachTooltips(doc, ledgerMap) {
    const tip = doc.getElementById("tooltip");
    const move = (ev) => {
      const pad = 14;
      let x = ev.clientX + pad, y = ev.clientY + pad;
      if (x + tip.offsetWidth > window.innerWidth) x = ev.clientX - tip.offsetWidth - pad;
      if (y + tip.offsetHeight > window.innerHeight) y = ev.clientY - tip.offsetHeight - pad;
      tip.style.left = x + "px"; tip.style.top = y + "px";
    };
    doc.querySelectorAll(".term").forEach((span) => {
      span.addEventListener("mouseenter", (ev) => {
        const e = ledgerMap[span.getAttribute("data-term")];
        if (!e) return;
        tip.textContent = "";
        const sym = el(doc, "span", "sym"); sym.textContent = e.symbol || e.plain;
        tip.appendChild(sym);
        tip.appendChild(doc.createTextNode(" — " + (e.formal || "")));
        if (e.intuition) { tip.appendChild(doc.createElement("br")); tip.appendChild(doc.createTextNode(e.intuition)); }
        tip.style.opacity = "1";
        move(ev);
      });
      span.addEventListener("mousemove", move);
      span.addEventListener("mouseleave", () => { tip.style.opacity = "0"; });
    });
  }

  function main() {
    const doc = document;
    const DATA = JSON.parse(doc.getElementById("data").textContent);
    setLanguage(DATA.language, DATA.ui_labels); // chrome follows the prose language; host can localize any language
    doc.documentElement.lang = String(DATA.language || "ja");
    const md = createMd();
    const ledgerMap = {};

    const header = el(doc, "header", "doc");
    const h1 = el(doc, "h1"); h1.textContent = DATA.title;
    const kind = el(doc, "span", "kind"); kind.textContent = DATA.kind || "";
    h1.appendChild(kind); header.appendChild(h1);
    if (DATA.summary) header.appendChild(proseEl(doc, md, DATA.summary));
    const src = el(doc, "div", "src");
    const pa = DATA.source && anchor(doc, DATA.source.paper_url, L.paper);
    const ra = DATA.source && anchor(doc, DATA.source.repo_url, L.repo);
    if (pa) src.appendChild(pa);
    if (ra) src.appendChild(ra);
    header.appendChild(src);
    const relatedRow = renderRelatedRow(doc, DATA.related);
    if (relatedRow) header.appendChild(relatedRow);

    const m = doc.getElementById("main");
    m.appendChild(header);
    (DATA.components || []).forEach((c, i) => m.appendChild(renderComponent(doc, md, c, i, ledgerMap)));
    buildLibrary(doc, DATA);

    // syntax highlight
    if (typeof hljs !== "undefined") {
      doc.querySelectorAll("pre code[class^='language-']").forEach((b) => {
        try { hljs.highlightElement(b); } catch (e) { /* ignore */ }
      });
    }
    // mermaid: render after DOM is built; handle the promise so failures degrade gracefully
    if (typeof mermaid !== "undefined") {
      try {
        mermaid.initialize({ startOnLoad: false, theme: "neutral", securityLevel: "strict" });
        const p = mermaid.run({ querySelector: ".mermaid" });
        if (p && typeof p.catch === "function") p.catch(() => showDiagramErrors(doc));
      } catch (e) { showDiagramErrors(doc); }
    }
    attachTooltips(doc, ledgerMap);
  }

  function showDiagramErrors(doc) {
    doc.querySelectorAll(".mermaid").forEach((node) => {
      if (node.querySelector("svg")) return;
      node.classList.add("diagram-error");
      node.setAttribute("data-error-msg", L.diagramError);
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {
      escHtml, safeHref, createMd, renderProseHTML, wrapTerms, renderComponent,
      isSafeSlug, wrapWikilinks, renderRelatedRow, upgradeLinks, setLanguage,
    };
  } else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", main);
    else main();
  }
})();
