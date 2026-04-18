# Streamlit 1.56.0 新機能「st.menu_button」でツールバーとドロップダウンメニューが驚くほど簡単に作れるようになった話

---

## はじめに

2026年3月31日にリリースされた **Streamlit 1.56.0** の目玉機能の一つが **`st.menu_button`** です。

「ボタンをクリックしたらメニューが開いて、項目を選べる」――アプリのツールバーやアクションリストを作るとき、一度は欲しいと思ったことがある機能ではないでしょうか。

この記事では、`st.menu_button` が**何を解決したのか**を、Before/After の比較を交えながらわかりやすく解説します。

---

## そもそも「ドロップダウンボタン」とはどんなUIか

**ドロップダウンボタン** とは、クリックするとメニューが展開し、複数のアクションを選択できるUIコンポーネントです。

```
[エクスポート ▼]  ← ボタン
      ┌──────────┐
      │ CSV 形式  │  ← クリックで選択
      │ JSON 形式 │
      │ HTML レポート │
      └──────────┘
```

「1つの操作のバリエーションをまとめて提示する」という設計で、ツールバーやファイル操作メニューなどでよく使われます。

---

## Before ― v1.55.0 以前の"苦しい回避策"

v1.55.0 までは、このようなUIを作るための専用ウィジェットがありませんでした。よく使われた回避策を見てみましょう。

### 回避策① st.selectbox を流用する

```python
import streamlit as st

# selectbox をメニュー代わりにする
action = st.selectbox(
    "操作を選択",
    ["選択してください", "CSV 形式", "JSON 形式", "HTML レポート"],
    index=0,
)

if action == "CSV 形式":
    st.write("CSVとしてエクスポートします")
elif action == "JSON 形式":
    st.write("JSONとしてエクスポートします")
```

**問題点:**
- ボタンではなくセレクトボックスなので、**見た目がメニューに見えない**
- 「選択してください」という初期値が常に表示される
- **選択後もラベルが変わってしまう**（ボタンの感覚とが異なる）
- 実行後もセレクトボックスに選択値が残り続けるため、意図しない二重実行のリスクがある

### 回避策② st.popover でボタンを並べる

```python
import streamlit as st

with st.popover("エクスポート"):
    if st.button("CSV 形式"):
        st.write("CSVとしてエクスポートします")
    if st.button("JSON 形式"):
        st.write("JSONとしてエクスポートします")
    if st.button("HTML レポート"):
        st.write("HTMLレポートを生成します")
```

**問題点:**
- popoverを閉じる操作と選択操作が**ネストされた2段階**になる
- 選択後にpopoverが自動で閉じないため、UXが不自然
- ボタンの戻り値が `True/False` なので、**どれが選ばれたか**を変数一つで管理できない
- `st.columns` でツールバーを並べるとコードが大幅に複雑になる

### これらに共通する課題

```
# v1.55.0 でよくあったツールバーのコード（※擬似コード）

col1, col2, col3 = st.columns(3)

with col1:
    with st.popover("エクスポート"):
        if st.button("CSV"):
            st.session_state.action = "csv"
        if st.button("JSON"):
            st.session_state.action = "json"

with col2:
    with st.popover("チャート"):
        if st.button("スピード"):
            st.session_state.chart = "speed"
        if st.button("RPM"):
            st.session_state.chart = "rpm"

# ↑ ネストが深く、session_stateの手動管理が必要
```

---

## After ― v1.56.0 の `st.menu_button` で劇的にシンプルになった

`st.menu_button` はこれらの不便をすべて解決しました。

```python
import streamlit as st

action = st.menu_button(
    "エクスポート",
    options=["CSV 形式", "JSON 形式", "HTML レポート"],
)

if action == "CSV 形式":
    st.write("CSVとしてエクスポートします")
elif action == "JSON 形式":
    st.write("JSONとしてエクスポートします")
elif action == "HTML レポート":
    st.write("HTMLレポートを生成します")
```

### ポイント：`st.button` と `st.selectbox` の「いいとこ取り」

| 特性 | st.button | st.selectbox | st.menu_button |
|---|---|---|---|
| ボタンの見た目 | ✅ | ❌ | ✅ |
| 複数オプションから選択 | ❌ | ✅ | ✅ |
| 選択後ラベルが変わらない | ✅ | ❌ | ✅ |
| 選択値が次のリランでリセット | ✅ | ❌ | ✅ |
| 返り値で選択内容を判定 | ❌ (True/False) | ✅ | ✅ |

`st.menu_button` は選択されたオプション文字列を返し、**次のリランでは `None` にリセット**されます。これは `st.button` の「クリックしたときだけ `True`」という挙動と同じ設計思想です。

---

## 全パラメータ解説

