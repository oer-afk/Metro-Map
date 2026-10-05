# 地下鉄学習マップ

中国の都市の地下鉄の路線と駅を、実際の地図の上で覚えるための学習用ページ。
仕様は [docs/metro-map-spec.md](docs/metro-map-spec.md)。乗換案内・旅行計画の機能は持たない。

現在の段階：**第 1 段階（上海）完了**（2026-10-04）。

## フォルダ構成

```
metro-map/
├─ README.md                  この文書（判断事項・手順）
├─ requirements.txt           データ作成用の Python ライブラリ
├─ docs/metro-map-spec.md     仕様・指示書（原本の写し）
├─ site/                      ← 表示ページ一式。公開するときはこのフォルダだけを置く
│   ├─ index.html / app.js / style.css
│   └─ data/cities.json, data/shanghai.json
├─ config/<city>.json         都市ごとの取得・加工設定（行政区、主要エリア、除外条件など）
├─ tools/                     データ作成スクリプト（Python 3）
│   ├─ fetch_osm.py           Overpass API → raw/<city>/routes.json, stations.json
│   ├─ fetch_reference.py     照合用の駅一覧・路線色（中国語版 Wikipedia）→ raw/<city>/
│   ├─ build_city.py          raw/ → site/data/<city>.json（＋ reports/）
│   ├─ textconv.py            日本漢字表記・ピンイン・カタカナ（駅データに依存しない部品）
│   └─ validate.py            検証（仕様 6.3）→ reports/<city>_validation.md
├─ overrides/                 人が直す辞書（下記）
├─ raw/<city>/                取得した生データ。再取得せずに加工をやり直せる
└─ reports/                   ビルド記録・検証結果・全駅一覧
```

## 使い方

### 開く（PC・iPhone・iPad 共通）

**https://oer-afk.github.io/Metro-Map/** をブラウザで開く（ブックマークやホーム画面への追加がおすすめ）。PC 側のサーバーは不要。

- GitHub リポジトリ: https://github.com/oer-afk/Metro-Map （フォルダ全体を公開）
- `site/` の変更を `main` に push すると、GitHub Actions（`.github/workflows/pages.yml`）が `site/` だけを Pages に公開する（1〜2 分）。
- データを作り直したら、`site/data/` と `reports/` などをコミットして push する。

### ローカルで起動する（PC・オフライン確認用）

**`start.bat` をダブルクリック**するだけ。ローカルサーバーが最小化ウィンドウ（タスクバーの「metro-map server」）で立ち上がり、ブラウザで http://localhost:8765/ が開く。

- もう一度ダブルクリックしても、サーバーは増えずブラウザが開くだけ。
- 止めるときは、タスクバーの「metro-map server」ウィンドウを閉じる。
- サーバーは自分の PC（127.0.0.1）からしか見えない。iPhone・iPad では上の公開 URL を使う。
- 地図ライブラリ（Leaflet・MapLibre）と背景地図はネットから読み込むため、ネット接続が必要。
- `index.html` を直接開くと JSON が読めないので、必ず `start.bat`（または下のコマンド）から開く。

手動で起動する場合:

```bash
python -m http.server 8765 --directory site
```

### データを作り直す

```bash
pip install -r requirements.txt
python tools/fetch_osm.py shanghai          # OSM を再取得（数分。混雑時は自動で再試行）
python tools/fetch_reference.py shanghai    # 照合用の Wikipedia を再取得
python tools/build_city.py shanghai         # site/data/shanghai.json を作る
python tools/validate.py shanghai           # reports/shanghai_validation.md を作る
```

- 辞書（overrides/）だけを直した場合は `build_city.py` と `validate.py` だけでよい。
- `fetch_reference.py shanghai --offline` で、保存済みの wikitext から照合 CSV だけ作り直せる。
- Windows では日本語を含む出力のため `set PYTHONIOENCODING=utf-8`（PowerShell なら `$env:PYTHONIOENCODING="utf-8"`）を付けて実行する。
- OneDrive 上にあるため、仮想環境（venv）はこのフォルダの中に作らないこと（同期が重くなる）。

### 都市を追加する（第 2 段階以降）

1. `config/<city>.json` を作る（`overpass_area`、`focus_bbox`、`script`、`reading_lang` など。上海を手本に）
2. `fetch_osm.py` → `build_city.py` → `validate.py`
3. `build_city.py` が `site/data/<city>.json` を書き、`site/data/cities.json` に 1 行追加する。表示ページの修正は不要。

