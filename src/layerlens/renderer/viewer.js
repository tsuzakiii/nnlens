/*
 * layerlens viewer — assembles the five-view page from the embedded Explanation JSON.
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
        const u = new URL(href, "http://layerlens.local/");
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

  // ---- browser-only rendering below ----

  const VIEW_TITLES = {
    structure: "構造", words: "言葉での説明", math: "数式",
    naive: "素の実装", optimized: "最適化された実装",
  };

  function el(doc, tag, cls) {
    const e = doc.createElement(tag);
    if (cls) e.className = cls;
    return e;
  }

  function proseEl(doc, md, src) {
    const div = el(doc, "div", "prose");
    div.innerHTML = renderProseHTML(src, md);
    wrapTerms(div);
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
    h.appendChild(doc.createTextNode(" " + VIEW_TITLES[key]));
    v.appendChild(h);
    (Array.isArray(nodes) ? nodes : [nodes]).forEach((nd) => nd && v.appendChild(nd));
    return v;
  }

  function ledgerTable(doc, md, ledger) {
    if (!ledger || !ledger.length) return null;
    const t = el(doc, "table", "ledger");
    const head = el(doc, "thead");
    head.innerHTML = "<tr><th>平易な呼び名</th><th>記号</th><th>正式名</th><th>直感</th></tr>";
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
      badge.textContent = ok ? "実行成功" : "実行失敗";
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
      line.appendChild(doc.createTextNode("出典: "));
      if (a) line.appendChild(a); else { const s = el(doc, "span"); s.textContent = label; line.appendChild(s); }
      opNodes.push(line);
    } else if (op.is_self_impl) {
      const note = el(doc, "div", "note");
      note.textContent = "公式実装が見つからなかったため自前実装";
      opNodes.push(note);
    }
    opNodes.push(codeBlock(doc, op.code, op.language || "python"));
    if (op.note) opNodes.push(proseEl(doc, md, op.note));
    sec.appendChild(viewBlock(doc, 5, "optimized", opNodes));

    return sec;
  }

  function buildTOC(doc, comps) {
    const toc = doc.getElementById("toc");
    comps.forEach((c, i) => {
      const a = doc.createElement("a");
      a.href = "#c-" + (c.id || i);
      a.textContent = c.name;
      toc.appendChild(a);
    });
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
    const md = createMd();
    const ledgerMap = {};

    const header = el(doc, "header", "doc");
    const h1 = el(doc, "h1"); h1.textContent = DATA.title;
    const kind = el(doc, "span", "kind"); kind.textContent = DATA.kind || "";
    h1.appendChild(kind); header.appendChild(h1);
    if (DATA.summary) header.appendChild(proseEl(doc, md, DATA.summary));
    const src = el(doc, "div", "src");
    const pa = DATA.source && anchor(doc, DATA.source.paper_url, "📄 論文");
    const ra = DATA.source && anchor(doc, DATA.source.repo_url, "💻 リポジトリ");
    if (pa) src.appendChild(pa);
    if (ra) src.appendChild(ra);
    header.appendChild(src);

    const m = doc.getElementById("main");
    m.appendChild(header);
    (DATA.components || []).forEach((c, i) => m.appendChild(renderComponent(doc, md, c, i, ledgerMap)));
    buildTOC(doc, DATA.components || []);

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
    });
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = { escHtml, safeHref, createMd, renderProseHTML, wrapTerms };
  } else if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", main);
    else main();
  }
})();
