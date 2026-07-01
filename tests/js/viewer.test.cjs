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
