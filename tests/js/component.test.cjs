"use strict";
// Assembly-logic test: renderComponent must emit all five views, the ledger table,
// the naive run badge, and wire {{term}} marks — checked on a real (jsdom) DOM.

const test = require("node:test");
const assert = require("node:assert");
const path = require("path");
const { JSDOM } = require("jsdom");
const markdownit = require("markdown-it");
const texmath = require("markdown-it-texmath");
const katex = require("katex");

const viewer = require(path.resolve(__dirname, "../../src/nnlens/renderer/viewer.js"));
const md = viewer.createMd({ markdownit, texmath, katex });

function sampleComponent() {
  return {
    id: "demo",
    name: "デモ層",
    ledger: [{ plain: "重み", symbol: "w", formal: "weight", intuition: "掛ける係数" }],
    structure: { diagram_mermaid: "graph LR; A-->B", note: "{{重み}} を掛ける" },
    words: "ここで {{重み}} を使う",
    math: "式: $y = w x$ ここでも {{重み}}",
    naive: { code: "print('hi')", language: "python", run_stdout: "hi\n", run_ok: true },
    optimized: {
      source: { repo: "o/r", path: "a.py", url: "https://github.com/o/r/blob/main/a.py" },
      code: "y = w @ x",
      language: "python",
      note: "速い",
      is_self_impl: false,
    },
  };
}

test("renderComponent emits all five views + ledger + run badge + wired terms", () => {
  const dom = new JSDOM("<!doctype html><body></body>");
  const doc = dom.window.document;
  const ledgerMap = {};
  const sec = viewer.renderComponent(doc, md, sampleComponent(), 0, ledgerMap);

  assert.strictEqual(sec.querySelector("h2").textContent, "デモ層");
  assert.strictEqual(sec.querySelectorAll(".view").length, 5, "five views");
  assert.ok(sec.querySelector("table.ledger"), "ledger table present");
  assert.ok(sec.querySelector(".mermaid").textContent.includes("graph LR"), "mermaid source kept");
  assert.ok(sec.querySelector(".run .badge.ok"), "success badge present");

  // ledger map populated for tooltips
  assert.strictEqual(ledgerMap["重み"].symbol, "w");

  // {{重み}} in prose became term spans (words + math + note = at least 3)
  const terms = sec.querySelectorAll('span.term[data-term="重み"]');
  assert.ok(terms.length >= 3, `expected >=3 wired terms, got ${terms.length}`);

  // optimized source link is a safe anchor
  const a = sec.querySelector(".src-link a");
  assert.ok(a && a.href.startsWith("https://github.com/o/r"), "safe source link");
});

test("renderComponent shows a failure badge when run_ok is false", () => {
  const dom = new JSDOM("<!doctype html><body></body>");
  const doc = dom.window.document;
  const comp = sampleComponent();
  comp.naive.run_ok = false;
  comp.naive.run_stdout = "";
  const sec = viewer.renderComponent(doc, md, comp, 0, {});
  assert.ok(sec.querySelector(".run.fail .badge.fail"), "failure badge present");
});
