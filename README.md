# 地下鉄学習マップ

中国の都市の地下鉄の路線と駅を、実際の地図の上で覚えるための学習用ページ。
仕様は [docs/metro-map-spec-v2.md](docs/metro-map-spec-v2.md)（第2版。第1版は [docs/metro-map-spec.md](docs/metro-map-spec.md)）。乗換案内・旅行計画の機能は持たない。

現在の段階：**段階 2b（香港・高鉄）完了**（2026-10-06）。仕様書第2版の範囲はすべて実装済み。

| 地域 | 路線網 | 路線 | 駅 | 確認済み |
|---|---|---:|---:|---:|
| 上海 | 上海 | 19 | 413 | 64（付録 A・本人確認） |
| 珠江デルタ（広深港） | 広州 | 19 | 317 | 50（AI 照合・本人承認） |
| 〃 | 深圳 | 17 | 351 | 50（同上） |
| 〃 | 香港 | 13（MTR 10・輕鐵・電車・山頂纜車） | 254 | 51（同上） |
| 〃 | 高鉄 | 2（広深港高速鉄道・広深線） | 18 | 0 |

**確認済みの意味**: 上海の 64 駅は付録 A（本人が確認したもの）。広州・深圳・香港は、本人の承認のもとで AI が点検したもの
（英語の公式駅名との突き合わせ、多音字・字形・定着名の点検。確認方法は `overrides/verified_<id>.csv` の「確認方法」列に記録）。

## フォルダ構成

```
metro-map/
├─ README.md                  この文書（判断事項・手順）
├─ requirements.txt           データ作成用の Python ライブラリ
├─ docs/metro-map-spec-v2.md  仕様書 第2版（珠江デルタ拡張）
├─ docs/metro-map-spec.md     仕様書 第1版（原本の写し）
├─ site/                      ← 表示ページ一式。公開するときはこのフォルダだけを置く
│   ├─ index.html / app.js / style.css
│   └─ data/cities.json（路線網の一覧）, data/<id>.json（shanghai・guangzhou・shenzhen・hongkong・prd_rail）
├─ config/<id>.json           路線網ごとの取得・加工・照合の設定（下記）
├─ tools/                     データ作成スクリプト（Python 3）
│   ├─ fetch_osm.py           Overpass API → raw/<city>/routes.json, stations.json
│   ├─ fetch_reference.py     照合用の駅一覧・路線色（中国語版 Wikipedia）→ raw/<city>/
│   ├─ build_city.py          raw/ → site/data/<city>.json（＋ reports/）。地下鉄・輕鐵・電車の路線網
│   ├─ build_rail.py          高鉄（線路の路線リレーション＋駅一覧）→ site/data/prd_rail.json（取得も兼ねる）
│   ├─ textconv.py            日本漢字表記・ピンイン・カタカナ（駅データに依存しない部品）
│   ├─ validate.py            検証（仕様 6.3）→ reports/<id>_validation.md
│   └─ make_verify_draft.py   確認用の駅一覧 → reports/<id>_verify_draft.csv
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
python tools/fetch_osm.py guangzhou          # OSM を再取得（数分。混雑時は予備サーバーへ自動で切り替え）
python tools/fetch_reference.py guangzhou    # 照合用の Wikipedia を再取得
python tools/build_city.py guangzhou         # site/data/guangzhou.json を作る
python tools/validate.py guangzhou           # reports/guangzhou_validation.md を作る
python tools/make_verify_draft.py guangzhou  # 確認用の駅一覧（主要エリアの 50 駅）を作る
```

`guangzhou` の部分を `shanghai`・`shenzhen`・`hongkong` に替えれば他の路線網も同じ。
高鉄だけは別のスクリプトで、`python tools/build_rail.py prd_rail --fetch`（`--fetch` を外すと保存済みの raw/ から作り直す）。

