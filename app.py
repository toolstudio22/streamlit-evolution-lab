"""
streamlit-evolution-lab — エントリーポイント

このファイルをルートに置くことで、バージョンを追加しても起動コマンドが変わらない。

    streamlit run app.py

各バージョンフォルダ (v*.*.*/app.py) を自動検出し、
選択されたバージョンの show() を importlib 経由で呼び出す。
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent  # ワークスペースルート


# ---------------------------------------------------------------------------
# ヘルパー
# ---------------------------------------------------------------------------
def scan_versions() -> list[str]:
    """ルート直下の v*.*.* フォルダを自動検出してバージョンリストを返す (降順)。"""
    versions: list[tuple[int, int, int, str]] = []
    for folder in _ROOT.iterdir():
        if not folder.is_dir():
            continue
        m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", folder.name)
        if m and (folder / "app.py").exists():
            versions.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), folder.name))
    versions.sort(reverse=True)  # 降順: 最新バージョンが先頭
    return [v[3] for v in versions]


# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Racing Simulator Telemetry Analysis",
    page_icon="🏎",
    layout="wide",
)

# ---------------------------------------------------------------------------
# サイドバー: 言語選択
# ---------------------------------------------------------------------------
st.sidebar.selectbox(
    "🌐 言語 / Language",
    ["日本語", "English"],
    key="lang_selector",
)
st.sidebar.divider()

# ---------------------------------------------------------------------------
# サイドバー: バージョン選択
# ---------------------------------------------------------------------------
_available_versions = scan_versions()

if not _available_versions:
    st.error(
        "バージョンフォルダが見つかりません。\n\n"
        "`v*.*.*` フォルダに `app.py` を配置してください。"
    )
    st.stop()

st.sidebar.selectbox(
    "🔖 Streamlit Version",
    _available_versions,
    key="version_selector",
    help="デモを確認したい Streamlit バージョンを選択してください。"
         " v*.*.*/ フォルダ内の app.py が自動検出されます。",
)
st.sidebar.divider()

_selected_version: str = st.session_state["version_selector"]

# ---------------------------------------------------------------------------
# バージョン app.py をロードして show() を呼び出す
# ---------------------------------------------------------------------------
_target_app = _ROOT / _selected_version / "app.py"

if not _target_app.exists():
    st.error(f"`{_selected_version}/app.py` が見つかりません。")
    st.stop()

_spec = importlib.util.spec_from_file_location(
    f"app_{_selected_version.replace('.', '_')}", _target_app
)
if _spec is None or _spec.loader is None:
    st.error(f"`{_selected_version}/app.py` の読み込みに失敗しました。")
    st.stop()

_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

if not hasattr(_mod, "show"):
    st.error(
        f"`{_selected_version}/app.py` に `show()` 関数が定義されていません。\n\n"
        "各バージョンの `app.py` は `def show():` を公開してください。"
    )
    st.stop()

_mod.show()
