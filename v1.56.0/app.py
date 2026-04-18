"""
GT7 Race Telemetry Analyzer
Streamlit v1.56.0 – st.iframe デモアプリ

st.iframe の 3 つの使い方を実演します:
  Tab 1: HTML 文字列 (インライン HTML でラップサマリーカード)
  Tab 2: ローカル HTML ファイル (Plotly テレメトリレポートを Path で渡す)
  Tab 3: 外部 URL (st.iframe の公式ドキュメントを埋め込み)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
# デフォルト: リポジトリルート直下の共通サンプルデータフォルダ
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
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
def build_summary_html(meta: LapMeta, df: pd.DataFrame) -> str:
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
<html lang="ja">
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
  <div class="card-title">パフォーマンス指標</div>
  <div class="stats-grid">
    <div class="stat">
      <div class="stat-val">{speed_max:.0f}</div>
      <div class="stat-label">最高速度 (km/h)</div>
    </div>
    <div class="stat">
      <div class="stat-val">{speed_avg:.1f}</div>
      <div class="stat-label">平均速度 (km/h)</div>
    </div>
    <div class="stat">
      <div class="stat-val">{rpm_max:.0f}</div>
      <div class="stat-label">最高 RPM</div>
    </div>
    <div class="stat">
      <div class="stat-val">{top_gear}</div>
      <div class="stat-label">使用最高ギア</div>
    </div>
    <div class="stat">
      <div class="stat-val">{lat_g_max:.2f}</div>
      <div class="stat-label">最大横 G</div>
    </div>
    <div class="stat">
      <div class="stat-val">{lon_g_max:.2f}</div>
      <div class="stat-label">最大縦 G</div>
    </div>
  </div>
</div>

<!-- スロットル / ブレーキ -->
<div class="card">
  <div class="card-title">アクセル / ブレーキ 使用率 (平均)</div>
  <div class="bar-row">
    <div class="bar-label">スロットル</div>
    <div class="bar-bg"><div class="bar-fill-t" style="width:{t_w}%"></div></div>
    <div class="bar-pct">{throttle_avg:.1f}%</div>
  </div>
  <div class="bar-row">
    <div class="bar-label">ブレーキ</div>
    <div class="bar-bg"><div class="bar-fill-b" style="width:{b_w}%"></div></div>
    <div class="bar-pct">{brake_avg:.1f}%</div>
  </div>
</div>

<!-- タイヤ温度 -->
<div class="card">
  <div class="card-title">タイヤ温度 平均 (°C)</div>
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
    page_title="GT7 テレメトリ解析 │ st.iframe デモ",
    page_icon="🏎",
    layout="wide",
)

st.title("🏎  GT7 レースシミュレーター テレメトリ解析")
st.caption(
    "**Streamlit v1.56.0** 新機能 `st.iframe` のデモアプリ — "
    "富士スピードウェイ / GR Supra / RM タイヤ / ドライ条件"
)

# ---------------------------------------------------------------------------
# サイドバー: 共通選択UI
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("データ選択")

    # --- データフォルダ選択 ---
    data_dir_input = st.text_input(
        "データフォルダ",
        value=str(_DEFAULT_DATA_DIR),
        help="CSV ファイルが格納されたフォルダのパスを入力してください。",
        key="data_dir",
    )
    data_dir = Path(data_dir_input)
    if not data_dir.is_dir():
        st.error(f"フォルダが見つかりません:\n`{data_dir}`")
        st.stop()

    # ---------------------------------------------------------------------------
    # データ読み込み・セッショングルーピング
    # ---------------------------------------------------------------------------
    all_metas = load_all_meta(data_dir)
    sessions = group_sessions(all_metas)
    session_keys = list(sessions.keys())

    selected_session = st.selectbox("セッション", session_keys, key="session")
    # セッション状態に古いキーが残存している場合、sessions に存在しない値が
    # selectbox から返ることがある (KeyError の原因)。先頭キーへフォールバック。
    if selected_session not in sessions:
        selected_session = session_keys[0] if session_keys else None
    if selected_session is None:
        st.error("利用可能なセッションデータがありません。")
        st.stop()
    laps = sessions[selected_session]
    lap_labels = [f"Lap {m.lap_no}  ({m.lap_time_display})" for m in laps]
    selected_lap_idx = st.selectbox(
        "ラップ", range(len(laps)), format_func=lambda i: lap_labels[i], key="lap"
    )
    selected_meta = laps[selected_lap_idx]

    st.divider()
    st.markdown(
        f"""