- 辞書（overrides/）だけを直した場合は `build_city.py` と `validate.py` だけでよい。
- `fetch_reference.py <id> --offline` で、保存済みの wikitext から照合 CSV だけ作り直せる。
- **上海の回帰確認**: 仕組みを変えたら、上海の路線・駅・表記・読み・座標が変わっていないことを確かめる（段階 2a では差 0 を確認済み）。
- 文字コードはスクリプト側で UTF-8 に固定しているので、Windows のコマンドプロンプト・PowerShell からそのまま実行できる。
- OneDrive 上にあるため、仮想環境（venv）はこのフォルダの中に作らないこと（同期が重くなる）。

### 路線網を追加する

1. `config/<id>.json` を作る（広州・深圳を手本に）。主な項目:

| 項目 | 内容 |
|---|---|
| `region` / `region_name_ja` / `order` | 地域と、その中での「移動」の並び順 |
| `overpass_area` | 取得範囲。**Wikidata の ID で指定する**（例 `area["wikidata"="Q16572"]`。地名指定は広州・深圳で失敗した） |
| `route_types` / `network_include` / `network_exclude` / `exclude_relation_name_patterns` | 含める路線の条件 |
| `id_prefix` | 路線 ID・駅 ID の接頭辞（`sh` `gz` `sz`） |
| `line_names` / `badges` / `line_ids` | 番号のない路線の名前・バッジ・ID（例 広州 `GF` → 广佛线・バッジ `广佛`） |
| `ref_by_name_pattern` | ref の無い支線を路線にまとめる |
| `line_station_ranges` | 直通運転で OSM が 1 本にしている路線を公式の区切りで切る（深圳 2号線・8号線） |
| `extra_track_ways` | 路線リレーションに入っていない線路を名前で追加取得する（深圳 13号線の北延伸） |
| `keep_zhan_regex` | 駅名末尾の「站」を残す駅（广州南站・深圳北站など） |
| `reference` | 照合用の Wikipedia（ページ名、駅テンプレートの系統名、見出し→路線の対応、色の定義） |
| `rename_checks` / `validation_notes` | 既知の改称の確認、理由の分かっている照合差の注記 |
| `reading_langs` / `script` | 読みの言語（香港は `["cmn","yue"]`）と字体（`hant` で繁体字の扱い） |
| `name_tags` / `id_from_en` | 駅名を取るタグの優先順（香港は `name:zh-Hant`）、駅 ID を英語名から作る |
| `ref_by_network` / `allow_no_network_route_types` | 系統ごとの relation を 1 路線にまとめる（輕鐵・電車）、事業者タグの無い路線を許す（山頂纜車） |
| `line_order` / `line_colors` / `groups` / `group_by_mode` / `kind_by_mode` | 番号の無い路線の並び、色の指定（系統ごとに色が違う輕鐵・電車など）、凡例の小見出し、駅の種別 |
| `reference` を配列に | 照合ページを複数（港鐵・輕鐵）。`station_re` で駅名の書式、`variant` で字体、`stop_at` で読む範囲を指定 |

2. `fetch_osm.py` → `fetch_reference.py` → `build_city.py` → `validate.py` → `make_verify_draft.py`
3. `build_city.py` が `site/data/<id>.json` を書き、`site/data/cities.json` に 1 行追加する。表示ページの修正は不要。

## データ構造（site/data/<id>.json）

仕様書第2版 5 章のとおり。主な点:

| 場所 | 項目 | 内容 |
|---|---|---|
| 路線網 | `region`, `reading_langs` | 地域、読みの言語（`["cmn"]`。香港は `["cmn","yue"]`） |
| 路線網 | `source.license` | `ODbL 1.0` |
| 路線 | `id` | **路線網の接頭辞付き**（`sh_2`、`gz_gf`、`sz_6b`）。複数の路線網を同時に表示しても重ならない |
| 路線 | `badge` | バッジの文字（番号、または `广佛` `6支` など） |
| 路線 | `color_source` | `osm`（OSM の colour）または `supplemented`（overrides で補完） |
| 路線 | `mode` | OSM の route 種別。`subway`、浦江線・広州 APM 線は `light_rail` |
| 路線 | `loop` | 環状線なら `true`（上海 4号線、広州 11号線） |
| 路線 | `branches` | 支線。分岐駅から支線終点までの駅 ID の配列の配列 |
| 駅 | `reading` | 言語ごとの入れ物。普通話は `{"cmn": {"roman", "kana"}}` |
| 駅 | `kind` | `metro` ／ `light_rail` ／ `tram` ／ `funicular` ／ `hsr`（記号の出し分け） |
| 駅 | `reading`（香港） | `{"cmn": {"roman"}, "yue": {"jyutping", "kana"}}`。高鉄の香港西九龍駅も同じ |
| 駅 | `name_en` | OSM の `name:en`（上海・広州・深圳は参考保持。表示しない） |