広東語（香港）の読みは `textconv.py` に `reading_yue()` を足す必要がある（第 3 段階）。

## データ構造（site/data/<city>.json）

仕様書 5 章の形に、次の項目を加えている。表示ページはこれらを画面に出さない（`branches` 等は内部情報）。

| 場所 | 項目 | 内容 |
|---|---|---|
| 都市 | `name_orig` | 都市名の原表記 |
| 都市 | `source.license` | `ODbL 1.0` |
| 路線 | `color_source` | `osm`（OSM の colour）または `supplemented`（overrides で補完） |
| 路線 | `mode` | OSM の route 種別。`subway`、浦江線は `light_rail` |
| 路線 | `loop` | 環状線なら `true`（4号線） |
| 路線 | `branches` | 支線。分岐駅から支線終点までの駅 ID の配列の配列 |
| 駅 | `name_en` | OSM の `name:en`（上海は参考保持。表示しない） |

**支線の持ち方**：`stations` は「本線の駅順 → 支線にしかない駅」の順に並べた路線の全駅。
本線は OSM の運転系統のうち駅数が最も多いもの。`branches` の各配列は先頭が分岐駅（本線上）で、そこから支線の終点まで。
上海では 5号線（东川路→闵行开发区）、10号線（龙溪路→航中路）、11号線（嘉定新城→嘉定北）が該当する。
区間運転・急行（1号線の上海火车站折返し、16号線の大站车・直达车）は駅が本線に含まれるので持たない。

## 判断した事項

### 対象路線（上海）

- 上海地铁の営業路線 **1〜18号線と浦江線の 19 路線**。Wikipedia の営業路線と一致。
- **浦江線を含めた**：OSM では `route=light_rail` だが、上海地铁の正式な路線（APM）で公式路線図にも載るため。`mode: light_rail` で区別できる。
- **除外**：磁浮線、市域機場線・金山鉄道（市域鉄道）、浦東空港の旅客捷運（APM）、松江トラム。`config/shanghai.json` の `route_types`・`network_include`・`exclude_relation_name_patterns` で指定。
- 開業前の路線（19〜23号線など）は OSM に route リレーションが無く、混入していない。既存路線の延伸区間（建設中）も混入なし（validate で確認）。

### OSM と現況の食い違いの直し（overrides/station_status_shanghai.json）

- **9号線 金吉路を追加**：2017-12-30 に開業済みだが OSM の 9号線リレーションに停車位置が無い。`railway=station` の点から位置を取り、金桥〜金海路の間に入れた。
- **14号線 龙居路を除外**：OSM のリレーションに停車位置があるが、Wikipedia の駅一覧では未供用（14号線は 2021 年に龙居路以外の 30 駅で開業）。開業したらこの行を消して再ビルドする。
- **改称**：OSM の 14号線の停車位置 1 つに旧名「东昌路」が残っていたため「浦东南路」に置換（overrides/station_renames_shanghai.json）。

### 路線色

OSM の `colour` を採用した（仕様 6.2 の手順どおり。値は運営会社の Pantone 指定の換算値とみられる）。全路線に colour があり、補完はなし。
Wikipedia の色（路線図からの採色）とは路線によって差があり、とくに 16号線は差が大きい（OSM #2CD5C4／Wikipedia #98D1C0）。一覧は `reports/shanghai_validation.md`。
変えたい場合は OSM 側を直すか、`build_city.py` で `overrides/line_colors.json` を優先するよう変える。

### 駅の統合と位置

- 同じ駅名の停車位置を 800 m 以内でまとめて 1 駅にする（同名で離れた別駅は上海には無かった）。
- 位置は `railway=station` の点（無ければ停車位置の平均）を基に、**所属路線の線形上の最寄り点の平均**へ寄せた。
  単独駅は線の上に乗り、乗換駅は各路線の間に来る。乗換駅のうち路線同士が離れている駅（国家会展中心、浦东南路、曹杨路など）は、どちらの線からも 150〜300 m 離れる（仕様の「1 駅 1 点」による）。
- 駅 ID は `sh_` ＋ 声調なしピンイン（例：`sh_lujiazui`）。

### 表記と読み