**セッション詳細**
- サーキット: `{selected_meta.circuit}`
- 車両: `{selected_meta.car}`
- タイヤ: `{selected_meta.tyre}` / `{selected_meta.condition}`
- 日時: `{selected_meta.date[:2]}/{''.join(['0'+selected_meta.date[2:4],'0'+selected_meta.date[4:6]])}`
- ラップ数: `{len(laps)}`
"""
    )

df_selected = load_csv(selected_meta.path)

# ---------------------------------------------------------------------------
# タブ
# ---------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Tab 1 — HTML 文字列",
    "📈 Tab 2 — ローカル HTML ファイル",
    "🗺 Tab 3 — 外部 URL (地図)",
    "🛠 Tab 4 — st.menu_button",
])

# =====================================================
# Tab 1: HTML 文字列を st.iframe に渡す
# =====================================================
with tab1:
    col_main, col_api = st.columns([3, 2], gap="large")

    with col_api:
        st.subheader("st.iframe API ポイント")
        st.markdown("""
`st.iframe` に **HTML 文字列** を直接渡すと、
その場でインライン HTML としてレンダリングされます。

```python
st.iframe(
    html_string,     # str — HTML文字列をそのまま渡す
    height="content" # 'content' でコンテンツ高さに自動調整
)
```

| パラメータ | 選択肢 |
|---|---|
| `height` | `"content"` / `"stretch"` / `int(px)` |
| `width` | `"stretch"` / `"content"` / `int(px)` |
| `tab_index` | `None` / `-1` / `int` |

> `height="content"` を指定すると、  
> Streamlit 側で HTML の実際の高さを計測して iframe を自動リサイズします。
""")

        st.markdown("---")
        st.subheader("height パラメータ を試す")
        height_mode = st.radio(
            "height",
            options=["content (自動)", "stretch (縦伸長)", "固定値 (px)"],
            index=0,
            key="tab1_height",
        )
        if height_mode == "固定値 (px)":
            height_val: int | str = st.slider("高さ (px)", 200, 1000, 600, step=50, key="tab1_px")
        elif height_mode == "stretch (縦伸長)":
            height_val = "stretch"
        else:
            height_val = "content"

    with col_main:
        st.subheader(f"ラップ {selected_meta.lap_no} サマリーカード")
        html_str = build_summary_html(selected_meta, df_selected)
        st.iframe(html_str, height=height_val)

# =====================================================
# Tab 2: ローカル HTML ファイルを Path で st.iframe に渡す
# =====================================================
with tab2:
    st.subheader("Plotly テレメトリレポート")

    col_chart, col_api2 = st.columns([5, 2], gap="large")

    with col_api2:
        st.subheader("st.iframe API ポイント")
        st.markdown("""
`st.iframe` に **`Path` オブジェクト** を渡すと、
Streamlit がファイルを読み込んで自動で埋め込みます。

```python
from pathlib import Path
st.iframe(
    Path("reports/telemetry.html"),
    height=800,
)
```

- `.html` / `.htm` ファイルはコンテンツをそのまま埋め込み
- PDF / 画像 / SVG などは Streamlit のメディアストレージ経由でブラウザが直接表示
- ファイルはアプリ実行時に都度差し替え可能（ここではラップ選択変更で再生成）
""")

        st.markdown("---")
        h_val = st.slider("iframe 高さ (px)", 400, 1200, 870, step=50, key="tab2_height")

    with col_chart:
        out_html = REPORTS_DIR / "telemetry.html"
        with st.spinner("テレメトリレポートを生成中..."):
            build_telemetry_html(selected_meta, df_selected, out_html)

        st.caption(
            f"生成ファイル: `{out_html}` — "
            f"ラップ {selected_meta.lap_no} / {selected_meta.circuit} / {selected_meta.car}"
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
    st.subheader("富士スピードウェイ — OpenStreetMap を埋め込み表示")
    st.markdown("""
