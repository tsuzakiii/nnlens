"use strict";
// Headless tests for the viewer JS. Verifies the security-critical transforms
// (HTML escaping, math handling, {{term}} wrapping, link scheme allowlist) without
// a real browser — mermaid/katex layout aren't asserted here, only that math is
// handed to katex and raw HTML never survives.

const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const { JSDOM } = require("jsdom");
const markdownit = require("markdown-it");
const texmath = require("markdown-it-texmath");
const katex = require("katex");

const viewer = require(path.resolve(__dirname, "../../src/layerlens/renderer/viewer.js"));
const md = viewer.createMd({ markdownit, texmath, katex });

test("renders markdown but escapes raw HTML (no XSS from prose)", () => {
  const html = viewer.renderProseHTML("普通の**太字** と <img src=x onerror=alert(1)>", md);
  assert.ok(html.includes("<strong>"), "markdown still works");
  assert.ok(!/<img\b/i.test(html), "raw HTML tag must not survive");
  assert.ok(html.includes("&lt;img"), "raw HTML is escaped");
});

test("math is rendered by katex and not mangled by markdown", () => {
  const html = viewer.renderProseHTML("式は $a_i + b_i$ で、表示式は $$\\frac{a_i}{b_i}$$ です", md);
  assert.ok(html.includes("katex"), "katex output present");
  assert.ok(!html.includes("<em>"), "underscores inside math must not become <em>");
});

test("markdown links restricted to http(s); images not auto-loaded", () => {
  const html = viewer.renderProseHTML(
    "[ok](https://example.com) [bad](ftp://x/y) ![track](https://attacker/p.png)",
    md,
  );
  assert.ok(/href="https:\/\/example\.com"/.test(html), "https link kept");
  assert.ok(!/href="ftp:/i.test(html), "ftp link not rendered as a live href");
  assert.ok(!/<img\b/i.test(html), "images are not rendered");
});

test("safeHref blocks javascript:/data: and allows http/https", () => {
  assert.strictEqual(viewer.safeHref("javascript:alert(1)"), null);
  assert.strictEqual(viewer.safeHref("data:text/html,<script>1</script>"), null);
  assert.strictEqual(viewer.safeHref(""), null);
  assert.strictEqual(viewer.safeHref("not a url"), null);
  assert.ok(viewer.safeHref("https://example.com/a").startsWith("https://"));
  assert.ok(viewer.safeHref("http://example.com/a").startsWith("http://"));
});

test("wrapTerms wraps {{term}} in prose but leaves code spans literal", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = viewer.renderProseHTML("これは {{注目度}} と `{{コード内}}` です", md);
  viewer.wrapTerms(r);
  const spans = [...r.querySelectorAll("span.term")];
  assert.strictEqual(spans.length, 1, "exactly one prose term wrapped");
  assert.strictEqual(spans[0].getAttribute("data-term"), "注目度");
  assert.ok(
    r.querySelector("code").textContent.includes("{{コード内}}"),
    "term inside code stays literal",
  );
});

test("wrapTerms does not touch text already inside a .term span", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = "<span class='term' data-term='x'>{{x}}</span>";
  viewer.wrapTerms(r);
  assert.strictEqual(r.querySelectorAll("span.term").length, 1, "no double-wrapping");
});

// ---- related links / wikilinks ----

test("isSafeSlug rejects path separators and traversal", () => {
  assert.strictEqual(viewer.isSafeSlug("layer-normalization"), true);
  assert.strictEqual(viewer.isSafeSlug("../secret"), false);
  assert.strictEqual(viewer.isSafeSlug("a/b"), false);
  assert.strictEqual(viewer.isSafeSlug("a\\b"), false);
  assert.strictEqual(viewer.isSafeSlug(""), false);
  assert.strictEqual(viewer.isSafeSlug(null), false);
});

test("wrapWikilinks turns [[slug]] into a pending span, leaves code literal", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = viewer.renderProseHTML("参照: [[layer-normalization]] や `[[コード内]]` はそのまま", md);
  viewer.wrapWikilinks(r);
  const spans = [...r.querySelectorAll("span.wikilink.pending")];
  assert.strictEqual(spans.length, 1, "exactly one wikilink wrapped");
  assert.strictEqual(spans[0].getAttribute("data-slug"), "layer-normalization");
  assert.strictEqual(spans[0].textContent, "layer-normalization");
  assert.ok(
    r.querySelector("code").textContent.includes("[[コード内]]"),
    "wikilink inside code stays literal",
  );
});