- 日本漢字：OpenCC（簡体→繁体→日本新字体）。地名で略字化しない字を `overrides/chars_ja.json` で戻している（竜→龍、予→豫、澱→淀、巌→岩、粵→粤）。区切り点は「・」。
- ピンイン：pypinyin（声調は本来の声調、軽声は使わない）。地名の多音字を `overrides/pinyin_words.json` で直している（闵行 Mǐnháng、莘庄・七莘・虹莘の莘 xīn、长风・长清の长 cháng、刘行 Liúháng、银都 dū など）。
- 分かち書き（`textconv.segment`）：
  - 通名（路・公路・大道・大桥・街・寺・公园・博物馆・火车站・航站楼）は前と分ける。
  - 方位・数字＋路は `Dōng Lù`・`Sān Lù` と分ける（固有名部分が 3 字以上のとき。北中路・场中路などはそのまま）。
  - 語末の方位も分ける（三林东 → Sānlín Dōng）。
  - 「上海」は語頭で独立（上海科技馆 → Shànghǎi Kējìguǎn）。
  - 新城・新村・大学・中心・开发区・保税区・大学城も前と分ける。
  - 残りの固有名は 3 字以下を続け書き、4 字以上は 2 字ずつ（端数は末尾の語に寄せる）。合わないものは `overrides/segments.json`。
- カタカナ：音節の対応表（`textconv.syllable_to_kana`）。付録 A の表記を正として規則を合わせた。
  語の区切りは「・」、駅名の区切り点（·）は「／」。方位・数字＋路と「n号」はカナで続ける（ドンルー、イーハオ）。
- 付録 A の 64 駅は確認済みとして上書きし、`verified: true`。**機械変換と付録 A の食い違いは 0 件**（`reports/shanghai_machine_vs_verified.csv`）。

### 表示ページ

- 地図：Leaflet 1.9.4。
- 背景地図
  - 既定「淡色（ラベルなし）」＝ OpenFreeMap の Positron スタイルから文字・記号の層を除いたもの（MapLibre GL を Leaflet に重ねて描画）。
    仕様作成時に想定していた CARTO の淡色タイルは、2026-10 時点で API キー必須（「API KEY REQUIRED」の透かし）になっていたため使っていない。
  - 「標準（ラベルあり）」＝ OpenStreetMap 標準タイル（少量利用の範囲で。大量アクセスする用途にはしない）。
  - どちらも出典を右下に表示する（© OpenStreetMap contributors ほか）。
- 駅：単独駅は路線色の点、乗換駅は大きめの白抜き。**未確認の駅は薄く・破線の縁**。
- 吹き出し（ホバー、タッチ端末ではタップ）：原表記 ／ 日本漢字、ピンイン（カナ）、路線バッジのみ。緯度・経度は出さない。
- ズーム 14 以上で駅名を常時表示。表記（日本漢字・原表記・両方・なし）を切替可能。
- 凡例で路線ごとに表示・非表示。都市・背景・ラベル表記・非表示路線はブラウザに記憶する（`localStorage`。消えても初期状態で動く）。
- URL の `#shanghai` で都市を指定できる。
- `window.metroMap` に地図オブジェクトを出している（開発者ツールでの確認用）。

## 検証結果（第 1 段階・上海）

詳細は [reports/shanghai_validation.md](reports/shanghai_validation.md)。

- 路線数 19（Wikipedia の営業路線と一致）、駅数 **413**。
- 各路線の駅数・駅名：上記の金吉路・龙居路の上書き後、**全 19 路線で Wikipedia と一致**。
- 開業前の駅・路線の混入：なし。
- 駅と自路線の線形の距離：150 m を超えるのは乗換駅のみ（上記）。
- 付録 A の所属路線と OSM の差：なし。
- **未確認の駅：349**（確認済み 64）。全駅の表記・読みは `reports/shanghai_stations.csv`（Excel で開ける）で確認できる。
  確認して直す場合は、読みの誤りなら `overrides/pinyin_words.json`、分かち書きなら `overrides/segments.json`、
  確認済みにするなら `overrides/verified_shanghai.csv` に行を足して再ビルドする。

## 出典・ライセンス

- 路線・駅データ：© OpenStreetMap contributors（ODbL 1.0）。
- 背景地図：OpenFreeMap / OpenMapTiles / OpenStreetMap、OpenStreetMap 標準タイル。
- 照合用（表示データには混ぜない）：中国語版 Wikipedia「上海地铁车站列表」「Module:Adjacent stations/上海地铁」（CC BY-SA）。
