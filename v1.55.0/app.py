"""
GT7 Race Telemetry Analyzer
Streamlit v1.55.0 — Widget Binding & Dynamic Containers デモアプリ

【このバージョンで実演する機能 (v1.55.0)】

Widget Binding:
  Tab 1: bind="query-params" — 各ウィジェット種別のデモ

動的コンテナ:
  Tab 2: st.expander / st.popover の on_change + プログラム制御
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------------------------
# 定数
# ---------------------------------------------------------------------------
_DEFAULT_DATA_DIR = Path(__file__).parent.parent / "data"
_THIS_VERSION = "v1.55.0"


# ---------------------------------------------------------------------------
# 翻訳ヘルパー
# ---------------------------------------------------------------------------
def load_translations(lang: str) -> dict:
    locale_path = Path(__file__).parent / "locales" / f"{lang}.json"
    with locale_path.open(encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# ファイル名パターン
# ---------------------------------------------------------------------------
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
# データ処理ヘルパー
# ---------------------------------------------------------------------------
@st.cache_data
def load_all_meta(data_dir: Path) -> list[LapMeta]:
    metas: list[LapMeta] = []
    for f in sorted(data_dir.glob("*.csv")):
        m = _FNAME_RE.match(f.name)
        if not m:
            continue
        date, time_, source, circuit, car, tyre, condition, lap_no, lap_time = m.groups()
        metas.append(LapMeta(
            path=f, date=date, time=time_,
            session_id=f"{date}_{time_}",
            source=source, circuit=circuit, car=car,
            tyre=tyre, condition=condition,
            lap_no=int(lap_no), lap_time_str=lap_time,
        ))
    return metas


def group_sessions(metas: list[LapMeta]) -> dict[str, list[LapMeta]]:
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
# show(): v1.55.0 のコンテンツを描画する
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

    # -----------------------------------------------------------------------
    # サイドバー: データ選択
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.header(tr["sidebar_data_header"])

        data_dir_input = st.text_input(
            tr["sidebar_data_folder_label"],
            value=str(_DEFAULT_DATA_DIR),
            help=tr["sidebar_data_folder_help"],
            key="data_dir_155",
        )
        data_dir = Path(data_dir_input)
        if not data_dir.is_dir():
            st.error(tr["sidebar_folder_not_found"].format(data_dir=data_dir))
            st.stop()

        all_metas = load_all_meta(data_dir)
        sessions = group_sessions(all_metas)
        session_keys = list(sessions.keys())

        selected_session = st.selectbox(
            tr["sidebar_session_label"], session_keys, key="session_155",
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
            key="lap_155",
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

    # -----------------------------------------------------------------------
    # タブ
    # -----------------------------------------------------------------------
    tab1, tab2 = st.tabs([
        tr["tab1_label"],
        tr["tab2_label"],
    ])

    # =====================================================================
    # Tab 1: Widget Binding 基本
    # =====================================================================
    with tab1:
        col_demo, col_api = st.columns([3, 2], gap="large")

        with col_api:
            st.subheader(tr["tab1_api_subheader"])
            st.markdown(tr["tab1_api_desc"])

        with col_demo:
            st.subheader(tr["tab1_subheader"])

            # リセットフラグ処理: ウィジェット生成前にデフォルト値をセット
            if st.session_state.pop("_t1_reset_requested", False):
                st.session_state["t1_circuit"] = tr["tab1_selectbox_options"][0]
                st.session_state["t1_speed"] = 0
                st.session_state["t1_chart"] = tr["tab1_radio_options"][0]
                st.session_state["t1_metrics"] = ["Speed"]
                st.session_state["t1_note"] = ""

            # --- 各ウィジェットに bind="query-params" を付与 ---
            st.markdown(tr["tab1_url_hint"])

            circuit_val = st.selectbox(
                tr["tab1_selectbox_label"],
                tr["tab1_selectbox_options"],
                key="t1_circuit",
                bind="query-params",
            )
            speed_filter = st.slider(
                tr["tab1_slider_label"],
                0, 300, 0,
                step=10,
                key="t1_speed",
                bind="query-params",
            )
            chart_type = st.radio(
                tr["tab1_radio_label"],
                tr["tab1_radio_options"],
                horizontal=True,
                key="t1_chart",
                bind="query-params",
            )
            metrics = st.multiselect(
                tr["tab1_multiselect_label"],
                tr["tab1_multiselect_options"],
                default=["Speed"],
                key="t1_metrics",
                bind="query-params",
            )
            note = st.text_input(
                tr["tab1_text_input_label"],
                placeholder=tr["tab1_text_input_placeholder"],
                key="t1_note",
                bind="query-params",
            )

            st.divider()

            # --- リアルタイム query_params 表示 ---
            st.markdown(tr["tab1_live_url"])
            params_display = dict(st.query_params)
            if params_display:
                st.code(str(params_display), language="python")
            else:
                st.code("{}", language="python")

            st.markdown(tr["tab1_default_note"])

            st.divider()

            # --- リセットボタン ---
            if st.button(tr["tab1_reset_button"], help=tr["tab1_reset_help"], key="t1_reset"):
                st.session_state["_t1_reset_requested"] = True
                st.rerun()

            st.markdown(tr["tab1_reset_note"])

    # =====================================================================
    # Tab 2: 動的コンテナ (on_change + プログラム制御)
    # =====================================================================
    with tab2:
        col_demo3, col_api3 = st.columns([3, 2], gap="large")

        with col_api3:
            st.subheader(tr["tab3_api_subheader"])
            st.markdown(tr["tab3_api_desc"])

        with col_demo3:
            st.subheader(tr["tab3_subheader"])

            # -----------------------------------------------------------
            # st.expander — on_change + プログラム制御
            # -----------------------------------------------------------
            st.markdown(tr["tab3_expander_section"])

            # イベントログを session_state で管理
            if "exp_events" not in st.session_state:
                st.session_state.exp_events = []

            def _on_exp_change():
                is_open = st.session_state.get("dyn_exp", False)
                label = tr["tab3_expander_opened"] if is_open else tr["tab3_expander_closed"]
                st.session_state.exp_events = [label] + st.session_state.exp_events[:4]

            # プログラム制御ボタン
            _ec1, _ec2 = st.columns(2)
            with _ec1:
                if st.button(tr["tab3_expander_open_btn"], key="exp_open_btn"):
                    st.session_state["dyn_exp"] = True
            with _ec2:
                if st.button(tr["tab3_expander_close_btn"], key="exp_close_btn"):
                    st.session_state["dyn_exp"] = False

            with st.expander(
                tr["tab3_expander_label"],
                key="dyn_exp",
                on_change=_on_exp_change,
            ):
                _lap_ms = selected_meta.lap_time_ms
                st.metric("Lap Time", selected_meta.lap_time_display)
                _c1, _c2, _c3 = st.columns(3)
                _c1.metric("Max Speed", f"{df_selected['speed_kmh'].max():.0f} km/h")
                _c2.metric("Max RPM", f"{df_selected['engine_rpm'].max():.0f}")
                _c3.metric("Top Gear", int(df_selected["gear"].max()))

            if st.session_state.exp_events:
                st.markdown(tr["tab3_expander_event_log"])
                for evt in st.session_state.exp_events:
                    st.markdown(f"- {evt}")
            else:
                st.caption(tr["tab3_event_log_empty"])

            st.divider()

            # -----------------------------------------------------------
            # st.popover — on_change + プログラム制御
            # -----------------------------------------------------------
            st.markdown(tr["tab3_popover_section"])

            if "popover_events" not in st.session_state:
                st.session_state.popover_events = []

            def _on_popover_change():
                is_open = st.session_state.get("dyn_popover", False)
                label = tr["tab3_popover_opened"] if is_open else tr["tab3_popover_closed"]
                st.session_state.popover_events = [label] + st.session_state.popover_events[:4]

            _pc1, _pc2 = st.columns([1, 3])
            with _pc1:
                if st.button(tr["tab3_popover_open_btn"], key="popover_open_btn"):
                    st.session_state["dyn_popover"] = True

            with _pc2:
                with st.popover(
                    tr["tab3_popover_label"],
                    key="dyn_popover",
                    on_change=_on_popover_change,
                ):
                    st.write(tr["tab3_popover_content"])
                    _pop_metric = st.selectbox(
                        "Metric",
                        ["speed_kmh", "throttle_pct", "engine_rpm"],
                        key="pop_metric",
                    )
                    _pop_val = df_selected[_pop_metric].mean()
                    st.metric(f"Avg {_pop_metric}", f"{_pop_val:.1f}")

            if st.session_state.popover_events:
                st.markdown(tr["tab3_popover_event_log"])
                for evt in st.session_state.popover_events:
                    st.markdown(f"- {evt}")
            else:
                st.caption(tr["tab3_event_log_empty"])
