# Streamlit 1.56.0 新機能「st.iframe」で外部コンテンツの埋め込みが劇的にシンプルになった話

---

## はじめに

2026年3月31日にリリースされた **Streamlit 1.56.0** には、さまざまな新機能が追加されました。その中でも今回紹介する **`st.iframe`** は、「HTMLや外部URLをアプリに埋め込む」という定番ユースケースを、かつてないほどシンプルに書けるようにしてくれた機能です。

この記事では、**Streamlit初心者の方**に向けて「何が変わったのか」「何がうれしいのか」を実感していただけるよう、Before/After の比較を交えながら解説します。

---

## そもそも「iframe」って何？

**iframe（インラインフレーム）** は、ウェブページの中に別のページやHTMLを「枠ごと埋め込む」HTML要素です。

```html
<iframe src="https://example.com" width="100%" height="400"></iframe>
```

Streamlitアプリでも、レポートHTML・地図・PDF・カスタムビジュアルなどを埋め込みたい場面はよくあります。

---

## Before ― v1.55.0 以前の"二刀流"

v1.55.0 までは、埋め込みたいコンテンツの種類によって **関数を使い分ける** 必要がありました。

```python
import streamlit.components.v1 as components

# HTML文字列を埋め込みたいとき → components.html()
components.html(
    "<h1 style='color:red'>Hello!</h1>",
    height=200,
)

# 外部URLを埋め込みたいとき → components.iframe()
components.iframe(
    "https://www.openstreetmap.org/export/embed.html?...",
    height=400,
)
```

これには、次の **3つの不便な点** がありました。

### 不便その① 関数が2つある

「HTMLを埋め込む関数」と「URLを埋め込む関数」が別々。どっちを使うんだっけ、と毎回悩む。

### 不便その② 高さが手動指定のみ

`height=300` のように**必ず数値を渡さなければならず**、コンテンツに合わせた自動調整ができない。コンテンツが短ければ余白が余り、長ければスクロールバーが出る。

```python
# コンテンツが50pxしかないのに300px確保してしまう……
components.html("<p>短いHTML</p>", height=300)
```

### 不便その③ ファイルを直接渡せない

ローカルの `report.html` を表示したい場合、`Path`オブジェクトをそのまま渡せないため、いちど読み込んで文字列に変換してから渡す必要があった。

```python
from pathlib import Path

# こういう書き方はできなかった
# components.html(Path("report.html"))  # ← エラー

# 毎回こう書く必要があった
html_text = Path("report.html").read_text(encoding="utf-8")
components.html(html_text, height=800)
```

---

## After ― v1.56.0 の `st.iframe` で全部まとまった

`st.iframe` はこれらの不便をすべて解決しました。

```python
import streamlit as st
from pathlib import Path

# ① 外部URL → そのまま渡すだけ
st.iframe("https://www.openstreetmap.org/export/embed.html?...", height=600)

# ② HTML文字列 → そのまま渡すだけ（自動判別）
st.iframe("<h1 style='color:red'>Hello!</h1>")

# ③ ローカルファイル → Path をそのまま渡すだけ
st.iframe(Path("reports/telemetry.html"), height=800)
```

### ポイント：入力の種類を自動判別してくれる

| 渡したもの | Streamlitがやること |
|---|---|
| `http://` や `https://` で始まる文字列 | 外部URLとしてiframeに読み込む |
| `/` で始まる文字列 | 静的ファイルサービング経由で読み込む |
| `<html>` などHTML文字列 | インラインHTMLとして埋め込む |
| `Path("...")` オブジェクト | ファイルを自動で読み込んで埋め込む |

関数が1つになっただけでなく、**データの種類を判別して適切に処理**してくれます。

---

## 特に革命的な「height="content"」

個人的に一番うれしいのが **`height="content"`（デフォルト値）** の追加です。

```python
# 高さを指定しなくてもコンテンツにぴったり合う！
st.iframe("<p>短いHTMLです</p>")          # → 自動で小さくなる
st.iframe("<div style='height:500px'>...</div>")  # → 自動で大きくなる
```

Streamlitがフレーム内のHTMLコンテンツの実際の高さを計測して、iframeのサイズを自動で調整してくれます。余計な余白も、不要なスクロールバーも出ません。