```python
action = st.menu_button(
    label="エクスポート",           # ボタンのラベル（必須）
    options=["CSV", "JSON"],        # 選択肢のリスト（必須）
    type="secondary",               # ボタンのスタイル
    icon=":material/download:",     # ボタンアイコン
    width="content",                # ボタン幅
    format_func=lambda x: x,        # 表示名変換関数
    disabled=False,                  # 無効化フラグ
    help="ツールチップのテキスト",   # ホバー時のヒント
    on_click=None,                   # 選択時コールバック
    key=None,                        # ウィジェットキー
)
```

### `type` パラメータ ― ボタンのスタイル

```python
# primary: アプリのメインカラーで強調表示
st.menu_button("実行", options=["A", "B"], type="primary")

# secondary（デフォルト）: 通常のボタン
st.menu_button("操作", options=["A", "B"], type="secondary")

# tertiary: 枠なし・背景なしのプレーンテキスト
st.menu_button("詳細", options=["A", "B"], type="tertiary")
```

用途に応じて使い分けることで、ユーザーに視覚的な優先度を伝えられます。

### `icon` パラメータ ― Material アイコンか絵文字

```python
# Material Symbols ライブラリのアイコン
st.menu_button("ダウンロード", options=["CSV", "JSON"],
               icon=":material/download:")

st.menu_button("設定", options=["テーマ", "言語"],
               icon=":material/settings:")

# 絵文字でも OK
st.menu_button("エクスポート", options=["CSV", "JSON"], icon="📤")
```

### `format_func` パラメータ ― 内部値と表示名を分離

`st.selectbox` と同様、**内部で扱う値（キー）と表示するラベルを別々に管理**できます。

```python
# 内部値: "speed", "throttle", "rpm"（英語）
# 表示名: 日本語で見やすく
action = st.menu_button(
    "チャート切替",
    options=["speed", "throttle", "rpm"],
    format_func=lambda x: {
        "speed":    "📈 スピード",
        "throttle": "🎮 スロットル",
        "rpm":      "⚙ RPM",
    }[x],
    icon=":material/bar_chart:",
)

if action:
    st.write(f"内部値: {action}")   # → "speed" などが返る
```

戻り値は表示名ではなく**元の `options` の値**が返るため、後続の処理がシンプルになります。

### `width` パラメータ ― ボタン幅の制御

```python
# content（デフォルト）: テキスト幅に合わせる
st.menu_button("短い", options=["A", "B"], width="content")

# stretch: 親コンテナ幅いっぱいに広げる
st.menu_button("横幅いっぱい", options=["A", "B"], width="stretch")

# 固定ピクセル数
st.menu_button("固定幅", options=["A", "B"], width=200)
```

`st.columns` でツールバーを作る場合、`width="stretch"` にするとボタンの幅が揃ってきれいに仕上がります。

---

## 実践：ツールバーを作る

`st.menu_button` の真価が発揮されるのが、複数のドロップダウンボタンを横並びにする**ツールバーパターン**です。

### Before（v1.55.0）

```python
import streamlit as st

col1, col2, col3 = st.columns(3)

with col1:
    with st.popover("📤 エクスポート"):
        if st.button("CSV", use_container_width=True):
            st.session_state.export_type = "csv"
        if st.button("JSON", use_container_width=True):
            st.session_state.export_type = "json"

with col2:
    with st.popover("📈 チャート切替"):
        for name in ["スピード", "スロットル", "RPM"]:
            if st.button(name, use_container_width=True):
                st.session_state.chart = name

with col3:
    with st.popover("📊 統計ライン"):
        for name in ["最大値", "平均値", "最小値"]:
            if st.button(name, use_container_width=True):
                st.session_state.stat = name

# 後続処理で session_state を参照……
export_type = st.session_state.get("export_type")
current_chart = st.session_state.get("chart", "スピード")
current_stat = st.session_state.get("stat", "最大値")
```

**問題点:** コードが長く、`session_state` の手動管理が不可欠。popoverのネストで可読性も低い。

### After（v1.56.0）

```python
import streamlit as st

col1, col2, col3 = st.columns(3)

with col1:
    export_action = st.menu_button(
        "エクスポート",
        options=["CSV 形式", "JSON 形式", "HTML レポート"],
        type="primary",
        icon=":material/download:",
        width="stretch",
    )

with col2:
    chart_action = st.menu_button(
        "チャート切替",
        options=["speed", "throttle", "rpm"],
        format_func=lambda x: {"speed":"スピード","throttle":"スロットル","rpm":"RPM"}[x],
        icon=":material/bar_chart:",
        width="stretch",
    )

with col3:
    stat_action = st.menu_button(
        "統計ライン",
        options=["max", "mean", "min"],
        format_func=lambda x: {"max":"最大値","mean":"平均値","min":"最小値"}[x],
        icon=":material/analytics:",
        width="stretch",
    )

# 選択されたときだけ session_state を更新
if chart_action:
    st.session_state.chart = chart_action
if stat_action:
    st.session_state.stat = stat_action

# エクスポート処理
if export_action == "CSV 形式":
    st.download_button("⬇ CSVダウンロード", data="...", file_name="data.csv")
```

