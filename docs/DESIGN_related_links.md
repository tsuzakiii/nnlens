# 設計書: 解説間リンク（related / wikilink）

日付: 2026-07-02 / 対象: nnlens v0.1 / 状態: 実装待ち

## 目的

ライブラリが現状フラットで、解説同士の関係（「Transformer block は attention と LayerNorm を含む」「PRISM は TTT の並列化」）を表現できない。
解説に **related フィールド**と**本文中の wikilink** を導入し、解説間を相互リンクして知識グラフとして育つようにする。

## 変更一覧（この5点で完結。スコープ外のことはしない）

### 1. スキーマ (`src/nnlens/models.py`)

`Explanation` に追加:

```python
class RelatedRef(BaseModel):
    slug: str = Field(..., description="Slug of the related explanation, e.g. 'layer-normalization'.")
    label: str = Field("", description="Display label; defaults to the slug at render time.")
    relation: Literal["contains", "part-of", "builds-on", "related"] = "related"

class Explanation(BaseModel):
    ...
    related: list[RelatedRef] = Field(default_factory=list)
```

- `slug` は `Explanation.slug()` と同じ safe 形式を期待するが、**バリデーションで弾かない**（正規化は不要、レンダラー側で存在チェックするため）。ただし `/` `\` `..` を含むものは pydantic validator で reject する（リンク先パスに使うため）。
- 既存 JSON（related 無し）は default `[]` で後方互換。

### 2. MCP ツール追加 (`src/nnlens/server.py`)

```python
@mcp.tool()
def list_library() -> dict:
    """Return every explanation in the local library ({slug, title, kind} each)."""
    return {"explanations": reconcile_index(config.store_dir())}
```

- ホストが**既存の解説の slug を知ってから** related / wikilink を張れるようにするのが目的。
- `reconcile_index` は `nnlens.renderer` から import（既存関数、ディスク走査つき）。

### 3. プロンプト (`src/nnlens/prompts.py`)

`EXPLAIN_PROMPT` に追記（How to work セクションと JSON shape の両方）:

- 手順に: 「最初に `list_library` を呼び、既存の解説一覧を確認する。関連する解説があれば `related` に張る。本文（words / math / summary / note）中で他の解説に言及するときは `[[slug]]` または `[[slug|表示テキスト]]` と書く（存在する slug のみ）。」
- JSON shape 例に `"related": [{ "slug": "…", "label": "…", "relation": "contains | part-of | builds-on | related" }]` を追加。
- 注意: このファイルは `.format(topic=...)` を使うので **literal な `{` `}` は `{{` `}}` にエスケープ**する（既存コード参照）。

### 4. レンダラー (`src/nnlens/renderer/viewer.js` + `template.html` の CSS)

#### 4a. 関連チップ（ヘッダー直下）

- `DATA.related` が非空なら、header 内（`.src` の後）に `div.related-row` を描画。
- 各エントリはチップ: `relation` の日本語ラベル + リンク。
  - `contains` →「含む」/ `part-of` →「一部」/ `builds-on` →「基づく」/ `related` →「関連」
- 表示テキストは `label || slug`（ライブラリ index にあれば index の title を優先して良い）。

#### 4b. wikilink（本文中の `[[slug]]` / `[[slug|text]]`）

- `wrapTerms` と同じ **DOM text-node walk** 方式で実装（`innerHTML` への文字列注入は禁止。code/pre/katex/mermaid/term/既存リンク内はスキップ — wrapTerms の skip 規則を流用しつつ `A` タグ内もスキップに追加）。
- 正規表現: `/\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g`。slug 部に `/` `\` `..` を含むものはリンク化せずプレーンテキストのまま。

#### 4c. 存在チェックと2段階アップグレード

- チップ / wikilink は最初 `<span class="wikilink pending" data-slug data-label>` として描画（この時点ではリンクでない）。
- 既存の `refreshLibrary` が index を fetch した後に `upgradeLinks(doc, indexEntries)` を呼び:
  - slug が index に**ある** → `<a href="./<encodeURIComponent(slug)>.html">` に置換（class `wikilink`）。
  - **ない** → class を `wikilink missing` にし `title="まだ生成されていません"`（グレー表示のまま）。これは「次に生成すべきもの」の可視化を兼ねる。
- `file://`（index が取れない）ではアップグレードが走らず pending 表示のまま = 安全に劣化。

#### 4d. CSS（template.html）

- `.related-row`（flex, gap, 小さめ）と `.chip`（角丸・枠線・relation ラベルは muted）。
- `.wikilink`（accent 色 + 下線なし hover 下線）、`.wikilink.missing` / `.wikilink.pending`（muted、cursor:default）。

### 5. 例・テスト

- `examples/transformer_attention.json` と `examples/layer_norm.json` に相互の `related` を追加（relation は両方向 `related` で良い）。attention の words 内の LayerNorm 言及は無いので本文はいじらない（related チップのみで十分）。**ビルドスクリプト（scripts/build_example.py / build_layernorm.py）側の dict にも同じ変更を入れて再生成**すること（fixture は生成物）。
- Python テスト (`tests/test_models.py` など):
  - related 付き Explanation が validate を通る / 埋め込み JSON（build_html 出力）に related が現れる。
  - `slug` に `../x` を入れると ValidationError。
  - `list_library` ツールが登録されている（`server.mcp.list_tools()` に名前が出る — 既存の introspect パターン参照、または tests/test_integration.py 流に直接関数を呼ぶ）。
- JS テスト (`tests/js/`):
  - wikilink: `[[layer-normalization]]` がプロース中で span になり、`upgradeLinks` で `<a href="./layer-normalization.html">` になる。index に無い slug は `missing` になる。
  - コードブロック内の `[[x]]` はそのまま（walk の skip）。
  - related チップ: 描画される・XSS 安全（textContent / createElement のみ）。
- 既存テストが全部 green のまま（23 Python + 8 JS + 追加分）。

## 受け入れ条件

1. `pytest`（venv: `.venv/Scripts/python.exe -m pytest -q`）と `cd tests/js && node --test` が全 green。
2. `scripts/build_example.py` → `scripts/build_layernorm.py` を実行し直すと、attention / layer_norm のページ双方のヘッダーに相互の「関連」チップが出て、クリックで行き来できる（store: `~/.nnlens/store`、サーバー再起動が必要なら 8787 の既存プロセスを止めてから `scripts/demo_render.py` を background で）。
3. 存在しない slug への related / wikilink はグレー表示（リンク化されない）で、ページは壊れない。
4. XSS 安全: すべて createElement / textContent。`innerHTML` への注入を新規に増やさない。

## 実装上の注意（このリポジトリの流儀）

- Edit の前に必ず対象ファイルを Read する。
- viewer.js はブラウザ + Node(jsdom) 両対応（末尾の `module.exports` に新関数 `upgradeLinks` / wikilink 処理関数を追加してテスト可能にする）。
- `prompts.py` の `{` エスケープを壊さない（`.format()` が通ることをテストで確認: 既存の import + `EXPLAIN_PROMPT.format(topic="x")` がエラーにならない）。
- コミットはしない（レビュー後にこちらで行う）。