### height の3パターン

| 値 | 挙動 | 用途 |
|---|---|---|
| `"content"` （デフォルト） | HTMLの実際の高さに自動フィット | インラインHTML・ローカルファイル |
| `"stretch"` | 画面の縦幅いっぱいに広げる | ダッシュボード全画面表示 |
| 整数（例: `800`） | 固定ピクセル | サイズを厳密に制御したいとき |

> ⚠️ **外部URLの場合の注意点**  
> `height="content"` は外部URLには使えません（クロスオリジン制限でiframe内の高さを計測できないため）。外部URLには整数または `"stretch"` を使いましょう。

---

## 実際のコード比較

### ラップサマリーをカスタムHTMLで表示する例

**Before（v1.55.0）:**

```python
import streamlit.components.v1 as components

summary_html = """
<style>
  .card { background: #1e2a3a; padding: 20px; border-radius: 12px; color: white; }
  .time { font-size: 3rem; font-weight: bold; color: #58a6ff; }
</style>
<div class="card">
  <div class="time">1:39.208</div>
  <p>最高速度: 287 km/h</p>
</div>
"""

# 固定heightしか指定できない。余白が出るか、足りないか……
components.html(summary_html, height=200)
```

**After（v1.56.0）:**

```python
import streamlit as st

summary_html = """
<style>
  .card { background: #1e2a3a; padding: 20px; border-radius: 12px; color: white; }
  .time { font-size: 3rem; font-weight: bold; color: #58a6ff; }
</style>
<div class="card">
  <div class="time">1:39.208</div>
  <p>最高速度: 287 km/h</p>
</div>
"""

# height="content"（省略可）でコンテンツに自動フィット！
st.iframe(summary_html)
```

### Plotlyレポートファイルを表示する例

**Before（v1.55.0）:**

```python
from pathlib import Path
import streamlit.components.v1 as components

# ファイルを読んで文字列にする手間が必要
html_content = Path("reports/telemetry.html").read_text(encoding="utf-8")
components.html(html_content, height=800)
```

**After（v1.56.0）:**

```python
from pathlib import Path
import streamlit as st

# Pathをそのまま渡すだけ！
st.iframe(Path("reports/telemetry.html"), height=800)
```

---

## よくある疑問

### Q. 外部URLが「接続拒否」になる場合は？

`docs.streamlit.io` や `github.com` などは **X-Frame-Options** という設定でiframe埋め込みをブロックしています。これはサイト側の制限なので、Streamlitの問題ではありません。

iframe埋め込みに対応しているサービスの例:
- **OpenStreetMap** — 地図の埋め込み
- **YouTube**（Embed URL形式）— 動画の埋め込み
- 自分で作ったHTMLファイルやレポート

### Q. 旧来の `components.html()` は使えなくなる？

いいえ、廃止にはなっていません。引き続き使えます。ただ今後は **`st.iframe` を使うのが推奨**です。

### Q. PDFを表示できる？

はい。`Path("document.pdf")` を渡すと、Streamlitがメディアストレージ経由でブラウザのネイティブPDFビューアを使って表示します。

```python
st.iframe(Path("race_report.pdf"), height=700)
```

---

## まとめ

| | v1.55.0 以前 | v1.56.0 `st.iframe` |
|---|---|---|
| HTML文字列の埋め込み | `components.html()` | `st.iframe()` |
| 外部URLの埋め込み | `components.iframe()` | `st.iframe()` |
| ファイルの埋め込み | 読んで文字列にしてから | `Path` をそのまま |
| 高さの自動調整 | ❌ できない | ✅ `height="content"` |
| 関数の数 | 2つ | **1つ** |

**「HTMLとURLとファイルを1つの関数で。高さは自動。」**

それが `st.iframe` が1.56.0でもたらしてくれたシンプルさです。埋め込み系の処理を書くときは、まず `st.iframe` を試してみてください。

---

## 参考リンク

- [st.iframe 公式ドキュメント](https://docs.streamlit.io/develop/api-reference/text/st.iframe)
- [Streamlit 1.56.0 リリースノート](https://docs.streamlit.io/develop/quick-reference/release-notes)
- [GitHub リリースページ](https://github.com/streamlit/streamlit/releases/tag/1.56.0)
