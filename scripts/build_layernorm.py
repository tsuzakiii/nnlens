"""Build examples/layer_norm.json and render the full example set into the store.

Adds a second, genuinely-correct explanation (Layer Normalization) so the sidebar
library shows more than one entry. Like build_example.py, the naive view is really
executed so its output is real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from nnlens import config  # noqa: E402
from nnlens.models import Explanation  # noqa: E402
from nnlens.renderer import update_index, write_explanation  # noqa: E402
from nnlens.sandbox import run_python  # noqa: E402

NAIVE_CODE = '''\
import numpy as np

def layer_norm(x, gamma, beta, eps=1e-5):
    mu = x.mean(axis=-1, keepdims=True)          # 平均
    var = x.var(axis=-1, keepdims=True)          # 分散
    x_hat = (x - mu) / np.sqrt(var + eps)        # 正規化 (平均0, 分散1)
    return gamma * x_hat + beta                  # スケール・シフト

rng = np.random.default_rng(0)
x = rng.standard_normal((2, 4))                  # (バッチ, 特徴)
gamma, beta = np.ones(4), np.zeros(4)

y = layer_norm(x, gamma, beta)
print("output shape:", y.shape)
print("row mean ~0:", np.round(y.mean(-1), 6))
print("row std ~1:", np.round(y.std(-1), 4))
'''

OPTIMIZED_CODE = '''\
import torch
import torch.nn.functional as F

x = torch.randn(2, 4)
# normalized_shape で「どの軸をならすか」を指定。gamma/beta は省略時は無し。
y = F.layer_norm(x, normalized_shape=(4,))
print(y.shape)  # torch.Size([2, 4])
'''

WORDS = """\
ニューラルネットの各層では、値の大きさがバラつくと学習が不安定になります。{{正規化}}は、その層のベクトルを毎回「ならして」安定させる仕組みです。

まず1つのベクトルの中で、値の{{平均}}と、散らばり具合（{{分散}}）を測ります。次に、各値から{{平均}}を引いて散らばりで割ることで、平均0・ばらつき1にそろえます（割り算でゼロにならないよう、ごく小さな数＝{{微小量}}を足します）。

ただ毎回そろえるだけだと表現力が落ちるので、最後に学習で決まる倍率（{{スケール}}）とゲタ（{{シフト}}）をかけて、ネットワークが必要な大きさに調整できるようにします。
"""

MATH = """\
各特徴ベクトル {{入力}} $x$（長さ $d$）について、まず{{平均}} $\\mu$ と{{分散}} $\\sigma^2$ を求めます:

$$\\mu = \\frac{1}{d}\\sum_i x_i, \\qquad \\sigma^2 = \\frac{1}{d}\\sum_i (x_i - \\mu)^2$$

各要素を平均0・分散1に{{正規化}}します（{{微小量}} $\\epsilon$ はゼロ割回避）:

$$\\hat{x}_i = \\frac{x_i - \\mu}{\\sqrt{\\sigma^2 + \\epsilon}}$$

最後に学習可能な{{スケール}} $\\gamma$ と{{シフト}} $\\beta$ をかけて戻します:

$$y_i = \\gamma_i\\, \\hat{x}_i + \\beta_i$$
"""

MERMAID = """\
graph LR
  X["入力 x"] --> M["平均 μ・分散 σ²"]
  M --> N["正規化 (x-μ)/√(σ²+ε)"]
  N --> Y["y = γ·x̂ + β"]
"""

LEDGER = [
    {"plain": "入力", "symbol": "x", "formal": "input", "intuition": "層に入るベクトル"},
    {"plain": "平均", "symbol": "μ", "formal": "mean", "intuition": "ベクトルの値の平均"},
    {"plain": "分散", "symbol": "σ²", "formal": "variance", "intuition": "値の散らばり具合"},
    {"plain": "正規化", "symbol": "x̂", "formal": "normalized value", "intuition": "平均0・分散1にそろえた値"},
    {"plain": "微小量", "symbol": "ε", "formal": "epsilon", "intuition": "ゼロ割回避の小さな数"},
    {"plain": "スケール", "symbol": "γ", "formal": "gain (gamma)", "intuition": "学習可能な倍率"},
    {"plain": "シフト", "symbol": "β", "formal": "bias (beta)", "intuition": "学習可能なゲタ"},
]


def build() -> dict:
    run = run_python(NAIVE_CODE)
    explanation = {
        "id": "layer-normalization",
        "title": "Layer Normalization",
        "kind": "technique",
        "language": "ja",
        "summary": "各ベクトルを毎回「平均0・分散1」にならして学習を安定させ、"
        "学習可能な{{スケール}}と{{シフト}}で表現力を戻すテクニック。",
        "source": {
            "name": "Layer Normalization",
            "paper_url": "https://arxiv.org/abs/1607.06450",
            "repo_url": "https://github.com/pytorch/pytorch",
        },
        "related": [
            {
                "slug": "scaled-dot-product-attention",
                "label": "Scaled Dot-Product Attention",
                "relation": "related",
            },
        ],
        "components": [
            {
                "id": "layer-normalization",
                "name": "Layer Normalization",
                "ledger": LEDGER,
                "structure": {
                    "diagram_mermaid": MERMAID,
                    "note": "{{入力}}から{{平均}}・{{分散}}を出し、{{正規化}}してから{{スケール}}・{{シフト}}を掛ける。",
                },
                "words": WORDS,
                "math": MATH,
                "naive": {
                    "code": NAIVE_CODE,
                    "language": "python",
                    "run_stdout": run.get("stdout", ""),
                    "run_ok": run.get("ok"),
                },
                "optimized": {
                    "source": {
                        "repo": "pytorch/pytorch",
                        "path": "aten/src/ATen/native/layer_norm.cpp",
                        "url": "https://github.com/pytorch/pytorch/blob/main/aten/src/ATen/native/layer_norm.cpp",
                    },
                    "code": OPTIMIZED_CODE,
                    "language": "python",
                    "note": "`F.layer_norm` は素の実装と同じ数式を、融合カーネルで1パスで計算する。",
                    "is_self_impl": False,
                },
            }
        ],
    }
    Explanation.model_validate(explanation)
    return explanation


def main() -> None:
    explanation = build()
    out = ROOT / "examples" / "layer_norm.json"
    out.write_text(json.dumps(explanation, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}  (naive run_ok = {explanation['components'][0]['naive']['run_ok']})")

    # Render every bundled example into the store so the library has multiple entries.
    store = config.store_dir()
    for name in ("transformer_attention.json", "layer_norm.json"):
        data = json.loads((ROOT / "examples" / name).read_text(encoding="utf-8"))
        ex = Explanation.model_validate(data)
        write_explanation(ex.model_dump(), store, ex.slug())
        update_index(store, ex.slug(), ex.title, ex.kind)
        print(f"rendered {ex.slug()} -> library")


if __name__ == "__main__":
    main()