**支線の持ち方**：`stations` は「本線の駅順 → 支線にしかない駅」の順に並べた路線の全駅。
本線は OSM の運転系統のうち駅数が最も多いもの。`branches` の各配列は先頭が分岐駅（本線上）で、そこから支線の終点まで。
上海では 5号線（东川路→闵行开发区）、10号線（龙溪路→航中路）、11号線（嘉定新城→嘉定北）が該当する。
区間運転・急行（1号線の上海火车站折返し、16号線の大站车・直达车）は駅が本線に含まれるので持たない。

## 判断した事項

### 広州（段階 2a）

- **含める**: 地下鉄 1〜14・18・21・22号線、広佛線（佛山区間を含む全線）、APM線、14号線知識城支線、7号線の佛山（順徳）区間（広州地鉄が運行する 7号線の一部）。
- **除外**: トラム（海珠・黄埔）、佛山地鉄 2号線（広州南駅まで乗り入れるが佛山地鉄の路線）。
- **11号線 广州火车站を除外**: OSM には停車位置があるが、国鉄広州駅の改築に合わせて開業日未定（Wikipedia で「有待確定」）。
- **12号線 赤岗を追加**: 2026-02-13 開業だが OSM の 12号線に未反映。8号線の赤岗駅の位置を使い、乗換駅になる。
- 読みの上書き（`overrides/pinyin_words_guangzhou.json`）: 广東の地名の「涌」は chōng（东涌・大涌など）、「陂」は bēi（车陂・黄陂）、区庄の「区」は ōu、长洲・长湴の「长」は cháng、美的は měidì。
  上海の黄陂南路（Huángpí、付録 A）と広州の黄陂（Huángbēi）のように、同じ字でも都市で読みが違うため都市別の辞書にした。

### 深圳（段階 2a）

- **含める**: 地下鉄 1〜14・16・20号線、6号線支線。**除外**: トラム、坪山雲巴。
- **2号線・8号線**: 直通運転のため OSM では両方とも赤湾〜溪涌の 1 本で登録されている。公式の区切り（2号線 赤湾〜莲塘、8号線 莲塘〜溪涌）で駅と線形を切り分けた。境界の莲塘は両方の駅（Wikipedia は 2号線側にだけ載せている。レポートに注記）。
- **13号線の北延伸（上屋〜李松蓢の 11 駅）を追加**: 2026-06-28 開業。OSM に駅と線路はあるが 13号線のリレーションに未反映のため、駅は `railway=station`、線形は線路の名前（深圳地铁13号线）で追加取得した。
- 読みの上書き（`overrides/pinyin_words_shenzhen.json`）: 「厦」は xià（岗厦・湾厦）、「涌」は chōng（溪涌）、茜坑は Xīkēng、民乐は Mínlè、长圳・长岭陂の「长」は cháng。

### 香港（段階 2b）

- **含める**: MTR 10 路線（エアポートエクスプレス・ディズニーランド線を含む）、輕鐵（12 系統を 1 路線「輕鐵」に。68 停留所）、香港電車（6 系統を 1 路線「香港電車」に。82 停留所＝同名の上下の停留所を 1 点に）、山頂纜車（6 駅）。
  **除外**: 空港内 APM、海洋公園の海洋列車、ディズニーランド園内鉄道。
