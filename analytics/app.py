"""
analytics/app.py
================
アクセス推移ダッシュボード

Supabase の access_logs テーブルから日次アクセス数を集計し、
バージョン別の折れ線グラフで可視化する。

Usage:
    cd streamlit-evolution-lab
    streamlit run analytics/app.py
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ---------------------------------------------------------------------------
# Supabase ヘルパー
# ---------------------------------------------------------------------------
@st.cache_resource
def _get_supabase():
    """Supabase クライアントを返す。secrets 未設定時は None を返す。"""
    try:
        from supabase import create_client
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_PUBLISHABLE_KEY"]
        return create_client(url, key)
    except Exception as e:
        import sys
        print(f"[_get_supabase] ERROR: {type(e).__name__}: {e}", file=sys.stderr)
        return None


@st.cache_data(ttl=300)
def _load_access_logs(days: int) -> pd.DataFrame:
    """
    access_logs テーブルから直近 days 日分のレコードを取得して返す。

    Returns
    -------
    DataFrame with columns: date (datetime.date), version (str)
    接続不可時は空 DataFrame を返す。
    """
    client = _get_supabase()
    if client is None:
        return pd.DataFrame(columns=["date", "hour", "version"])

    try:
        since = (date.today() - timedelta(days=days - 1)).isoformat()
        batch_size = 1000
        offset = 0
        all_rows: list[dict] = []
        while True:
            res = (
                client.table("access_logs")
                .select("version, accessed_at")
                .gte("accessed_at", since)
                .order("accessed_at")
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
            return pd.DataFrame(columns=["date", "version"])

        df = pd.DataFrame(all_rows)
        df["accessed_at"] = pd.to_datetime(df["accessed_at"], utc=True).dt.tz_convert("Asia/Tokyo")
        df["date"] = df["accessed_at"].dt.date
        # tz_localize(None) でタイムゾーン情報を除去（st.bar_chart / st.line_chart が tz-naive を要求するため）
        df["hour"] = df["accessed_at"].dt.floor("h").dt.tz_localize(None)
        return df[["date", "hour", "version"]]

    except Exception:
        return pd.DataFrame(columns=["date", "hour", "version"])


# ---------------------------------------------------------------------------
# ページ設定
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="アクセス推移ダッシュボード",
    page_icon="📊",
    layout="wide",
)

st.title("📊 アクセス推移ダッシュボード")

# ---------------------------------------------------------------------------
# サイドバー
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("フィルター")
    days = st.slider("表示期間（日）", min_value=7, max_value=90, value=30, step=1)

    st.divider()
    if st.button("🔄 データ再取得", use_container_width=True):
        _load_access_logs.clear()
        st.rerun()

# ---------------------------------------------------------------------------
# 接続チェック
# ---------------------------------------------------------------------------
if _get_supabase() is None:
    st.warning(
        "Supabase に接続できません。"
        " `.streamlit/secrets.toml` に `SUPABASE_URL` と "
        "`SUPABASE_PUBLISHABLE_KEY` を設定してください。",
        icon="⚠️",
    )
    st.stop()

# ---------------------------------------------------------------------------
# データ取得
# ---------------------------------------------------------------------------
with st.spinner("データを取得中..."):
    df = _load_access_logs(days)

if df.empty:
    st.info(f"直近 {days} 日間のアクセスデータがありません。", icon="ℹ️")
    st.stop()

# ---------------------------------------------------------------------------
# 集計: 日次
# ---------------------------------------------------------------------------
daily = (
    df.groupby(["date", "version"])
    .size()
    .reset_index(name="count")
)

# ピボット（欠損日は 0 補完）
pivot = (
    daily
    .pivot(index="date", columns="version", values="count")
    .fillna(0)
    .astype(int)
)
pivot.index = pd.to_datetime(pivot.index)
pivot = pivot.sort_index()
pivot.columns.name = None

versions = list(pivot.columns)
total_accesses = int(pivot.values.sum())
total_versions = len(versions)

# ---------------------------------------------------------------------------
# 集計: 時間帯別（1 時間ごと）
# ---------------------------------------------------------------------------
hourly_raw = (
    df.groupby(["hour", "version"])
    .size()
    .reset_index(name="count")
)
hourly_pivot = (
    hourly_raw
    .pivot(index="hour", columns="version", values="count")
    .fillna(0)
    .astype(int)
)
hourly_pivot = hourly_pivot.sort_index()
hourly_pivot.columns.name = None

# ---------------------------------------------------------------------------
# メトリクスカード
# ---------------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("総アクセス数", f"{total_accesses:,}")
col2.metric("バージョン数", total_versions)
col3.metric("集計期間", f"直近 {days} 日間")

st.divider()

# ---------------------------------------------------------------------------
# 折れ線グラフ（バージョン別 日次アクセス数）
# ---------------------------------------------------------------------------
st.subheader("バージョン別 日次アクセス数")

_line_labels = pivot.index.strftime("%Y-%m-%d")
_line_fig = go.Figure()
for ver in versions:
    _line_fig.add_trace(go.Scatter(
        x=_line_labels,
        y=pivot[ver],
        mode="lines+markers",
        name=ver,
    ))
_line_fig.update_layout(
    xaxis_title=None,
    yaxis_title="アクセス数",
    legend_title="バージョン",
    height=320,
    margin=dict(l=0, r=0, t=20, b=0),
)
st.plotly_chart(_line_fig, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# 棒グラフ（1 時間ごとのアクセス数）
# ---------------------------------------------------------------------------
st.subheader("1 時間ごとのアクセス数")

_bar_labels = hourly_pivot.index.strftime("%m/%d %H:%M")
_fig = go.Figure()
for ver in hourly_pivot.columns:
    _fig.add_trace(go.Bar(
        x=_bar_labels,
        y=hourly_pivot[ver],
        name=ver,
    ))
_fig.update_layout(
    barmode="stack",
    xaxis_title=None,
    yaxis_title="アクセス数",
    legend_title="バージョン",
    height=350,
    margin=dict(l=0, r=0, t=20, b=0),
)
st.plotly_chart(_fig, width='stretch')

st.divider()

# ---------------------------------------------------------------------------
# 日次データテーブル（折りたたみ）
# ---------------------------------------------------------------------------
with st.expander("日次データを表示"):
    display_df = (
        pivot
        .rename_axis("日付")
        .reset_index()
        .assign(日付=lambda d: d["日付"].dt.strftime("%Y-%m-%d"))
    )
    # 合計列を追加
    if len(versions) > 1:
        display_df["合計"] = display_df[versions].sum(axis=1)

    st.dataframe(display_df, width='stretch', hide_index=True)
