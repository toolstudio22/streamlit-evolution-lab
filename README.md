# streamlit-evolution-lab

[![Streamlit](https://img.shields.io/badge/Streamlit-1.56.0+-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org)
[![Demo](https://img.shields.io/badge/🚀_Demo-evolution--lab.streamlit.app-FF4B4B)](https://evolution-lab.streamlit.app/)

---

## 概要 / Overview

Streamlit の新機能をバージョンごとにデモするリポジトリです。  
`v*.*.*/app.py` をバージョンごとに追加していく構成で、サイドバーのドロップダウンから切り替えて各バージョンの新機能を比較できます。  
デモ題材には Gran Turismo 7 のリアルタイムテレメトリデータを使用しています。

<details>
<summary>English</summary>

A repository for demonstrating Streamlit's new features, organized by version.  
Each version is implemented as `v*.*.*/app.py`. You can switch between versions using the sidebar dropdown and compare new features side-by-side.  
Gran Turismo 7 real-time telemetry data is used as the demo subject.

</details>

---

## Live Demo

**[https://evolution-lab.streamlit.app/](https://evolution-lab.streamlit.app/)**

---

## バージョン一覧 / Versions

| バージョン | リリース日 | 実演機能 | 使用データ |
|---|---|---|---|
| [v1.56.0](./v1.56.0/app.py) | 2026-03-31 | `st.iframe` / `st.menu_button` | GT7 テレメトリ CSV |

<details>
<summary>English</summary>

| Version | Release Date | Features Demonstrated | Data Used |
|---|---|---|---|
| [v1.56.0](./v1.56.0/app.py) | 2026-03-31 | `st.iframe` / `st.menu_button` | GT7 Telemetry CSV |

</details>

### v1.56.0 タブ構成 / Tab Layout

| タブ | 実演機能 | 内容 |
|---|---|---|
| Tab 1 | `st.iframe(html_str)` | Python で生成したラップサマリー HTML カードをインライン表示。`height` モード（`"content"` / `"stretch"` / 固定 px）の切り替えデモ |
| Tab 2 | `st.iframe(Path(...))` | Plotly テレメトリチャート（速度・スロットル/ブレーキ・RPM・タイヤ温度の 4 段）を `Path` オブジェクトで渡して表示 |
| Tab 3 | `st.iframe("https://...")` | 外部 URL（OpenStreetMap・富士スピードウェイ）の埋め込み表示 |
| Tab 4 | `st.menu_button(...)` | CSV / JSON / HTML エクスポートとチャート切り替えをドロップダウンボタンで実現するツールバー UI |

<details>
<summary>English</summary>

| Tab | Feature Demonstrated | Description |
|---|---|---|
| Tab 1 | `st.iframe(html_str)` | Displays Python-generated lap summary HTML cards inline. Demo of `height` modes: `"content"` / `"stretch"` / fixed px |
| Tab 2 | `st.iframe(Path(...))` | Renders a Plotly telemetry chart (4-row layout: speed, throttle/brake, RPM, tyre temps) passed as a `Path` object |
| Tab 3 | `st.iframe("https://...")` | Embeds an external URL (OpenStreetMap / Fuji Speedway) |
| Tab 4 | `st.menu_button(...)` | Toolbar UI for CSV / JSON / HTML export and chart switching via dropdown buttons |

</details>

---

## セットアップ / Setup

### 前提条件 / Prerequisites

- Python 3.10 以上 / Python 3.10+
- Git

### 手順 / Steps

```bash
# 1. リポジトリをクローン / Clone the repository
git clone https://github.com/toolstudio22/streamlit-evolution-lab.git
cd streamlit-evolution-lab

# 2. 仮想環境を作成・有効化 / Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. 依存パッケージをインストール / Install dependencies
pip install -r v1.56.0/requirements.txt

# 4. アプリを起動 / Run the app
streamlit run v1.56.0/app.py
```

ブラウザで `http://localhost:8501` が自動的に開きます。  
The browser will open automatically at `http://localhost:8501`.

### Supabase 設定（任意）/ Supabase Configuration (Optional)

アクセスカウンター機能を使用する場合は `.streamlit/secrets.toml` を作成してください。  
未設定でもアプリはすべての機能を利用できます。

<details>
<summary>設定例 / Configuration example</summary>

```toml
# .streamlit/secrets.toml
[supabase]
url = "https://<your-project>.supabase.co"
key = "<your-anon-key>"
```

</details>

<details>
<summary>English</summary>

To enable the access counter feature, create `.streamlit/secrets.toml`.  
The app works fully without this configuration.

</details>

---

## ディレクトリ構造 / Project Structure

```
streamlit-evolution-lab/
├── .devcontainer/          # Dev Container configuration
├── .streamlit/
│   └── secrets.toml        # Supabase credentials (git-ignored)
├── data/                   # GT7 telemetry CSV files
│   └── YYMMDD_HHMMSS_Live_<Circuit>_<Car>_<Tyre>_<Surface>_L<Lap>_<LapTime>.csv
├── v1.56.0/
│   ├── app.py              # Streamlit app (v1.56.0)
│   ├── requirements.txt
│   └── reports/            # Auto-generated HTML reports (git-ignored)
│       ├── telemetry.html
│       └── telemetry_menu.html
├── .gitignore
└── README.md
```

> `v*/reports/` および `.streamlit/secrets.toml`、`.venv/` は `.gitignore` によりリポジトリ管理外です。  
> `v*/reports/`, `.streamlit/secrets.toml`, and `.venv/` are excluded by `.gitignore`.

---

## データ形式 / Data Format

### ファイル名規則 / Filename Convention

```
YYMMDD_HHMMSS_Live_<Circuit>_<Car>_<Tyre>_<Surface>_L<Lap>_<LapTime>.csv
```

**例 / Example:**  
`260414_224256_Live_Fuji_Supra18_RM_Dry_L05_1m39s427.csv`  
→ 2026-04-14 22:42:56、富士スピードウェイ、GR スープラ '18、レーシングミディアム、ドライ、Lap 5、1:39.427

### 主要カラム / Key Columns

| カテゴリ / Category | カラム / Columns |
|---|---|
| 位置・速度 / Position & Speed | `pos_x/y/z`, `speed_kmh`, `vx/vy/vz` |
| 姿勢 / Orientation | `rotation_x/y/z`, `yaw_rate`, `ang_vel_x/z` |
| 操作入力 / Driver Input | `throttle_pct`, `brake_pct`, `clutch_pedal`, `gear` |
| エンジン / Engine | `engine_rpm`, `boost_pressure`, `fuel_remaining`, `water_temp`, `oil_temp` |
| タイヤ / Tyres | `tyre_temp_fl/fr/rl/rr`, `tyre_radius_fl/fr/rl/rr`, `sus_height_fl/fr/rl/rr` |
| 計時 / Timing | `best_lap_ms`, `last_lap_ms`, `lap_count` |
| G センサー / G-Force | `lat_g`, `lon_g` |
| 制御フラグ / Control Flags | `is_on_track`, `tcs_active`, `asm_active`, `hand_brake_active` |

---

## 関連記事 / Related Articles

### Qiita

- **【Streamlit 1.56.0】st.iframe が登場！HTML・外部URL・ファイルの埋め込みがこれ 1 つで完結**  
  <!-- TODO: 公開後に URL を更新してください / Update URL after publishing -->  
  `https://qiita.com/...`

- **Streamlit 1.56.0 新機能「st.menu_button」でツールバーとドロップダウンメニューが驚くほど簡単に作れるようになった話**  
  <!-- TODO: 公開後に URL を更新してください / Update URL after publishing -->  
  `https://qiita.com/...`