**改善点:** ネストが消え、`session_state` の更新も選択があったときだけ行えばよい。コードが圧倒的に短く、読みやすくなりました。

---

## `st.menu_button` の「リセット挙動」を理解する

`st.menu_button` が返す値の挙動は、**`st.button` と同じ**です。これが他のウィジェットとの大きな違いです。

```
[1回目のリラン] 未操作
  → action = None

[ユーザーが "CSV 形式" を選択 → リラン]
  → action = "CSV 形式"  ← この1回だけ

[次のリラン（何も操作なし）]
  → action = None  ← リセットされる
```

```python
action = st.menu_button("操作", options=["実行", "キャンセル"])

if action == "実行":
    do_something()        # 選択したリランの1回だけ実行される
    # ← st.selectbox と違い、次のリランでは実行されない
```

これにより、ダウンロードや外部API呼び出しなど「一度だけ実行したい処理」を安全に書けます。

### `session_state` と組み合わせると状態が引き継げる

選択を次のリランにも持ち越したい場合は、`session_state` を使います。

```python
if "chart_type" not in st.session_state:
    st.session_state.chart_type = "speed"

chart_action = st.menu_button("チャート切替", options=["speed", "rpm"])

if chart_action:  # 選択があったリランだけ更新
    st.session_state.chart_type = chart_action

# ← 常に最後に選ばれた値を使える
current_chart = st.session_state.chart_type
```

---

## よくある疑問

### Q. `st.selectbox` と何が違うの？

最大の違いは **UIが「選択ボックス」ではなく「ボタン」** な点です。

| | st.selectbox | st.menu_button |
|---|---|---|
| 見た目 | プルダウン選択ボックス | クリック式ボタン |
| 選択後のラベル | **選択値に変わる** | **変わらない** |
| 返り値の持続 | ずっと保持 | 次のリランでNullにリセット |
| 用途 | 設定値の選択・保持 | **アクションの実行トリガー** |

ツールバーやワンショットの操作トリガーには `st.menu_button`、フォームや設定画面の選択肢には `st.selectbox` が適しています。

### Q. `options` にアイコンを入れることはできる？

はい。`options` のラベルにはMarkdownが使えるので、絵文字や画像を含められます。また `format_func` で動的に変換することもできます。

```python
st.menu_button(
    "操作",
    options=["download", "edit", "delete"],
    format_func=lambda x: {
        "download": "⬇ ダウンロード",
        "edit":     "✏️ 編集",
        "delete":   "🗑 削除",
    }[x],
)
```

### Q. 旧来の `st.popover + st.button` は廃止になる？

いいえ、廃止にはなっていません。`st.popover` は引き続き使えますし、ボタン以外の任意のウィジェットをポップオーバーに入れたい場合には今後も有効です。  
シンプルなドロップダウンメニュー・ツールバーには **`st.menu_button` を使うのが推奨**です。

### Q. `disabled=True` でも見た目を示せる？

はい。「近日公開予定」や「権限がないため使用不可」などのUIをグレーアウトした状態で表示できます。

```python
st.menu_button(
    "詳細設定",
    options=["オプションA", "オプションB"],
    icon=":material/lock:",
    type="tertiary",
    disabled=True,
    help="管理者のみ使用できます",
)
```

---

## まとめ

| | v1.55.0 以前（回避策） | v1.56.0 `st.menu_button` |
|---|---|---|
| ドロップダウンボタンの実現 | `st.popover` + `st.button` のネスト | `st.menu_button` 1つ |
| 返り値 | `True/False` × 複数変数 | 選択文字列を1変数で受け取り |
| 選択後のボタンラベル | 変わる(selectbox) or 変わらない(popover) | **常に変わらない** |
| ツールバー構築のコード量 | 多い（session_stateも手動管理） | **少ない・すっきり** |
| ボタンスタイルの統一 | 困難 | `type` / `width` で簡単 |

**「ボタンの見た目のまま、複数のアクションを1つにまとめる。」**

それが `st.menu_button` が1.56.0でもたらした恩恵です。ツールバーや操作メニューを作るときは、ぜひ `st.menu_button` を使ってみてください。

---

## 参考リンク

- [st.menu_button 公式ドキュメント](https://docs.streamlit.io/develop/api-reference/widgets/st.menu_button)
- [Streamlit 1.56.0 リリースノート](https://docs.streamlit.io/develop/quick-reference/release-notes)
- [GitHub PR #13981](https://github.com/streamlit/streamlit/pull/13981)