- **同名の駅の扱い**: 統合は「種別（地下鉄・輕鐵・電車・纜車）と名前」が同じものだけ。MTR の屯門駅と輕鐵の屯門停留所は別の点。
- **駅名**: OSM の `name` は「旺角 Mong Kok」のように中英併記なので `name:zh-Hant`・`name:zh` を使う。英語名は `name:en`。駅 ID は英語名から（`hk_mongkok`、輕鐵は `hk_lr_…`）。
  電車の「總站」（終点）は駅名の一部として残す。
- **読み**: 普通話は簡体字に直してピンイン（香港の地名の「涌」は chōng）。分かち書きは、英語由来の音訳地名（堅尼地城＝Kennedy Town）を 2 字ずつに切らず、「道」「總站」「醫院」「碼頭」を通名として切る。
  広東語は pycantonese の粤拼（多音字は `overrides/jyutping_words.json`、例: 深水埗 bou6）。
  カナは粤拼から対応表で作り、語ごとに「・」で区切る（皇后大道西＝ウォンハウ・タイトー・サイ）。日本で定着した広東語由来の呼び名は `overrides/kana_yue.json`（旺角＝モンコック、九龍＝カオルーン など。語の単位でも当てる: 屯門醫院＝トゥエンムン・イーユン）。
- **色**: MTR は OSM の colour。輕鐵（#D3A809、MTR の輕鐵の色）・電車（#00704A）・山頂纜車（#9B2335）は系統ごとに色が違う／無いため config で指定。
- **日本漢字**: 繁体字から直接 t2jp。「綫」→「線」、「啟」→「啓」を補正。

### 高鉄（段階 2b）

- **広深港高速鉄道**（OSM relation 9405634）: 广州南・南沙北（旧 庆盛、改称済み）・虎门・光明城・深圳北・福田・香港西九龍の 7 駅。
- **広深線**（OSM relation 408151）: 中国語版 Wikipedia「广深铁路」の駅一覧のうち、類型に「客」を含み廃止・休止の注記が無い 11 駅（广州・广州东・石牌・广州新塘・石龙・东莞・常平・樟木头・平湖・深圳东・深圳）。
- 運行系統（route=train）の情報が乏しいため、**線形は線路の路線リレーション、駅は config の駅名に一致する railway=station の点**から作る（`tools/build_rail.py`）。駅の点は線路の上に寄せる。
- 駅名は「站」まで含めた正式名（广州南站）。地下鉄の同名駅とは別の点で、**四角**の記号。香港西九龍站は香港と同じ 4 言語の吹き出し。
- 色は公式の定めが無いため、区別しやすい色を選んだ（広深港＝赤 #C8102E、広深＝紺 #1F4E9A）。
- 「移動＝高鉄」の主要エリアは、全駅と線形が収まる範囲を自動計算して上書きする。

### 3都市共通の判断（段階 2a）

- 地名では軽声を使わない（竹子林 Zhúzǐlín、太子湾 Tàizǐwān）。上海の読みへの影響は無し。
- 「广场」「口岸」も前の語と分かち書きにする（团一大广场 Tuányīdà Guǎngchǎng、深圳湾口岸 Shēnzhènwān Kǒu'àn）。
- 日本漢字の補正を追加: 湧→涌（地名の「涌」）、廈→厦、衝→沖（文冲）、曬→晒。
- 照合（Wikipedia）の未開業の判定: 上海は「建设中」・灰色背景、広州・深圳は**斜体の駅名**・「預計2026年」「预留站」「有待確定」・「后通段（在建）」の見出し。コメントアウトされた行は読まない。

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
- 上部バー: **地域**（上海 ／ 珠江デルタ（広深港））、**移動**（広州・深圳・香港の主要エリア、高鉄は珠江デルタ全体）、主要エリア・全域、駅名、地図、路線。
  同じ地域の路線網はまとめて読み込み、同時に表示する（全域で広州と深圳が両方見える）。
