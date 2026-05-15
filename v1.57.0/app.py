"""
GT7 Race Telemetry Analyzer
Streamlit v1.57.0 – Alert title= / :shimmer[] / st.bottom デモアプリ

【バージョン選択機能】
サイドバー最上部の「🔖 Streamlit バージョン」セレクターで確認したいバージョンを
切り替えられます。ワークスペースルート配下の v*.*.* フォルダを自動検出し、
対象バージョンの app.py に定義された show() 関数を動的にロードして呼び出します。
将来バージョンのデモを追加する際は v*/app.py に show() 関数を定義してください。

【このバージョンで実演する機能 (v1.57.0)】
Alert title= パラメータ:
  Tab 1: st.info / st.warning / st.error / st.success に title= 引数追加
         タイトル付きアラートで GT7 レーシング警告の表現力が向上

:shimmer[] マークダウンディレクティブ:
  Tab 2: :shimmer[テキスト] でアニメーション付きローディング表示
         テレメトリ読み込み中の UX を改善

st.bottom コンテナ:
  Tab 3: ビューポート底部に固定コンテンツを表示
         常時表示のラップ HUD「テレメトリステータスバー」として活用
"""

from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
_THIS_VERSION = "v1.57.0"

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


_BOT_UA_RE = re.compile(
    r"\b(bot|spider|crawler)\b"
    r"|uptimerobot|pingdom|statuscake|better\s*uptime|freshping"
    r"|hetrixtools|hyperping|cronitor|monitor|check|health",
    re.IGNORECASE,
)
_BOT_HOURLY_THRESHOLD = 8


def _increment_counter(version: str) -> None:
    """access_logs テーブルに 1 行 INSERT する。失敗時はサイレントに無視。"""
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
# 翻訳ヘルパー
# locales/ja.json / locales/en.json を読み込んで UI 文字列辞書を返す
# ---------------------------------------------------------------------------
def load_translations(lang: str) -> dict:
    """言語コードに対応する翻訳 JSON を読み込んで返す。"""
    locale_path = Path(__file__).parent / "locales" / f"{lang}.json"
    with locale_path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# レポート出力先
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
    date: str
    time: str
    session_id: str
    source: str
    circuit: str
    car: str
    tyre: str
    condition: str
    lap_no: int
    lap_time_str: str

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
    """指定フォルダの CSV を読み込んで LapMeta リストを返す。"""
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
    """連続したタイムスタンプのファイルを同一セッションとしてグループ化する。"""
    if not metas:
        return {}

    sessions: dict[str, list[LapMeta]] = {}
    current_key: str | None = None
    prev_dt: datetime | None = None

    for meta in metas:
        dt = datetime.strptime(meta.date + meta.time, "%y%m%d%H%M%S")
        if prev_dt is None or (dt - prev_dt).total_seconds() > 180:
            current_key = meta.session_label
            sessions[current_key] = []
        sessions[current_key].append(meta)  # type: ignore[index]
        prev_dt = dt

    return sessions


@st.cache_data
def load_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