`st.iframe` に **絶対 URL** を渡すと、そのウェブページを iframe 内に表示します。  
ここでは、iframe 埋め込みが許可されている **OpenStreetMap** で富士スピードウェイの地図を表示します。

```python
st.iframe(
    "https://www.openstreetmap.org/export/embed.html"
    "?bbox=138.9066%2C35.3659%2C138.9468%2C35.3835"
    "&layer=mapnik&marker=35.3748%2C138.9267",
    height=600,
)
```

> **ポイント**: 外部 URL の場合、クロスオリジン制限により  
> `height="content"` は機能せず 400px にフォールバックします。  
> 高さは整数 `(px)` または `"stretch"` で指定してください。  
>
> ※ `docs.streamlit.io` などは `X-Frame-Options` で埋め込みをブロックしています。  
> 埋め込みには iframe 許可済みのサービスを選択してください。
""")

    col_left, col_right = st.columns([3, 1], gap="large")
    with col_right:
        ext_height = st.slider("iframe 高さ (px)", 300, 1000, 600, step=50, key="tab3_height")
        map_layer = st.selectbox(
            "地図レイヤー",
            options=[
                ("標準 (mapnik)", "mapnik"),
                ("サイクル (cycle)", "cycle"),
                ("交通 (transport)", "transport"),
            ],
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
            "[🗺 OpenStreetMap で開く]"
            "(https://www.openstreetmap.org/?mlat=35.3748&mlon=138.9267#map=14/35.3748/138.9267)",
            unsafe_allow_html=False,
        )

    with col_left:
        st.iframe(map_url, height=ext_height)

# =====================================================
# Tab 4: st.menu_button デモ (ツールバー構築)
# =====================================================
with tab4:
    st.subheader("🛠 ツールバー構築 — st.menu_button デモ")

    col_main4, col_api4 = st.columns([3, 2], gap="large")

    with col_api4:
        st.subheader("st.menu_button API ポイント")
        st.markdown(
            """
`st.menu_button` は **クリックでドロップダウンを展開** するボタンウィジェット。  
`st.button` と同様に、選択されたオプションを返し次のリランで `None` にリセットされます。

```python
action = st.menu_button(
    label="エクスポート",
    options=["CSV", "JSON", "HTML"],
    type="primary",               # "primary" / "secondary" / "tertiary"
    icon=":material/download:",   # Material アイコン or 絵文字
    width="content",              # "content" / "stretch" / int(px)
    format_func=lambda x: x,     # 表示名変換
    disabled=False,
    help="ツールチップ",
)
if action == "CSV":
    ...  # 選択時の処理
```

| パラメータ | 説明 |
|---|---|
| `type` | ボタンスタイル (primary/secondary/tertiary) |
| `icon` | Material アイコン or 絵文字 |
| `width` | ボタン幅の制御 |
| `format_func` | オプション表示名の変換 |
| `disabled` | ボタンを無効化 |
| `on_click` | 選択時コールバック |