- 「**表示する路線**」パネル（「路線」ボタン）: 路線網ごとのタブ（広州 ／ 深圳 ／ 香港 ／ 高鉄）。香港のタブは MTR・輕鐵・電車・山頂纜車の小見出しと、広東語の声調の早見表付き。各タブの先頭に「この路線網を表示」と全表示／全非表示、その下に路線ごとの表示切替。狭い画面では色付きバッジだけを並べる。
- 駅：単独駅は路線色の点、乗換駅は大きめの白抜き、高鉄の駅は四角、輕鐵・電車の停留所は小さめの点（線も細め）。**未確認の駅は薄く・破線の縁**。
- 吹き出し（ホバー、タッチ端末ではタップ）：原表記 ／ 日本漢字、ピンイン（カナ）、路線バッジのみ。緯度・経度は出さない。
  香港の駅（と香港西九龍站）は「原表記 ／ 英語 ／ 日本漢字」「普 ピンイン」「粤 粤拼（上付きの声調数字）（カナ）」と路線バッジ。
- ズーム 14 以上で駅名を常時表示。表記（日本漢字・原表記・両方・英語・なし）を切替可能。英語は香港の駅だけ英語名、それ以外は原表記。
- 地域・移動先・背景・ラベル表記・非表示の路線と路線網・開いているタブはブラウザに記憶する（`localStorage`。消えても初期状態で動く）。
- URL の `#<路線網 id>`（`#shanghai`、`#guangzhou`、`#shenzhen`、`#hongkong`、`#prd_rail`）でその路線網の主要エリアを開ける。
- `window.metroMap` に地図オブジェクトを出している（開発者ツールでの確認用）。

## 検証結果（段階 2b・香港・高鉄）

詳細は [reports/hongkong_validation.md](reports/hongkong_validation.md)、[reports/prd_rail_validation.md](reports/prd_rail_validation.md)。

- 香港: MTR 10 路線と輕鐵の駅数・駅名が Wikipedia（港鐵車站列表・香港輕鐵車站列表）と全一致。電車・山頂纜車は照合先の表が無いため注記扱い。駅と線形の距離 150 m 超なし。**未確認 203**。
- 高鉄: config の 18 駅（Wikipedia の旅客駅）がすべて線路から 50 m 以内に見つかった。**未確認 18**。
- 段階 2a の 3 都市への影響: 上海は差 0。深圳は駅名に見えない制御文字（U+200E）が付いていた 5 駅（田贝・通新岭・华新など）が駅の点と照合できるようになり、位置が最大 28 m 正確になった。
- 読みの全駅点検（英語の公式駅名との突き合わせ）で見つかった誤り 3 件を修正: 广州 海涌路（chōng）、深圳 沙壆（bó）、深圳 深外高中の分かち書き。

## 検証結果（段階 2a・広州・深圳）

詳細は [reports/guangzhou_validation.md](reports/guangzhou_validation.md)、[reports/shenzhen_validation.md](reports/shenzhen_validation.md)。

- 広州: 路線 19、駅 317。全路線の駅数・駅名が Wikipedia と一致（上書き 2 件の後）。駅と線形の距離 150 m 超なし。**未確認 317**。
- 深圳: 路線 17、駅 351。全路線一致（8号線の莲塘は理由付きの注記）。150 m 超は福民（4・10号線の乗換駅）のみ。**未確認 351**。
- 開業前の駅の混入: いずれもなし。
- 確認用の駅一覧: `reports/guangzhou_verify_draft.csv`、`reports/shenzhen_verify_draft.csv`（主要エリアの 50 駅ずつ。Excel で開ける）。
  確認・修正したら、修正列を反映して `overrides/verified_<id>.csv`（付録 A と同じ列）として保存し、再ビルドする。
- 上海の回帰確認: 第1版と比べ、路線・駅・表記・読み・色・座標の差は 0（路線 ID の接頭辞と読みの入れ物の変更を除く）。

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
- 照合用（表示データには混ぜない）：中国語版 Wikipedia「上海地铁车站列表」「广州地铁车站列表」「深圳地铁车站列表」と各路線の駅一覧テンプレート、「港鐵車站列表」「香港輕鐵車站列表」「广深铁路」「广深港高速铁路」、「Module:Adjacent stations/…」（CC BY-SA）。
- 広東語の読み：pycantonese（粤拼）。