test("wrapWikilinks supports [[slug|label]] and rejects path-traversal slugs", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = viewer.renderProseHTML(
    "[[layer-normalization|LayerNorm]] と [[../secret|x]] と [[a/b]]",
    md,
  );
  viewer.wrapWikilinks(r);
  const spans = [...r.querySelectorAll("span.wikilink.pending")];
  assert.strictEqual(spans.length, 1, "only the safe slug is linkified");
  assert.strictEqual(spans[0].getAttribute("data-slug"), "layer-normalization");
  assert.strictEqual(spans[0].getAttribute("data-label"), "LayerNorm");
  assert.strictEqual(spans[0].textContent, "LayerNorm");
  assert.ok(r.textContent.includes("[[../secret|x]]"), "unsafe slug left as literal text");
  assert.ok(r.textContent.includes("[[a/b]]"), "slug with '/' left as literal text");
});

test("upgradeLinks resolves known slugs to real links and marks unknown ones missing", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = viewer.renderProseHTML("[[layer-normalization]] と [[ghost-slug]]", md);
  viewer.wrapWikilinks(r);
  viewer.upgradeLinks(doc, [
    { slug: "layer-normalization", title: "Layer Normalization", kind: "technique" },
  ]);

  const a = r.querySelector("a.wikilink");
  assert.ok(a, "known slug becomes a real link");
  assert.strictEqual(a.getAttribute("href"), "./layer-normalization.html");

  const missing = r.querySelector("span.wikilink.missing");
  assert.ok(missing, "unknown slug becomes .missing");
  assert.ok(!missing.classList.contains("pending"), "missing is no longer pending");
  assert.strictEqual(missing.getAttribute("data-slug"), "ghost-slug");
});

test("upgradeLinks is prototype-safe: __proto__/constructor/toString never become live links", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  // Build the pending spans directly (markdown would eat __proto__'s underscores
  // as emphasis before wrapWikilinks ever saw it — which is itself safe).
  ["__proto__", "constructor", "toString"].forEach((slug) => {
    const span = doc.createElement("span");
    span.className = "wikilink pending";
    span.setAttribute("data-slug", slug);
    span.setAttribute("data-label", "");
    span.textContent = slug;
    r.appendChild(span);
  });
  viewer.upgradeLinks(doc, []); // empty index — nothing may upgrade
  assert.strictEqual(r.querySelectorAll("a.wikilink").length, 0, "no live links");
  assert.strictEqual(r.querySelectorAll("span.wikilink.missing").length, 3, "all marked missing");
});

test("upgradeLinks downgrades a live link back to missing when its target is deleted", () => {
  const dom = new JSDOM("<!doctype html><body><div id='r'></div></body>");
  const doc = dom.window.document;
  const r = doc.getElementById("r");
  r.innerHTML = viewer.renderProseHTML("[[layer-normalization]]", md);
  viewer.wrapWikilinks(r);
  viewer.upgradeLinks(doc, [{ slug: "layer-normalization", title: "LN", kind: "technique" }]);
  assert.ok(r.querySelector("a.wikilink"), "upgraded to a link first");
  viewer.upgradeLinks(doc, []); // target deleted: refresh with empty index
  assert.strictEqual(r.querySelectorAll("a.wikilink").length, 0, "link downgraded");
  const span = r.querySelector("span.wikilink.missing");
  assert.ok(span, "now a missing span");
  assert.strictEqual(span.getAttribute("data-slug"), "layer-normalization");
  // and it can come back (idempotent reconcile)
  viewer.upgradeLinks(doc, [{ slug: "layer-normalization", title: "LN", kind: "technique" }]);
  assert.ok(r.querySelector("a.wikilink"), "re-upgraded when the target returns");
});

test("renderRelatedRow renders relation chips and is XSS-safe (no innerHTML)", () => {
  const dom = new JSDOM("<!doctype html><body></body>");
  const doc = dom.window.document;
  const related = [
    { slug: "layer-normalization", label: "<img src=x onerror=alert(1)>", relation: "builds-on" },
    { slug: "../secret", label: "nope", relation: "related" }, // unsafe slug: dropped entirely
  ];
  const row = viewer.renderRelatedRow(doc, related);
  assert.ok(row, "row rendered");
  assert.strictEqual(row.className, "related-row");
  const chips = [...row.querySelectorAll(".chip")];
  assert.strictEqual(chips.length, 1, "unsafe-slug entry is dropped, not rendered");
  const relLabel = chips[0].querySelector(".rel");
  assert.strictEqual(relLabel.textContent, "基づく", "relation label localized");
  const link = chips[0].querySelector(".wikilink.pending");
  assert.strictEqual(link.getAttribute("data-slug"), "layer-normalization");
  // The label became a real DOM text node via textContent, never parsed as HTML.
  assert.strictEqual(link.querySelector("img"), null, "no element was injected from the label");
  assert.strictEqual(link.textContent, "<img src=x onerror=alert(1)>");
});

test("renderRelatedRow returns null when there is nothing to show", () => {
  const dom = new JSDOM("<!doctype html><body></body>");
  const doc = dom.window.document;
  assert.strictEqual(viewer.renderRelatedRow(doc, []), null);
  assert.strictEqual(viewer.renderRelatedRow(doc, undefined), null);
});
