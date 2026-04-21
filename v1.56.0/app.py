"""
GT7 Race Telemetry Analyzer
Streamlit v1.56.0 – st.iframe / st.menu_button デモアプリ

【バージョン選択機能】
サイドバー最上部の「🔖 Streamlit バージョン」セレクターで確認したいバージョンを
切り替えられます。ワークスペースルート配下の v*.*.* フォルダを自動検出し、
対象バージョンの app.py に定義された show() 関数を動的にロードして呼び出します。
将来バージョンのデモを追加する際は v*/app.py に show() 関数を定義してください。

【このバージョンで実演する機能 (v1.56.0)】
st.iframe の 3 つの使い方:
  Tab 1: HTML 文字列 (インライン HTML でラップサマリーカード)
  Tab 2: ローカル HTML ファイル (Plotly テレメトリレポートを Path で渡す)
  Tab 3: 外部 URL (OpenStreetMap を埋め込み)
st.menu_button の使い方:
  Tab 4: ツールバー形式のメニューボタン (エクスポート / チャート切替 / 統計ライン)
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
# デフォルト: リポジトリルート直下の共通サンプルデータフォルダ
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"

# このファイルが属するバージョン識別子（フォルダ名と一致させること）
_THIS_VERSION = "v1.56.0"

# ---------------------------------------------------------------------------
# アクセスカウンター ヘルパー (Supabase)
# ---------------------------------------------------------------------------
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
    """access_logs テーブルに 1 行 INSERT する。失敗時はサイレントに無視。"""
    client = _get_supabase()
    if client is None:
        return
    try:
        client.table("access_logs").insert({"version": version}).execute()
    except Exception:
        pass


def _load_counts() -> dict[str, int]:
    """全バージョンのアクセス数を {version: total} 形式で返す。"""
    client = _get_supabase()
    if client is None:
        return {}
    try:
        res = client.table("access_logs").select("version").execute()
        return dict(Counter(row["version"] for row in res.data))
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# 翻訳ヘルパー
# locales/ja.json / locales/en.json を読み込んで UI 文字列辞書を返す
# @st.cache_data によりリロード時の I/O を削減する
# ---------------------------------------------------------------------------
@st.cache_data
def load_translations(lang: str) -> dict:
    """言語コードに対応する翻訳 JSON を読み込んで返す。"""
    locale_path = Path(__file__).parent / "locales" / f"{lang}.json"
    with locale_path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# バージョン発見ヘルパー
# ---------------------------------------------------------------------------
def scan_versions() -> list[str]:
    """ワークスペースルート配下の v*.*.* フォルダを自動検出してバージョンリストを返す。

    各バージョンの app.py が show() 関数を公開していれば、
    そのバージョンのデモをこのエントリーポイントから呼び出せる。
    """
    root = Path(__file__).parent.parent
    versions: list[tuple[int, int, int, str]] = []
    for folder in root.iterdir():
        if not folder.is_dir():
            continue
        m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", folder.name)
        if m and (folder / "app.py").exists():
            versions.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), folder.name))
    versions.sort()
    return [v[3] for v in versions]


# ---------------------------------------------------------------------------
# レポート出力先 (Tab 2 で Plotly HTML を書き出すフォルダ)
# ---------------------------------------------------------------------------
REPORTS_DIR = Path(__file__).parent / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ファイル名パターン: 260407_232133_Live_Fuji_Supra18_RM_Dry_L01_1m41s220.csv
_FNAME_RE = re.compile(
    r"^(\d{6})_(\d{6})_(\w+)_(\w+)_(\w+)_(\w+)_(\w+)_L(\d+)_(\d+m\d+s\d+)\.csv$"
)


# ---------------------------------------------------------------------------
# データクラス
# ---------------------------------------------------------------------------
@dataclass
class LapMeta:
    path: Path
    date: str          # "260407"
    time: str          # "232133"
    session_id: str    # date + "_" + time → セッション識別に使う
    source: str        # "Live"
    circuit: str       # "Fuji"
    car: str           # "Supra18"
    tyre: str          # "RM"
    condition: str     # "Dry"
    lap_no: int
    lap_time_str: str  # "1m41s220"

    @property
    def lap_time_ms(self) -> int:
        m = re.match(r"(\d+)m(\d+)s(\d+)", self.lap_time_str)
        if m:
            minutes, seconds, millis = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return (minutes * 60 + seconds) * 1000 + millis
        return 0

    @property
    def lap_time_display(self) -> str:
        ms = self.lap_time_ms
        m = ms // 60000
        s = (ms % 60000) / 1000
        return f"{m}:{s:06.3f}"

    @property
    def session_label(self) -> str:
        dt = datetime.strptime(self.date + self.time, "%y%m%d%H%M%S")
        return dt.strftime("%Y-%m-%d %H:%M") + f"  ({self.circuit} / {self.car} / {self.tyre})"


# ---------------------------------------------------------------------------
# ファイル解析 & セッショングルーピング
# ---------------------------------------------------------------------------
@st.cache_data
def load_all_meta(data_dir: Path) -> list[LapMeta]:
    """指定フォルダの CSV を読み込んで LapMeta リストを返す。
    data_dir を引数にすることで、パス変更時に @st.cache_data が自動再実行される。
    """
    metas: list[LapMeta] = []
    for f in sorted(data_dir.glob("*.csv")):
        m = _FNAME_RE.match(f.name)
        if not m:
            continue
        date, time_, source, circuit, car, tyre, condition, lap_no, lap_time = m.groups()
        metas.append(LapMeta(
            path=f,
            date=date,
            time=time_,
            session_id=f"{date}_{time_}",
            source=source,
            circuit=circuit,
            car=car,
            tyre=tyre,
            condition=condition,
            lap_no=int(lap_no),
            lap_time_str=lap_time,
        ))
    return metas


def group_sessions(metas: list[LapMeta]) -> dict[str, list[LapMeta]]:
    """連続したタイムスタンプのファイルを同一セッションとしてグループ化する。
    ファイル名の日付+時刻部分から 1 セッション=180 秒以内に開始したファイルをまとめる。
    """
    if not metas:
        return {}

    sessions: dict[str, list[LapMeta]] = {}
    current_key: str | None = None
    prev_dt: datetime | None = None

    for meta in metas:
        dt = datetime.strptime(meta.date + meta.time, "%y%m%d%H%M%S")
        if prev_dt is None or (dt - prev_dt).total_seconds() > 180:
            # 新しいセッション
            current_key = meta.session_label
            sessions[current_key] = []
        sessions[current_key].append(meta)  # type: ignore[index]
        prev_dt = dt

    return sessions


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# Tab 1 ヘルパー: インライン HTML サマリーカード
# ---------------------------------------------------------------------------
def build_summary_html(meta: LapMeta, df: pd.DataFrame, tr: dict) -> str:
    speed_max = df["speed_kmh"].max()
    speed_avg = df["speed_kmh"].mean()
    throttle_avg = df["throttle_pct"].mean()
    brake_avg = df["brake_pct"].mean()
    rpm_max = df["engine_rpm"].max()
    top_gear = int(df["gear"].max())
    tyre_avg_fl = df["tyre_temp_fl"].mean()
    tyre_avg_fr = df["tyre_temp_fr"].mean()
    tyre_avg_rl = df["tyre_temp_rl"].mean()
    tyre_avg_rr = df["tyre_temp_rr"].mean()

    # Gカウンター (旋回Gのmax絶対値)
    lat_g_max = df["lat_g"].abs().max()
    lon_g_max = df["lon_g"].abs().max()

    # スロットル/ブレーキゾーン幅をプログレスバー用に 0–100 でクリップ
    t_w = min(max(int(throttle_avg), 0), 100)
    b_w = min(max(int(brake_avg), 0), 100)

    tyre_color = lambda t: (
        "#4fc3f7" if t < 60 else
        "#81c784" if t < 90 else
        "#ffb74d" if t < 110 else
        "#e57373"
    )

    html = f"""<!DOCTYPE html>