> `st.selectbox` と異なり、ボタンラベルは変わらず  
> 返り値は次のリランで `None` に戻ります。
"""
        )

    with col_main4:
        # --- セッション状態初期化 ---
        if "mb_chart" not in st.session_state:
            st.session_state.mb_chart = "speed"
        if "mb_stat" not in st.session_state:
            st.session_state.mb_stat = "max"

        # ---- ツールバー行 ----
        st.markdown("#### ツールバー")
        tb1, tb2, tb3, tb4_col, tb_space = st.columns([1.3, 1.5, 1.3, 1.0, 3.0])

        with tb1:
            export_action = st.menu_button(
                "エクスポート",
                options=["CSV 形式", "JSON 形式", "HTML レポート"],
                type="primary",
                icon=":material/download:",
                help="テレメトリデータをエクスポート",
                key="mb_export",
            )

        with tb2:
            chart_action = st.menu_button(
                "チャート切替",
                options=["speed", "throttle_brake", "rpm_gear", "tyre_temp"],
                format_func=lambda x: {
                    "speed": "📈 スピード",
                    "throttle_brake": "🎮 スロットル/ブレーキ",
                    "rpm_gear": "⚙ RPM & ギア",
                    "tyre_temp": "🌡 タイヤ温度",
                }[x],
                icon=":material/bar_chart:",
                help="表示するチャートを変更",
                key="mb_chart_btn",
            )

        with tb3:
            stat_action = st.menu_button(
                "統計ライン",
                options=["max", "mean", "min"],
                format_func=lambda x: {
                    "max": "最大値",
                    "mean": "平均値",
                    "min": "最小値",
                }[x],
                icon=":material/analytics:",
                help="統計ラインの種類を変更",
                key="mb_stat_btn",
            )

        with tb4_col:
            st.menu_button(
                "詳細",
                options=["比較モード", "オーバーレイ", "ラップ差分"],
                icon=":material/more_horiz:",
                type="tertiary",
                disabled=True,
                help="近日公開予定",
                key="mb_more",
            )

        # ---- アクション処理 ----
        if chart_action:
            st.session_state.mb_chart = chart_action
        if stat_action:
            st.session_state.mb_stat = stat_action

        if export_action == "CSV 形式":
            csv_bytes = df_selected.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇ CSV をダウンロード",
                data=csv_bytes,
                file_name=f"telemetry_{selected_meta.circuit}_lap{selected_meta.lap_no}.csv",
                mime="text/csv",
                key="dl_csv4",
            )
        elif export_action == "JSON 形式":
            json_bytes = df_selected.to_json(
                orient="records", force_ascii=False
            ).encode("utf-8")
            st.download_button(
                "⬇ JSON をダウンロード",
                data=json_bytes,
                file_name=f"telemetry_{selected_meta.circuit}_lap{selected_meta.lap_no}.json",
                mime="application/json",
                key="dl_json4",
            )
        elif export_action == "HTML レポート":
            out_html4 = REPORTS_DIR / "telemetry_menu.html"
            with st.spinner("HTML レポートを生成中..."):
                build_telemetry_html(selected_meta, df_selected, out_html4)
            st.success(f"HTML レポートを生成しました: `{out_html4}`")

        st.divider()

        # ---- チャート表示 ----
        _chart_meta: dict[str, tuple[str, list[str], list[str]]] = {
            "speed": (
                "スピード (km/h)",
                ["speed_kmh"],
                ["#58a6ff"],
            ),
            "throttle_brake": (
                "スロットル / ブレーキ (%)",
                ["throttle_pct", "brake_pct"],
                ["#56d364", "#f85149"],
            ),
            "rpm_gear": (
                "RPM",
                ["engine_rpm"],
                ["#d2a8ff"],
            ),
            "tyre_temp": (
                "タイヤ温度 (°C)",
                ["tyre_temp_fl", "tyre_temp_fr", "tyre_temp_rl", "tyre_temp_rr"],
                ["#79c0ff", "#56d364", "#ffa657", "#f85149"],
            ),
        }
        _stat_labels = {"max": "最大値", "mean": "平均値", "min": "最小値"}

        cur_chart = st.session_state.mb_chart
        cur_stat = st.session_state.mb_stat
        chart_title4, chart_cols4, chart_colors4 = _chart_meta[cur_chart]

        st.caption(
            f"表示中: **{chart_title4}**  |  統計ライン: **{_stat_labels[cur_stat]}**"
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
                annotation_text=f"{_stat_labels[cur_stat]}: {stat_val:.1f}",
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
        st.markdown("#### `type` パラメータ比較")
        tc1, tc2, tc3 = st.columns(3)
        for col_t, type_val in zip([tc1, tc2, tc3], ["primary", "secondary", "tertiary"]):
            with col_t:
                res = st.menu_button(
                    type_val,
                    options=["項目 A", "項目 B", "項目 C"],
                    type=type_val,  # type: ignore[arg-type]
                    width="stretch",
                    key=f"type_demo_{type_val}",
                )
                if res:
                    st.caption(f"選択: **{res}**")