# ---------------------------------------------------------------------------
# show(): バージョン v1.57.0 のコンテンツを描画する
# root app.py から importlib 経由で呼び出される。
# ---------------------------------------------------------------------------
def show() -> None:
    # 言語設定を root app.py の lang_selector (session_state) から読み取る
    _lang_codes = {"日本語": "ja", "English": "en"}
    _lang_display = st.session_state.get("lang_selector", "日本語")
    if _lang_display not in _lang_codes:
        _lang_display = "日本語"
    tr = load_translations(_lang_codes[_lang_display])

    st.title(tr["app_title"])
    st.caption(tr["app_caption"])

    # ---------------------------------------------------------------------------
    # サイドバー: 共通選択UI
    # ---------------------------------------------------------------------------
    with st.sidebar:
        st.header(tr["sidebar_data_header"])

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

        all_metas = load_all_meta(data_dir)
        sessions = group_sessions(all_metas)
        session_keys = list(sessions.keys())

        selected_session = st.selectbox(
            tr["sidebar_session_label"], session_keys, key="session", filter_mode="fuzzy"
        )
        if selected_session not in sessions:
            selected_session = session_keys[0] if session_keys else None
        if selected_session is None:
            st.error(tr["sidebar_no_session"])
            st.stop()
        laps = sessions[selected_session]
        lap_labels = [f"Lap {m.lap_no}  ({m.lap_time_display})" for m in laps]
        selected_lap_idx = st.selectbox(
            tr["sidebar_lap_label"],
            range(len(laps)),
            format_func=lambda i: lap_labels[i],
            key="lap",
            filter_mode="fuzzy",
        )
        selected_meta = laps[selected_lap_idx]

        st.divider()
        _date_display = (
            f"{selected_meta.date[:2]}/{selected_meta.date[2:4]}/{selected_meta.date[4:6]}"
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

    df_selected = load_csv(selected_meta.path)

    # ---------------------------------------------------------------------------
    # タブ
    # ---------------------------------------------------------------------------
    tab1, tab2, tab3 = st.tabs([
        tr["tab1_label"],
        tr["tab2_label"],
        tr["tab3_label"],
    ])

    # =====================================================
    # Tab 1: Alert title= パラメータ
    # =====================================================
    with tab1:
        col_main1, col_api1 = st.columns([3, 2], gap="large")

        with col_api1:
            st.subheader(tr["tab1_subheader_api"])
            st.markdown(tr["tab1_api_desc"])

        with col_main1:
            # ---- プリセット GT7 アラート ----
            st.subheader(tr["tab1_subheader_presets"])

            _tyre_fl_avg = float(df_selected["tyre_temp_fl"].mean())
            _tyre_fr_avg = float(df_selected["tyre_temp_fr"].mean())
            _tyre_rl_avg = float(df_selected["tyre_temp_rl"].mean())
            _tyre_rr_avg = float(df_selected["tyre_temp_rr"].mean())
            _tyre_max = max(_tyre_fl_avg, _tyre_fr_avg, _tyre_rl_avg, _tyre_rr_avg)

            st.success(
                tr["tab1_preset_success_body"].format(lap_time=selected_meta.lap_time_display),
                title=tr["tab1_preset_success_title"],
                icon=":material/flag:",
            )
            if _tyre_max > 110:
                st.warning(
                    tr["tab1_preset_warning_body"].format(temp=_tyre_max),
                    title=tr["tab1_preset_warning_title"],
                    icon=":material/thermostat:",
                )
            else:
                st.info(
                    tr["tab1_preset_info_body"],
                    title=tr["tab1_preset_info_title"],
                    icon=":material/info:",
                )
            st.error(
                tr["tab1_preset_error_body"],
                title=tr["tab1_preset_error_title"],
                icon=":material/warning:",
            )

            st.divider()

            # ---- インタラクティブデモ ----
            st.subheader(tr["tab1_subheader_interactive"])

            _ALERT_TYPE_KEYS = ["success", "info", "warning", "error"]
            _alert_type_labels: dict[str, str] = tr["tab1_type_labels"]
            _selected_type = st.segmented_control(
                tr["tab1_type_label"],
                options=_ALERT_TYPE_KEYS,
                format_func=lambda k: _alert_type_labels[k],
                default="success",
                key="alert_type",
            )
            _active_type = _selected_type or "success"

            _use_title = st.toggle(tr["tab1_title_toggle"], value=True, key="alert_use_title")

            _ci1, _ci2 = st.columns(2)
            with _ci1:
                _title_val = st.text_input(
                    tr["tab1_title_input"],
                    value=tr["tab1_title_placeholder"],
                    key="alert_title_val",
                    disabled=not _use_title,
                )
            with _ci2:
                _body_val = st.text_input(
                    tr["tab1_body_input"],
                    value=tr["tab1_body_placeholder"],
                    key="alert_body_val",
                )

            _alert_fn_map = {
                "success": st.success,
                "info": st.info,
                "warning": st.warning,
                "error": st.error,
            }
            _alert_fn = _alert_fn_map[_active_type]

            st.markdown(tr["tab1_compare_header"])
            _cc1, _cc2 = st.columns(2)
            with _cc1:
                st.caption(tr["tab1_without_title"])
                _alert_fn(_body_val)
            with _cc2:
                st.caption(tr["tab1_with_title"])
                if _use_title and _title_val:
                    _alert_fn(_body_val, title=_title_val)
                else:
                    _alert_fn(_body_val)

    # =====================================================
    # Tab 2: :shimmer[] ディレクティブ
    # =====================================================
    with tab2:
        col_main2, col_api2 = st.columns([3, 2], gap="large")

        with col_api2:
            st.subheader(tr["tab2_subheader_api"])
            st.markdown(tr["tab2_api_desc"])

        with col_main2:
            st.subheader(tr["tab2_subheader_demo"])

            _loading_mode = st.toggle(tr["tab2_loading_toggle"], key="tab2_loading")

            if _loading_mode:
                st.markdown(tr["tab2_shimmer_line1"])
                st.markdown(tr["tab2_shimmer_line2"])
                st.markdown(tr["tab2_shimmer_line3"])
            else:
                st.caption(tr["tab2_data_ready_caption"])
                _t2 = df_selected.index / len(df_selected) * selected_meta.lap_time_ms / 1000
                _fig2 = go.Figure()
                _fig2.add_trace(go.Scatter(
                    x=_t2,
                    y=df_selected["speed_kmh"],
                    name="Speed (km/h)",
                    line=dict(color="#58a6ff", width=1.5),
                    fill="tozeroy",
                    fillcolor="rgba(88,166,255,0.10)",
                ))
                _fig2.update_layout(
                    paper_bgcolor="#0d1117",
                    plot_bgcolor="#161b22",
                    font=dict(color="#8b949e"),
                    xaxis=dict(
                        title="Time (s)", gridcolor="#21262d", zerolinecolor="#30363d"
                    ),
                    yaxis=dict(
                        title="Speed (km/h)", gridcolor="#21262d", zerolinecolor="#30363d"
                    ),
                    height=320,
                    margin=dict(l=60, r=20, t=20, b=60),
                    legend=dict(
                        orientation="h",
                        y=-0.3,
                        bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#c9d1d9"),
                    ),
                )
                st.plotly_chart(_fig2, use_container_width=True)

            st.divider()

            # ---- 各コンテキストでの shimmer 表示例 ----
            st.subheader(tr["tab2_subheader_contexts"])
            for _ctx in tr["tab2_context_items"]:
                st.markdown(_ctx)

    # =====================================================
    # Tab 3: st.bottom コンテナ 解説
    # =====================================================
    with tab3:
        col_main3, col_api3 = st.columns([3, 2], gap="large")

        with col_api3:
            st.subheader(tr["tab3_subheader_api"])
            st.markdown(tr["tab3_api_desc"])

        with col_main3:
            st.subheader(tr["tab3_subheader_what"])
            st.markdown(tr["tab3_what_desc"])

            st.divider()

            st.subheader(tr["tab3_subheader_note"])
            st.markdown(tr["tab3_note_desc"])
            st.code(tr["tab3_code_example"], language="python")

    # =====================================================
    # st.bottom: 全タブ共通・ビューポート底部固定 テレメトリ HUD
    # =====================================================
    _speed_max_b = float(df_selected["speed_kmh"].max())
    _rpm_max_b = float(df_selected["engine_rpm"].max())
    _tyre_fl_b = float(df_selected["tyre_temp_fl"].mean())
    _tyre_fr_b = float(df_selected["tyre_temp_fr"].mean())
    _tyre_rl_b = float(df_selected["tyre_temp_rl"].mean())
    _tyre_rr_b = float(df_selected["tyre_temp_rr"].mean())
    _tyre_avg_b = (_tyre_fl_b + _tyre_fr_b + _tyre_rl_b + _tyre_rr_b) / 4

    with st.bottom:
        st.caption(tr["bottom_hint"])
        _b1, _b2, _b3, _b4, _b5, _b6 = st.columns(6)
        with _b1:
            st.metric(tr["bottom_lap_label"], f"LAP {selected_meta.lap_no}")
        with _b2:
            st.metric(tr["bottom_time_label"], selected_meta.lap_time_display)
        with _b3:
            st.metric(tr["bottom_circuit_label"], selected_meta.circuit)
        with _b4:
            st.metric(tr["bottom_speed_label"], f"{_speed_max_b:.0f} km/h")
        with _b5:
            st.metric(tr["bottom_rpm_label"], f"{_rpm_max_b:.0f}")
        with _b6:
            st.metric(tr["bottom_tyre_label"], f"{_tyre_avg_b:.1f}°C")


# ---------------------------------------------------------------------------
# スタンドアロン起動サポート
# `streamlit run v1.57.0/app.py` で直接実行された場合のみ動作する。
# importlib 経由でロードされる場合は __spec__ が設定されるためスキップ。
# ---------------------------------------------------------------------------
if __spec__ is None:  # type: ignore[name-defined]
    st.set_page_config(
        page_title="Racing Simulator Telemetry Analysis",
        page_icon="🏎",
        layout="wide",
    )

    # --- 言語選択 ---
    st.sidebar.selectbox(
        "🌐 言語 / Language",
        ["日本語", "English"],
        key="lang_selector",
    )
    st.sidebar.divider()

    # --- バージョン選択 (root app.py と同じロジックを再現) ---
    _root = Path(__file__).parent.parent

    def _scan_versions() -> list[str]:
        _versions: list[tuple[int, int, int, str]] = []
        for _folder in _root.iterdir():
            if not _folder.is_dir():
                continue
            _m = re.match(r"^v(\d+)\.(\d+)\.(\d+)$", _folder.name)
            if _m and (_folder / "app.py").exists():
                _versions.append((int(_m.group(1)), int(_m.group(2)), int(_m.group(3)), _folder.name))
        _versions.sort(reverse=True)
        return [v[3] for v in _versions]

    _available_versions = _scan_versions()
    st.sidebar.selectbox(
        "🔖 Streamlit Version",
        _available_versions,
        index=_available_versions.index(_THIS_VERSION) if _THIS_VERSION in _available_versions else 0,
        key="version_selector",
        help="デモを確認したい Streamlit バージョンを選択してください。",
    )
    st.sidebar.divider()

    # --- アクセスカウンター（バージョン切替に関わらず常時表示）---
    if "_visited" not in st.session_state:
        st.session_state["_visited"] = True
        try:
            _is_cloud = st.secrets.get("ENVIRONMENT") == "cloud"
        except Exception:
            _is_cloud = False
        if _is_cloud:
            _increment_counter(_THIS_VERSION)

    _selected = st.session_state["version_selector"]
    if _selected == _THIS_VERSION:
        show()
    else:
        _spec = importlib.util.spec_from_file_location(
            f"app_{_selected.replace('.', '_')}",
            _root / _selected / "app.py",
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            import sys as _sys
            _sys.modules[_spec.name] = _mod
            _spec.loader.exec_module(_mod)  # type: ignore[union-attr]
            if hasattr(_mod, "show"):
                _mod.show()

    # サイドバー最下部にアクセスカウンターを表示
    _counts = _load_counts()
    st.sidebar.divider()
    if _counts:
        st.sidebar.metric(label="📊 総アクセス数", value=f"{sum(_counts.values()):,}")
    else:
        st.sidebar.caption("📊 総アクセス数\n(Supabase 接続後に表示)")