<html lang="{tr['html_lang']}">
<head>
<meta charset="UTF-8">
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{
    font-family:'Segoe UI',system-ui,sans-serif;
    background:linear-gradient(135deg,#0d1117 0%,#161b22 100%);
    color:#e6edf3;
    padding:16px;
    min-height:100vh;
  }}
  .card{{
    background:rgba(255,255,255,.05);
    border:1px solid rgba(255,255,255,.1);
    border-radius:12px;
    padding:20px;
    margin-bottom:14px;
    backdrop-filter:blur(4px);
  }}
  .card-title{{
    font-size:.75rem;
    letter-spacing:.08em;
    text-transform:uppercase;
    color:#8b949e;
    margin-bottom:12px;
  }}
  .hero{{
    text-align:center;
    padding:28px 16px;
    background:linear-gradient(135deg,#1a1f3c 0%,#0d2144 100%);
    border:1px solid #30363d;
    border-radius:14px;
    margin-bottom:14px;
  }}
  .hero-time{{
    font-size:3.2rem;
    font-weight:700;
    letter-spacing:.02em;
    background:linear-gradient(90deg,#58a6ff,#79c0ff);
    -webkit-background-clip:text;
    -webkit-text-fill-color:transparent;
    background-clip:text;
  }}
  .hero-sub{{font-size:.9rem;color:#8b949e;margin-top:4px}}
  .stats-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
  .stat{{text-align:center;padding:12px 6px}}
  .stat-val{{font-size:1.6rem;font-weight:600;color:#79c0ff}}
  .stat-label{{font-size:.7rem;color:#8b949e;margin-top:3px}}
  .bar-row{{display:flex;align-items:center;gap:10px;margin-bottom:8px}}
  .bar-label{{width:80px;font-size:.8rem;color:#8b949e;text-align:right}}
  .bar-bg{{flex:1;height:10px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden}}
  .bar-fill-t{{height:100%;border-radius:99px;background:linear-gradient(90deg,#2ea44f,#56d364)}}
  .bar-fill-b{{height:100%;border-radius:99px;background:linear-gradient(90deg,#c5372c,#f85149)}}
  .bar-pct{{width:38px;font-size:.8rem;color:#e6edf3;text-align:right}}
  .tyre-grid{{
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:8px;
    max-width:240px;
    margin:0 auto;
  }}
  .tyre-cell{{
    padding:10px;
    border-radius:8px;
    text-align:center;
    font-weight:600;
    font-size:1.1rem;
  }}
  .tyre-lbl{{font-size:.65rem;font-weight:400;opacity:.7;display:block;margin-bottom:2px}}
</style>
</head>
<body>

<div class="hero">
  <div style="font-size:.8rem;color:#8b949e;margin-bottom:6px">
    {meta.circuit} &nbsp;·&nbsp; {meta.car} &nbsp;·&nbsp; {meta.tyre} / {meta.condition}
  </div>
  <div class="hero-time">{meta.lap_time_display}</div>
  <div class="hero-sub">LAP {meta.lap_no}</div>
</div>

<!-- スピード / RPM / G -->
<div class="card">
  <div class="card-title">{tr['card_perf_title']}</div>
  <div class="stats-grid">
    <div class="stat">
      <div class="stat-val">{speed_max:.0f}</div>
      <div class="stat-label">{tr['card_max_speed']}</div>
    </div>
    <div class="stat">
      <div class="stat-val">{speed_avg:.1f}</div>
      <div class="stat-label">{tr['card_avg_speed']}</div>
    </div>
    <div class="stat">
      <div class="stat-val">{rpm_max:.0f}</div>
      <div class="stat-label">{tr['card_max_rpm']}</div>
    </div>
    <div class="stat">
      <div class="stat-val">{top_gear}</div>
      <div class="stat-label">{tr['card_max_gear']}</div>
    </div>
    <div class="stat">
      <div class="stat-val">{lat_g_max:.2f}</div>
      <div class="stat-label">{tr['card_max_lat_g']}</div>
    </div>
    <div class="stat">
      <div class="stat-val">{lon_g_max:.2f}</div>
      <div class="stat-label">{tr['card_max_lon_g']}</div>
    </div>
  </div>
</div>

<!-- スロットル / ブレーキ -->
<div class="card">
  <div class="card-title">{tr['card_accel_brake']}</div>
  <div class="bar-row">
    <div class="bar-label">{tr['card_throttle']}</div>
    <div class="bar-bg"><div class="bar-fill-t" style="width:{t_w}%"></div></div>
    <div class="bar-pct">{throttle_avg:.1f}%</div>
  </div>
  <div class="bar-row">
    <div class="bar-label">{tr['card_brake']}</div>
    <div class="bar-bg"><div class="bar-fill-b" style="width:{b_w}%"></div></div>
    <div class="bar-pct">{brake_avg:.1f}%</div>
  </div>
</div>

<!-- タイヤ温度 -->
<div class="card">
  <div class="card-title">{tr['card_tire_temp']}</div>
  <div class="tyre-grid">
    <div class="tyre-cell" style="background:{tyre_color(tyre_avg_fl)}22;border:1px solid {tyre_color(tyre_avg_fl)}66">
      <span class="tyre-lbl">FL</span>{tyre_avg_fl:.1f}°
    </div>
    <div class="tyre-cell" style="background:{tyre_color(tyre_avg_fr)}22;border:1px solid {tyre_color(tyre_avg_fr)}66">
      <span class="tyre-lbl">FR</span>{tyre_avg_fr:.1f}°
    </div>
    <div class="tyre-cell" style="background:{tyre_color(tyre_avg_rl)}22;border:1px solid {tyre_color(tyre_avg_rl)}66">
      <span class="tyre-lbl">RL</span>{tyre_avg_rl:.1f}°
    </div>
    <div class="tyre-cell" style="background:{tyre_color(tyre_avg_rr)}22;border:1px solid {tyre_color(tyre_avg_rr)}66">
      <span class="tyre-lbl">RR</span>{tyre_avg_rr:.1f}°
    </div>
  </div>
</div>

</body>
</html>"""
    return html


# ---------------------------------------------------------------------------
# Tab 2 ヘルパー: Plotly テレメトリ HTML ファイル生成
# ---------------------------------------------------------------------------
def build_telemetry_html(meta: LapMeta, df: pd.DataFrame, out_path: Path) -> None:
    t = df.index / len(df) * meta.lap_time_ms / 1000  # 簡易時間軸 (秒)

    fig = make_subplots(
        rows=4, cols=1,
        shared_xaxes=True,
        subplot_titles=[
            "Speed (km/h)",
            "Throttle / Brake (%)",
            "Engine RPM & Gear",
            "Tyre Temperature (°C)",
        ],
        vertical_spacing=0.07,
        row_heights=[0.28, 0.22, 0.25, 0.25],
    )

    # --- Row 1: Speed ---
    fig.add_trace(go.Scatter(
        x=t, y=df["speed_kmh"],
        name="Speed", line=dict(color="#58a6ff", width=1.5),
        fill="tozeroy", fillcolor="rgba(88,166,255,0.08)",
    ), row=1, col=1)

    # --- Row 2: Throttle & Brake ---
    fig.add_trace(go.Scatter(
        x=t, y=df["throttle_pct"],
        name="Throttle", line=dict(color="#56d364", width=1.2),
        fill="tozeroy", fillcolor="rgba(86,211,100,0.12)",
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=t, y=df["brake_pct"],
        name="Brake", line=dict(color="#f85149", width=1.2),
        fill="tozeroy", fillcolor="rgba(248,81,73,0.12)",
    ), row=2, col=1)

    # --- Row 3: RPM + Gear (secondary y-axis) ---
    fig.add_trace(go.Scatter(
        x=t, y=df["engine_rpm"],
        name="RPM", line=dict(color="#d2a8ff", width=1.2),
    ), row=3, col=1)
    fig.add_trace(go.Scatter(
        x=t, y=df["gear"],
        name="Gear", line=dict(color="#ffa657", width=1.5, dash="dot"),
        yaxis="y5",
    ), row=3, col=1)

    # --- Row 4: Tyre Temps ---
    tyre_colors = {"fl": "#79c0ff", "fr": "#56d364", "rl": "#ffa657", "rr": "#f85149"}
    tyre_labels = {"fl": "FL", "fr": "FR", "rl": "RL", "rr": "RR"}
    for pos, color in tyre_colors.items():
        fig.add_trace(go.Scatter(
            x=t, y=df[f"tyre_temp_{pos}"],
            name=f"Tyre {tyre_labels[pos]}",
            line=dict(color=color, width=1.2),
        ), row=4, col=1)

    title_text = (
        f"Telemetry — {meta.circuit} &nbsp; {meta.car} &nbsp; "
        f"{meta.tyre}/{meta.condition} &nbsp; Lap {meta.lap_no} &nbsp; {meta.lap_time_display}"
    )
    fig.update_layout(
        title=dict(text=title_text, font=dict(size=16, color="#e6edf3")),
        paper_bgcolor="#0d1117",
        plot_bgcolor="#161b22",
        font=dict(color="#8b949e", size=11),
        legend=dict(
            orientation="h",
            y=-0.04,
            bgcolor="rgba(0,0,0,0)",
            font=dict(color="#c9d1d9"),
        ),
        margin=dict(l=60, r=20, t=70, b=60),
        height=850,
        yaxis5=dict(
            title="Gear",
            overlaying="y3",
            side="right",
            range=[0, 9],
            tickvals=list(range(1, 9)),
            showgrid=False,
        ),
        # 全サブプロット軸スタイル (xaxis4 だけ title を追加)
        **{
            f"xaxis{i if i > 1 else ''}": dict(
                gridcolor="#21262d",
                zerolinecolor="#30363d",
                **({"title": "Time (s)"} if i == 4 else {}),
            )
            for i in range(1, 5)
        },
        **{
            f"yaxis{i if i > 1 else ''}": dict(gridcolor="#21262d", zerolinecolor="#30363d")
            for i in [1, 2, 3, 4]
        },
    )

    fig.write_html(
        str(out_path),
        config={"displayModeBar": False},
        include_plotlyjs="cdn",
        full_html=True,
    )


# ---------------------------------------------------------------------------
# Streamlit アプリ本体
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Racing Simulator Telemetry Analysis",
    page_icon="🏎",
    layout="wide",
)

# ---------------------------------------------------------------------------
# 言語選択: サイドバー最上部
# 選択された言語コードで locales/{lang}.json を読み込み、以降の UI 文字列は
# すべて tr["キー"] 経由で参照する
# ---------------------------------------------------------------------------
_lang_options = ["日本語", "English"]
_lang_codes = {"日本語": "ja", "English": "en"}
_lang_display = st.sidebar.selectbox(
    "🌐 言語 / Language",
    _lang_options,
    key="lang_selector",
)
_lang_code = _lang_codes[_lang_display]
tr = load_translations(_lang_code)
st.sidebar.divider()

st.title(tr["app_title"])
st.caption(tr["app_caption"])

# ---------------------------------------------------------------------------
# バージョン選択: サイドバー最上部
# ---------------------------------------------------------------------------
_available_versions = scan_versions()
_default_idx = _available_versions.index(_THIS_VERSION) if _THIS_VERSION in _available_versions else 0
_selected_version: str = st.sidebar.selectbox(
    tr["sidebar_version_label"],
    _available_versions,
    index=_default_idx,
    key="version_selector",
    help=tr["sidebar_version_help"],
)
st.sidebar.divider()

# 別バージョンが選択された場合はそちらの app.py の show() を呼び出して終了
if _selected_version != _THIS_VERSION:
    _target_app = Path(__file__).parent.parent / _selected_version / "app.py"
    _spec = importlib.util.spec_from_file_location(
        f"app_{_selected_version.replace('.', '_')}", _target_app
    )
    if _spec is None or _spec.loader is None:
        st.error(tr["error_load_app"].format(version=_selected_version))
        st.stop()
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _mod
    _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
    if not hasattr(_mod, "show"):
        st.error(tr["error_no_show_fn"].format(version=_selected_version))
        st.stop()
    _mod.show()
    st.stop()

# ---------------------------------------------------------------------------
# サイドバー: 共通選択UI
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header(tr["sidebar_data_header"])

    # --- データフォルダ選択 ---
    data_dir_input = st.text_input(
        tr["sidebar_data_folder_label"],
        value=str(_DEFAULT_DATA_DIR),
        help=tr["sidebar_data_folder_help"],
        key="data_dir",
    )
    data_dir = Path(data_dir_input)
    if not data_dir.is_dir():
        st.error(tr["sidebar_folder_not_found"].format(data_dir=data_dir))
        st.stop()

    # ---------------------------------------------------------------------------
    # データ読み込み・セッショングルーピング
    # ---------------------------------------------------------------------------
    all_metas = load_all_meta(data_dir)
    sessions = group_sessions(all_metas)
    session_keys = list(sessions.keys())

    selected_session = st.selectbox(tr["sidebar_session_label"], session_keys, key="session")
    # セッション状態に古いキーが残存している場合、sessions に存在しない値が
    # selectbox から返ることがある (KeyError の原因)。先頭キーへフォールバック。
    if selected_session not in sessions:
        selected_session = session_keys[0] if session_keys else None
    if selected_session is None:
        st.error(tr["sidebar_no_session"])
        st.stop()
    laps = sessions[selected_session]
    lap_labels = [f"Lap {m.lap_no}  ({m.lap_time_display})" for m in laps]
    selected_lap_idx = st.selectbox(
        tr["sidebar_lap_label"], range(len(laps)), format_func=lambda i: lap_labels[i], key="lap"
    )
    selected_meta = laps[selected_lap_idx]

    st.divider()
    _date_display = (
        selected_meta.date[:2]
        + "/"
        + "".join(["0" + selected_meta.date[2:4], "0" + selected_meta.date[4:6]])
    )
    st.markdown(
        tr["sidebar_session_detail"].format(
            circuit=selected_meta.circuit,
            car=selected_meta.car,
            tyre=selected_meta.tyre,
            condition=selected_meta.condition,
            date=_date_display,
            lap_count=len(laps),
        )
    )

    # -----------------------------------------------------------------------
    # アクセスカウンター（セッション先頭で 1 回 Supabase に記録）
    # -----------------------------------------------------------------------
    st.divider()
    if "_visited" not in st.session_state:
        st.session_state["_visited"] = True
        # secrets.toml が存在しないローカル環境では StreamlitSecretNotFoundError が
        # 発生するため try/except でガードし、クラウド外とみなす
        try:
            _is_cloud = st.secrets.get("ENVIRONMENT") == "cloud"
        except Exception:
            _is_cloud = False
        if _is_cloud:
            _increment_counter(_THIS_VERSION)
    counts = _load_counts()
    if counts:
        st.caption(tr["sidebar_access_count"])
        for ver, cnt in sorted(counts.items()):
            st.metric(label=ver, value=cnt)
    else:
        st.caption(tr["sidebar_access_count"])
        st.caption(tr["sidebar_access_count_pending"])

df_selected = load_csv(selected_meta.path)

# ---------------------------------------------------------------------------
# タブ
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    tr["tab1_label"],
    tr["tab2_label"],
    tr["tab3_label"],
    tr["tab4_label"],
])

# =====================================================
# Tab 1: HTML 文字列を st.iframe に渡す
# =====================================================
with tab1:
    col_main, col_api = st.columns([3, 2], gap="large")

    with col_api:
        st.subheader(tr["tab1_subheader_api"])
        st.markdown(tr["tab1_api_desc"])

        st.markdown("---")
        st.subheader(tr["tab1_subheader_height"])
        _height_opts = tr["tab1_height_options"]
        height_mode = st.radio(
            "height",
            options=_height_opts,
            index=0,
            key="tab1_height",
        )
        if height_mode == tr["tab1_height_fixed"]:
            height_val: int | str = st.slider(tr["tab1_height_slider"], 200, 1000, 600, step=50, key="tab1_px")
        elif height_mode == tr["tab1_height_stretch"]:
            height_val = "stretch"
        else:
            height_val = "content"

    with col_main:
        st.subheader(tr["tab1_summary_subheader"].format(lap_no=selected_meta.lap_no))
        html_str = build_summary_html(selected_meta, df_selected, tr)
        st.iframe(html_str, height=height_val)

# =====================================================
# Tab 2: ローカル HTML ファイルを Path で st.iframe に渡す
# =====================================================
with tab2:
    st.subheader(tr["tab2_subheader_report"])

    col_chart, col_api2 = st.columns([5, 2], gap="large")

    with col_api2:
        st.subheader(tr["tab2_subheader_api"])
        st.markdown(tr["tab2_api_desc"])

        st.markdown("---")
        h_val = st.slider(tr["tab2_height_slider"], 400, 1200, 870, step=50, key="tab2_height")

    with col_chart:
        out_html = REPORTS_DIR / "telemetry.html"
        with st.spinner(tr["tab2_spinner"]):
            build_telemetry_html(selected_meta, df_selected, out_html)

        st.caption(
            tr["tab2_caption"].format(
                out_html=out_html,
                lap_no=selected_meta.lap_no,
                circuit=selected_meta.circuit,
                car=selected_meta.car,
            )
        )
        st.iframe(out_html, height=h_val)

# =====================================================
# Tab 3: 外部 URL を st.iframe に渡す
# =====================================================

# 富士スピードウェイ周辺の OpenStreetMap embed URL
_FUJI_MAP_URL = (
    "https://www.openstreetmap.org/export/embed.html"
    "?bbox=138.9066%2C35.3659%2C138.9468%2C35.3835"
    "&layer=mapnik"
    "&marker=35.3748%2C138.9267"
)

with tab3:
    st.subheader(tr["tab3_subheader"])
    st.markdown(tr["tab3_desc"])

    col_left, col_right = st.columns([3, 1], gap="large")
    with col_right:
        ext_height = st.slider(tr["tab3_height_slider"], 300, 1000, 600, step=50, key="tab3_height")
        map_layer = st.selectbox(
            tr["tab3_map_layer_label"],
            options=[tuple(opt) for opt in tr["tab3_map_options"]],
            format_func=lambda x: x[0],
            key="tab3_layer",
        )
        layer_param = map_layer[1]
        map_url = (
            "https://www.openstreetmap.org/export/embed.html"
            "?bbox=138.9066%2C35.3659%2C138.9468%2C35.3835"
            f"&layer={layer_param}"
            "&marker=35.3748%2C138.9267"
        )
        st.markdown(
            tr["tab3_osm_link"],
            unsafe_allow_html=False,
        )

    with col_left:
        st.iframe(map_url, height=ext_height)

# =====================================================
# Tab 4: st.menu_button デモ (ツールバー構築)
# =====================================================
with tab4:
    st.subheader(tr["tab4_subheader_toolbar"])

    col_main4, col_api4 = st.columns([3, 2], gap="large")

    with col_api4:
        st.subheader(tr["tab4_subheader_api"])
        st.markdown(tr["tab4_api_desc"])

    with col_main4:
        # --- セッション状態初期化 ---
        if "mb_chart" not in st.session_state:
            st.session_state.mb_chart = "speed"
        if "mb_stat" not in st.session_state:
            st.session_state.mb_stat = "max"

        # ---- ツールバー行 ----
        st.markdown(tr["tab4_toolbar_header"])
        tb1, tb2, tb3, tb4_col, tb_space = st.columns([1.3, 1.5, 1.3, 1.0, 3.0])

        with tb1:
            export_action = st.menu_button(
                tr["tab4_export"],
                options=tr["tab4_export_options"],
                type="primary",
                icon=":material/download:",
                help=tr["tab4_export_help"],
                key="mb_export",
            )

        with tb2:
            _chart_opts_map = tr["tab4_chart_options"]
            chart_action = st.menu_button(
                tr["tab4_chart_switch"],
                options=list(_chart_opts_map.keys()),
                format_func=lambda x: _chart_opts_map[x],
                icon=":material/bar_chart:",
                help=tr["tab4_chart_help"],
                key="mb_chart_btn",
            )

        with tb3:
            _stat_opts_map = tr["tab4_stat_options"]
            stat_action = st.menu_button(
                tr["tab4_stat_line"],
                options=list(_stat_opts_map.keys()),
                format_func=lambda x: _stat_opts_map[x],
                icon=":material/analytics:",
                help=tr["tab4_stat_help"],
                key="mb_stat_btn",
            )

        with tb4_col:
            st.menu_button(
                tr["tab4_detail"],
                options=tr["tab4_detail_options"],
                icon=":material/more_horiz:",
                type="tertiary",
                disabled=True,
                help=tr["tab4_detail_help"],
                key="mb_more",
            )

        # ---- アクション処理 ----
        if chart_action:
            st.session_state.mb_chart = chart_action
        if stat_action:
            st.session_state.mb_stat = stat_action

        _export_opts = tr["tab4_export_options"]
        if export_action == _export_opts[0]:
            csv_bytes = df_selected.to_csv(index=False).encode("utf-8")
            st.download_button(
                tr["tab4_download_csv"],
                data=csv_bytes,
                file_name=f"telemetry_{selected_meta.circuit}_lap{selected_meta.lap_no}.csv",
                mime="text/csv",
                key="dl_csv4",
            )
        elif export_action == _export_opts[1]:
            json_bytes = df_selected.to_json(
                orient="records", force_ascii=False
            ).encode("utf-8")
            st.download_button(
                tr["tab4_download_json"],
                data=json_bytes,
                file_name=f"telemetry_{selected_meta.circuit}_lap{selected_meta.lap_no}.json",
                mime="application/json",
                key="dl_json4",
            )
        elif export_action == _export_opts[2]:
            out_html4 = REPORTS_DIR / "telemetry_menu.html"
            with st.spinner(tr["tab4_spinner_html"]):
                build_telemetry_html(selected_meta, df_selected, out_html4)
            st.success(tr["tab4_success_html"].format(out_html=out_html4))

        st.divider()

        # ---- チャート表示 ----
        _chart_titles_map = tr["tab4_chart_titles"]
        _chart_meta: dict[str, tuple[str, list[str], list[str]]] = {
            "speed": (
                _chart_titles_map["speed"],
                ["speed_kmh"],
                ["#58a6ff"],
            ),
            "throttle_brake": (
                _chart_titles_map["throttle_brake"],
                ["throttle_pct", "brake_pct"],
                ["#56d364", "#f85149"],
            ),
            "rpm_gear": (
                _chart_titles_map["rpm_gear"],
                ["engine_rpm"],
                ["#d2a8ff"],
            ),
            "tyre_temp": (
                _chart_titles_map["tyre_temp"],
                ["tyre_temp_fl", "tyre_temp_fr", "tyre_temp_rl", "tyre_temp_rr"],
                ["#79c0ff", "#56d364", "#ffa657", "#f85149"],
            ),
        }
        _stat_labels = tr["tab4_stat_options"]

        cur_chart = st.session_state.mb_chart
        cur_stat = st.session_state.mb_stat
        chart_title4, chart_cols4, chart_colors4 = _chart_meta[cur_chart]

        st.caption(
            tr["tab4_chart_caption"].format(
                chart_title=chart_title4, stat_label=_stat_labels[cur_stat]
            )
        )

        t_axis = (
            df_selected.index / len(df_selected) * selected_meta.lap_time_ms / 1000
        )
        fig4 = go.Figure()

        for col_name, color in zip(chart_cols4, chart_colors4):
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            fig4.add_trace(
                go.Scatter(
                    x=t_axis,
                    y=df_selected[col_name],
                    name=col_name,
                    line=dict(color=color, width=1.5),
                    fill="tozeroy",
                    fillcolor=f"rgba({r},{g},{b},0.10)",
                )
            )
            if cur_stat == "max":
                stat_val = float(df_selected[col_name].max())
            elif cur_stat == "mean":
                stat_val = float(df_selected[col_name].mean())
            else:
                stat_val = float(df_selected[col_name].min())

            fig4.add_hline(
                y=stat_val,
                line_dash="dash",
                line_color=color,
                opacity=0.6,
                annotation_text=tr["tab4_stat_annotation"].format(
                    stat_label=_stat_labels[cur_stat], stat_val=f"{stat_val:.1f}"
                ),
                annotation_position="top right",
                annotation_font_color=color,
            )

        fig4.update_layout(
            paper_bgcolor="#0d1117",
            plot_bgcolor="#161b22",
            font=dict(color="#8b949e"),
            xaxis=dict(
                title="Time (s)", gridcolor="#21262d", zerolinecolor="#30363d"
            ),
            yaxis=dict(
                title=chart_title4, gridcolor="#21262d", zerolinecolor="#30363d"
            ),
            height=420,
            margin=dict(l=60, r=20, t=20, b=60),
            legend=dict(
                orientation="h",
                y=-0.18,
                bgcolor="rgba(0,0,0,0)",
                font=dict(color="#c9d1d9"),
            ),
        )
        st.plotly_chart(fig4, use_container_width=True)

        # ---- type パラメータ比較デモ ----
        st.divider()
        st.markdown(tr["tab4_type_comparison"])
        tc1, tc2, tc3 = st.columns(3)
        for col_t, type_val in zip([tc1, tc2, tc3], ["primary", "secondary", "tertiary"]):
            with col_t:
                res = st.menu_button(
                    type_val,
                    options=tr["tab4_item_options"],
                    type=type_val,  # type: ignore[arg-type]
                    width="stretch",
                    key=f"type_demo_{type_val}",
                )
                if res:
                    st.caption(tr["tab4_selection_caption"].format(res=res))
