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
from collections import Counter
from pathlib import Path

import pandas as pd
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
# アクセスカウンター ヘルパー (Supabase)
# ---------------------------------------------------------------------------
_BOT_UA_RE = re.compile(
    r"\b(bot|spider|crawler)\b"
    r"|uptimerobot|pingdom|statuscake|better\s*uptime|freshping"
    r"|hetrixtools|hyperping|cronitor|monitor|check|health",
    re.IGNORECASE,
)
_BOT_HOURLY_THRESHOLD = 8


@st.cache_resource
def _get_supabase():
    """Supabase クライアントを返す。secrets 未設定時は None を返す。"""
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
        return create_client(url, key)
    except Exception:
        return None


def _increment_counter(version: str) -> None:
    """access_logs テーブルに 1 行 INSERT する。ボット・失敗時はサイレントに無視。"""
    client = _get_supabase()
    if client is None:
        return
    try:
        ua: str = st.context.headers.get("User-Agent") or ""
        if _BOT_UA_RE.search(ua):
            return
        client.table("access_logs").insert({"version": version, "user_agent": ua}).execute()
    except Exception:
        pass


@st.cache_data(ttl=300)
def _load_counts() -> dict[str, int]:
    """全バージョンのアクセス数をボット除外した上で {version: total} 形式で返す。"""
    client = _get_supabase()
    if client is None:
        return {}
    try:
        batch_size = 1000
        offset = 0
        all_rows: list[dict] = []
        while True:
            res = (
                client.table("access_logs")
                .select("version, accessed_at, user_agent")
                .range(offset, offset + batch_size - 1)
                .execute()
            )
            if not res.data:
                break
            all_rows.extend(res.data)
            if len(res.data) < batch_size:
                break
            offset += batch_size

        if not all_rows:
            return {}

        df = pd.DataFrame(all_rows)
        df["accessed_at"] = pd.to_datetime(df["accessed_at"], utc=True).dt.tz_convert("Asia/Tokyo")
        df["hour"] = df["accessed_at"].dt.floor("h").dt.tz_localize(None)
        df["minute"] = df["accessed_at"].dt.minute

        ua_col = df["user_agent"].fillna("")
        is_known_bot = ua_col.str.contains(_BOT_UA_RE, na=False)

        no_ua = ua_col.eq("")
        if no_ua.sum() > 0:
            df_tmp = df.assign(_rem=df["minute"] % 5)
            bot_mask = pd.Series(False, index=df.index)
            for hour, grp in df_tmp[no_ua].groupby("hour"):
                rem_counts = grp["_rem"].value_counts()
                bot_rems = rem_counts[rem_counts >= _BOT_HOURLY_THRESHOLD].index
                if len(bot_rems) > 0:
                    in_hour = no_ua & (df_tmp["hour"] == hour)
                    bot_mask |= in_hour & df_tmp["_rem"].isin(bot_rems)
            is_legacy_bot = bot_mask
        else:
            is_legacy_bot = pd.Series(False, index=df.index)

        df = df[~(is_known_bot | is_legacy_bot)]
        return dict(Counter(df["version"].tolist()))
    except Exception:
        return {}


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

# セッション先頭で 1 回アクセスを記録
if "_visited" not in st.session_state:
    st.session_state["_visited"] = True
    try:
        _is_cloud = st.secrets.get("ENVIRONMENT") == "cloud"
    except Exception:
        _is_cloud = False
    if _is_cloud:
        _increment_counter(_selected_version)

_mod.show()

# サイドバー最下部にアクセスカウンターを表示
_counts = _load_counts()
st.sidebar.divider()
if _counts:
    st.sidebar.metric(label="📊 総アクセス数", value=f"{sum(_counts.values()):,}")
else:
    st.sidebar.caption("📊 総アクセス数")
    st.sidebar.caption("（Supabase 接続後に集計されます）")
