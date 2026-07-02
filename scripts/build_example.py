"""Build examples/transformer_attention.json.

Defines the explanation with real multi-line code (triple-quoted), actually runs
the naive view through the sandbox to fill run_stdout/run_ok, validates it against
the Explanation schema, and writes the JSON fixture. This is both the golden test
fixture and a worked example of the five-view format.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from layerlens.models import Explanation  # noqa: E402
from layerlens.sandbox import run_python  # noqa: E402

NAIVE_CODE = '''\
import numpy as np

def softmax(x, axis=-1):
    x = x - x.max(axis=axis, keepdims=True)   # 安定化のため最大値を引く
    e = np.exp(x)
    return e / e.sum(axis=axis, keepdims=True)

def attention(Q, K, V):
    d = Q.shape[-1]
    scores = Q @ K.transpose(0, 2, 1) / np.sqrt(d)   # スコア (B, T, T)
    weights = softmax(scores, axis=-1)               # 注目度 (行の合計 = 1)
    out = weights @ V                                # 出力 (B, T, d)
    return out, weights

B, T, d = 1, 4, 8
rng = np.random.default_rng(0)
Q = rng.standard_normal((B, T, d))
K = rng.standard_normal((B, T, d))
V = rng.standard_normal((B, T, d))

out, w = attention(Q, K, V)
print("output shape:", out.shape)
print("weights row sums:", np.round(w.sum(-1), 3))
'''

OPTIMIZED_CODE = '''\
import torch
import torch.nn.functional as F

# (B, T, d) の Q, K, V。実際にはヘッド次元 (B, H, T, d) で使うことが多い。
Q = torch.randn(1, 4, 8)
K = torch.randn(1, 4, 8)
V = torch.randn(1, 4, 8)

# 1 行で素の実装と同じ計算をするが、内部では融合カーネル
# (FlashAttention / memory-efficient attention) にディスパッチされ、
# 巨大な (T, T) の注目度行列をメモリに作らずに済む。
out = F.scaled_dot_product_attention(Q, K, V)
print(out.shape)  # torch.Size([1, 4, 8])
'''

WORDS = """\
文章の中のある単語を理解するには、周りのどの単語をどれだけ見ればいいかを決める必要があります。

まず単語ごとに3つの役割を用意します。今の単語が「何を探しているか」を表す{{クエリ}}、
各単語が「何を持っているか」の見出しである{{キー}}、そして各単語が実際に運ぶ中身の{{バリュー}}です。

今の単語の{{クエリ}}を、ほかのすべての単語の{{キー}}と照らし合わせて、どれくらい合っているかの
{{スコア}}を出します。よく合っているほど大きな{{スコア}}になります。

その{{スコア}}を、全部足すと1になるような割合に変換します。これが{{注目度}}です。
「この単語を見るときは、あの単語を6割、その単語を3割……」というふうに、見る配分を決めるわけです。

最後に、その{{注目度}}の配分どおりに各単語の{{バリュー}}を混ぜ合わせたものが、この単語の新しい表現になります。
"""

MATH = """\
各単語はベクトルとして、{{クエリ}} $Q$、{{キー}} $K$、{{バリュー}} $V$ の3つに変換されます
（それぞれ長さ {{次元}} $d$ のベクトル）。

$i$ 番目の単語の{{クエリ}}と $j$ 番目の単語の{{キー}}の内積が、両者の{{スコア}}です。
大きな $d$ で内積が膨らみすぎないよう $\\sqrt{d}$ で割ります:

$$\\text{スコア}_{ij} = \\frac{Q_i \\cdot K_j}{\\sqrt{d}}$$

この{{スコア}}を行方向の softmax にかけると、合計が1の{{注目度}} $\\alpha$ になります:

$$\\alpha_{ij} = \\frac{\\exp(\\text{スコア}_{ij})}{\\sum_k \\exp(\\text{スコア}_{ik})}$$

出力は、{{注目度}}を重みにした{{バリュー}}の加重和です:

$$\\text{出力}_i = \\sum_j \\alpha_{ij}\\, V_j$$

行列でまとめて書くと $\\operatorname{softmax}\\!\\left(\\frac{QK^\\top}{\\sqrt{d}}\\right)V$ の一行になります。
"""

MERMAID = """\
graph LR
  X["入力ベクトル"] --> Q["クエリ Q"]
  X --> K["キー K"]
  X --> V["バリュー V"]
  Q --> S["スコア = Q·Kᵀ / √d"]
  K --> S
  S --> A["softmax → 注目度 α"]
  A --> O["出力 = α·V"]
  V --> O
"""

LEDGER = [
    {"plain": "クエリ", "symbol": "Q", "formal": "query", "intuition": "今の単語が何を探しているか"},
    {"plain": "キー", "symbol": "K", "formal": "key", "intuition": "各単語が何を持っているかの見出し"},
    {"plain": "バリュー", "symbol": "V", "formal": "value", "intuition": "各単語が実際に運ぶ中身"},
    {"plain": "スコア", "symbol": "Q·Kᵀ/√d", "formal": "attention score", "intuition": "クエリとキーの合い具合"},
    {"plain": "注目度", "symbol": "α", "formal": "attention weight", "intuition": "各単語をどれだけ見るかの割合（合計1）"},
    {"plain": "次元", "symbol": "d", "formal": "head dimension", "intuition": "1つのベクトルの長さ"},
]


def build() -> dict:
    run = run_python(NAIVE_CODE)
    explanation = {
        "id": "scaled-dot-product-attention",
        "title": "Scaled Dot-Product Attention",
        "kind": "component",
        "summary": "Transformer の心臓部。各単語が「どの単語をどれだけ見るか」を{{注目度}}として計算し、"
        "その配分で情報を混ぜ合わせる仕組み。",
        "source": {
            "name": "Scaled Dot-Product Attention (Attention Is All You Need)",
            "paper_url": "https://arxiv.org/abs/1706.03762",
            "repo_url": "https://github.com/pytorch/pytorch",
        },
        "related": [
            {"slug": "layer-normalization", "label": "Layer Normalization", "relation": "related"},
        ],
        "components": [
            {
                "id": "scaled-dot-product-attention",
                "name": "Scaled Dot-Product Attention",
                "ledger": LEDGER,
                "structure": {
                    "diagram_mermaid": MERMAID,
                    "note": "入力から{{クエリ}}・{{キー}}・{{バリュー}}を作り、{{スコア}}→{{注目度}}を経て{{バリュー}}を混ぜる。",
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
                        "path": "aten/src/ATen/native/transformers/attention.cpp",
                        "url": "https://github.com/pytorch/pytorch/blob/main/aten/src/ATen/native/transformers/attention.cpp",
                    },
                    "code": OPTIMIZED_CODE,
                    "language": "python",
                    "note": "`F.scaled_dot_product_attention` は素の実装と同じ数式を計算するが、"
                    "内部で FlashAttention 等の融合カーネルにディスパッチし、(T, T) の{{注目度}}行列を"
                    "メモリに保持せずに計算する。",
                    "is_self_impl": False,
                },
            }
        ],
    }
    # Validate before writing so the fixture is always schema-correct.
    Explanation.model_validate(explanation)
    return explanation


def main() -> None:
    explanation = build()
    out = ROOT / "examples" / "transformer_attention.json"
    out.write_text(json.dumps(explanation, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = explanation["components"][0]["naive"]["run_ok"]
    print(f"wrote {out}")
    print(f"naive run_ok = {ok}")
    print("naive stdout:\n" + explanation["components"][0]["naive"]["run_stdout"])


if __name__ == "__main__":
    main()
