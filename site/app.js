/* 地下鉄学習マップ — 表示ページ
 * 読むのは data/cities.json（路線網の一覧）と data/<id>.json（路線網ごとのデータ）だけ。
 * 路線網の追加は data/ にファイルを置き、cities.json に 1 行足すだけでよい。
 * cities.json の各行は region（地域）を持ち、同じ地域の路線網は同時に表示する。
 */
(() => {
  "use strict";

  const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  // 淡色（ラベルなし）: OpenFreeMap の Positron スタイルから文字・記号の層（symbol）を除いて描く。
  // 標準（ラベルあり）: OpenStreetMap 標準タイル。どちらも OSM 由来・API キー不要。
  const OFM_STYLE = "https://tiles.openfreemap.org/styles/positron";
  let plainStyle = null;
  const BASEMAPS = {
    plain: async () => {
      if (!plainStyle) {
        const st = await (await fetch(OFM_STYLE)).json();
        st.layers = st.layers.filter((l) => l.type !== "symbol");
        plainStyle = st;
      }
      return L.maplibreGL({
        style: plainStyle, interactive: false,
        attribution: '<a href="https://openfreemap.org" target="_blank">OpenFreeMap</a> '
          + '&copy; <a href="https://www.openmaptiles.org/" target="_blank">OpenMapTiles</a> ' + OSM_ATTR,
      });
    },
    osm: async () => L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: OSM_ATTR,
    }),
  };
  // 広東語の声調の早見表（仕様 11 章）。香港の路線網があるタブに出す
  const YUE_TONES = [
    ["1", "高く平ら", "˥"], ["2", "中から高へ上がる", "˧˥"], ["3", "中くらいで平ら", "˧"],
    ["4", "低く下がる", "˨˩"], ["5", "低から中へ上がる", "˨˧"], ["6", "低く平ら", "˨"],
  ];

  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { return localStorage.getItem("metro-map:" + k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("metro-map:" + k, v); } catch { /* 保存できなくても動く */ } },
  };
  const isTouch = window.matchMedia("(hover: none)").matches;
  // 駅名を常時表示し始める拡大率（本人の指定、2026-10-06）。操作の 1 段階（＋−ボタン 1 回・ホイール 1 目盛り）＝拡大率 0.5。
  //   地下鉄 13・高鉄 11.5・APM 14.5・輕鐵 14・電車と山頂纜車 15（停留所の間隔が短い）。
  //   タッチ端末（iPhone・iPad）は吹き出しをタップしないと見えないので、地下鉄・高鉄はさらに 0.5 広い範囲から。
  // 文字が重なる所では、高鉄・乗換駅を先に置き、重なる駅名は省く（拡大すると出る）。
  const APM_LINES = new Set(["gz_apm"]);
  const TOUCH_EARLY = isTouch ? 0.5 : 0;
  function labelMinZoom(st) {
    if (st.kind === "hsr") return 11.5 - TOUCH_EARLY;
    if (st.kind === "tram" || st.kind === "funicular") return 15;
    if (st.kind === "light_rail") return 14;
    if (st.lines.every((l) => APM_LINES.has(l))) return 14.5;
    return 13 - TOUCH_EARLY;
  }
  const LABEL_MIN_ZOOM_ANY = 11.5 - TOUCH_EARLY;

  // ---------------------------------------------------------------- 地図
  const map = L.map("map", { zoomControl: true, preferCanvas: true, minZoom: 7, maxZoom: 18, zoomSnap: 0.25, zoomDelta: 0.5 });
  map.attributionControl.setPrefix(false);
  window.metroMap = map;  // 開発者ツールからの確認用
  const renderer = L.canvas({ tolerance: isTouch ? 10 : 4 });
  map.createPane("labels").style.zIndex = 430;

  // 高鉄の駅は四角で描く（Canvas に四角の描き方を足す）
  L.Canvas.include({
    _updateSquareMarker(layer) {
      if (!this._drawing || layer._empty()) return;
      const p = layer._point, r = layer._radius, ctx = this._ctx;
      this._layers[layer._leaflet_id] = layer;
      ctx.beginPath();
      ctx.rect(p.x - r, p.y - r, r * 2, r * 2);
      this._fillStroke(ctx, layer);
    },
  });
  const SquareMarker = L.CircleMarker.extend({
    _updatePath() { this._renderer._updateSquareMarker(this); },
  });

  let base = null;
  async function setBasemap(key) {
    if (!BASEMAPS[key]) key = "plain";
    $("basemap").value = key;
    store.set("basemap", key);
    let layer;
    try {
      layer = await BASEMAPS[key]();
    } catch (err) {
      console.error(err);
      if (key !== "osm") return setBasemap("osm");  // 淡色地図が取れなければ標準地図で続ける
      return;
    }
    if (base) map.removeLayer(base);
    base = layer.addTo(map);
  }

  // ---------------------------------------------------------------- 状態
  let catalog = [];           // cities.json
  let region = null;          // 表示中の地域 id
  let nets = [];              // 表示中の地域の路線網データ（cities.json の順）
  let netOf = {};             // 路線 id → 路線網データ
  let lineById = {};
  let hidden = new Set();     // 非表示の路線 id（全地域共通で保存）
  let hiddenNets = new Set(); // 非表示の路線網 id
  let activeTab = null;       // 「表示する路線」のタブ（路線網 id）
  let lineLayers = {};        // 路線 id → L.LayerGroup
  let stationLayer = L.layerGroup();
  let labelLayer = L.layerGroup();
  let stationMarkers = [];    // { st, net, marker }
  let labelMode = store.get("label", "ja");
  let legendLang = store.get("legendLang", "orig");  // 英語の路線名がある路線網（香港）の凡例: orig＝粤文、en＝English
  // 所要時間（docs/travel-time-draft.md）
  let routing = null;         // routing-<地域>.json を経路計算用に整えたもの
  let stById = {};            // 駅 id → 駅（表示中の地域の全路線網）
  let timeLabels = store.get("times", "0") === "1";  // 駅間の所要時間ラベル
  let timeLayer = L.layerGroup();
  let routeMode = false;      // 乗車時間の検索中（駅をタップで出発・到着を選ぶ）
  let routeFrom = null;
  let routeResult = null;     // 表示中の経路 { from, to, legs, ride, xfer, cost }
  let routeResults = [];      // 経路の候補（タブ）
  let routeLayer = L.layerGroup();

  function loadSet(k) { try { return new Set(JSON.parse(store.get(k, "[]"))); } catch { return new Set(); } }
  hidden = loadSet("hidden");
  hiddenNets = loadSet("hiddenNets");
  function saveHidden() {
    store.set("hidden", JSON.stringify([...hidden]));
    store.set("hiddenNets", JSON.stringify([...hiddenNets]));
  }
  const lineVisible = (id) => !!netOf[id] && !hidden.has(id) && !hiddenNets.has(netOf[id].id);

  // ---------------------------------------------------------------- 表示部品
  function textColor(hex) {
    const n = parseInt(hex.slice(1), 16);
    const [r, g, b] = [(n >> 16) & 255, (n >> 8) & 255, n & 255].map((c) => {
      c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    });
    const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    return lum > 0.4 ? "#1f2328" : "#ffffff";
  }
  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }
  function badge(line) {
    return `<span class="badge" style="background:${line.color};color:${textColor(line.color)}">${esc(line.badge || line.ref)}</span>`;
  }
  // 粤拼の声調数字を上付きにする（tung4 → tung⁴）
  const SUP = { 1: "¹", 2: "²", 3: "³", 4: "⁴", 5: "⁵", 6: "⁶" };
  const supTones = (s) => s.replace(/([a-z])([1-6])\b/g, (_, a, d) => a + SUP[d]);

  // 吹き出し（仕様 3.3）。これ以外は出さない。
  //   普通話の駅: 原表記 ／ 日本漢字、ピンイン（カナ）、路線バッジ
  //   香港の駅  : 原表記 ／ 英語 ／ 日本漢字、普 ピンイン、粤 粤拼（カナ）、路線バッジ
  function tipHtml(st) {
    const sep = '<span class="sep">／</span>';
    const r = st.reading || {};
    const badges = `<div class="badges">${st.lines.map((id) => badge(lineById[id])).join("")}</div>`;
    if (r.yue) {
      const names = [st.name_orig, st.name_en, st.name_ja !== st.name_orig ? st.name_ja : null].filter(Boolean).map(esc).join(sep);
      return `<div class="tip-name">${names}</div>`
        + (r.cmn ? `<div class="tip-reading"><span class="lang">普</span>${esc(r.cmn.roman)}</div>` : "")
        + `<div class="tip-reading"><span class="lang">粤</span>${esc(supTones(r.yue.jyutping))}`
        + `${r.yue.kana ? `（${esc(r.yue.kana)}）` : ""}</div>` + badges;
    }
    const c = r.cmn || {};
    const nm2 = st.name_orig === st.name_ja ? esc(st.name_orig) : `${esc(st.name_orig)}${sep}${esc(st.name_ja)}`;  // 同じ字なら 1 回
    return `<div class="tip-name">${nm2}</div>`
      + `<div class="tip-reading">${esc(c.roman || "")}${c.kana ? `（${esc(c.kana)}）` : ""}</div>` + badges;
  }
  function lineWeight(z, mode) {
    const w = z <= 9 ? 1.5 : z <= 10 ? 2 : z <= 11 ? 2.5 : z <= 12 ? 3 : z <= 13 ? 4 : z <= 15 ? 5 : 6.5;
    return mode === "tram" || mode === "light_rail" ? Math.max(1.2, w * 0.6) : w;
  }
  function stationRadius(z, transfer, kind) {
    let r = z <= 10 ? 1.5 : z <= 11 ? 2 : z <= 12 ? 2.5 : z <= 13 ? 3.5 : z <= 15 ? 4.5 : 6;
    if (kind === "tram" || kind === "light_rail") r *= 0.65;
    if (kind === "hsr") r += 1.5;
    return transfer ? r + 2 : r;
  }
  function stationStyle(st, z) {
    const transfer = st.lines.length > 1;
    const vis = st.lines.filter(lineVisible);
    const color = lineById[vis[0] || st.lines[0]].color;
    const s = transfer || st.kind === "hsr"
      ? { color: "#3a3f45", weight: z >= 13 ? 2 : 1.5, fillColor: "#ffffff", fillOpacity: 1 }
      : { color: "#ffffff", weight: z >= 13 ? 1.5 : 1, fillColor: color, fillOpacity: 1 };
    s.radius = stationRadius(z, transfer, st.kind);
    s.opacity = 1;
    s.dashArray = null;
    return s;
  }

  // ---------------------------------------------------------------- 駅名の読み上げ（クリック・タップで自動）
  // ブラウザの音声合成（Web Speech API）。中国本土の駅と高鉄の駅は普通話、香港の駅（MTR・輕鐵・電車・山頂纜車）は広東語。
  // 音声は端末に入っているものを使う（iPhone・iPad は標準で普通話・広東語あり。PC の Chrome は Google の音声）。
  const SPEECH = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  let voices = [];
  const loadVoices = () => { voices = window.speechSynthesis.getVoices(); };
  if (SPEECH) {
    loadVoices();
    window.speechSynthesis.addEventListener?.("voiceschanged", loadVoices);
  }
  const VOICE_RULES = {
    yue: { lang: "zh-HK", pats: [/^zh[-_]HK/i, /^yue/i, /cantonese|粤|粵/i] },
    cmn: { lang: "zh-CN", pats: [/^zh[-_]CN/i, /^cmn/i, /mandarin|普通话|普通話/i] },
  };
  function pickVoice(kind) {
    for (const re of VOICE_RULES[kind].pats) {
      const v = voices.find((x) => re.test(x.lang) || re.test(x.name));
      if (v) return v;
    }
    return null;
  }
  function speak(st) {
    if (!SPEECH) return;
    const kind = st.kind !== "hsr" && st.reading && st.reading.yue ? "yue" : "cmn";
    const u = new SpeechSynthesisUtterance(st.name_orig.replace(/[()（）·・]/g, " "));
    u.lang = VOICE_RULES[kind].lang;
    const v = pickVoice(kind);
    if (v) u.voice = v;
    u.rate = 0.9;
    window.speechSynthesis.cancel();  // 前の駅の読み上げが残っていれば止める
    window.speechSynthesis.speak(u);
  }

  // ---------------------------------------------------------------- 地域の読み込み
  async function loadRegion(regionId, moveTo) {
    const entries = catalog.filter((c) => c.region === regionId);
    const [datas, rdata] = await Promise.all([
      Promise.all(entries.map(async (e) => {
        const res = await fetch("data/" + e.file, { cache: "no-cache" });
        if (!res.ok) throw new Error(`${e.file}: ${res.status}`);
        return res.json();
      })),
      // 所要時間のデータは無くても地図は動く
      fetch(`data/routing-${regionId}.json`, { cache: "no-cache" }).then((r) => (r.ok ? r.json() : null)).catch(() => null),
    ]);
    clearLayers();  // 前の地域の表示を先に片付ける（移動中の再描画で古い路線を参照しないように）
    clearRoute();
    region = regionId;
    nets = datas;
    netOf = {};
    lineById = {};
    stById = {};
    for (const n of nets) for (const l of n.lines) { netOf[l.id] = n; lineById[l.id] = l; }
    for (const n of nets) for (const s of n.stations) stById[s.id] = s;
    routing = rdata ? prepareRouting(rdata) : null;
    $("btn-route").disabled = !routing;
    $("btn-times").disabled = !routing;
    if (routeMode) { if (routing) renderRoutePanel(); else setRouteMode(false); }
    store.set("region", region);
    document.title = `${entries[0].region_name_ja} — 地下鉄学習マップ`;
    $("region").value = region;
    const mv = $("move");
    mv.innerHTML = "";
    for (const n of nets) mv.add(new Option(n.name_ja, n.id));
    const target = nets.find((n) => n.id === moveTo) || nets[0];
    mv.value = target.id;
    if (!nets.some((n) => n.id === activeTab)) activeTab = target.id;
    moveToNet(target.id);  // 先に表示範囲を決める（ラベル描画が地図の範囲を使うため）
    build();
  }

  function clearLayers() {
    Object.values(lineLayers).forEach((g) => map.removeLayer(g));
    map.removeLayer(stationLayer);
    map.removeLayer(labelLayer);
    map.removeLayer(timeLayer);
    lineLayers = {};
    stationLayer = L.layerGroup();
    labelLayer = L.layerGroup();
    timeLayer = L.layerGroup();
    stationMarkers = [];
  }

  function build() {
    clearLayers();
    const z = map.getZoom() || 12;

    // 路線（白い縁取り＋路線色）。全路線網の線を先に描き、駅をその上に描く
    for (const net of nets) {
      for (const line of net.lines) {
        const g = L.layerGroup();
        for (const casing of [true, false]) {
          for (const pl of line.geometry) {
            g.addLayer(L.polyline(pl, {
              renderer, interactive: false, lineCap: "round", lineJoin: "round", _casing: casing, _mode: line.mode,
              color: casing ? "#ffffff" : line.color, opacity: casing ? 0.85 : 1,
              weight: lineWeight(z, line.mode) + (casing ? 2.5 : 0),
            }));
          }
        }
        lineLayers[line.id] = g;
      }
    }
    for (const net of nets) {
      const sorted = [...net.stations].sort((a, b) => a.lines.length - b.lines.length);  // 乗換駅を上に
      for (const st of sorted) {
        const Marker = st.kind === "hsr" ? SquareMarker : L.CircleMarker;
        const m = new Marker([st.lat, st.lon], { renderer, ...stationStyle(st, z) });
        m.bindTooltip(() => tipHtml(st), { className: "station-tip", direction: "top", offset: [0, -6], opacity: 1 });
        if (isTouch) m.off("mouseover mouseout");
        m.on("click", (e) => {
          L.DomEvent.stopPropagation(e);
          if (routeMode) { m.closeTooltip(); pickStation(st); return; }  // 乗車時間の検索中は駅を選ぶ（読み上げない）
          if (isTouch) {
            // タッチ端末: タップで表示、別の場所をタップで閉じる
            stationMarkers.forEach((o) => o.marker !== m && o.marker.closeTooltip());
            m.openTooltip();
          }
          speak(st);
        });
        stationMarkers.push({ st, net, marker: m });
      }
    }
    stationLayer.addTo(map);
    labelLayer.addTo(map);
    timeLayer.addTo(map);
    renderLegend();
    refresh();
  }

  // 路線の表示切替・ズームに応じた太さ・ラベルを反映
  function refresh() {
    if (!nets.length) return;
    const z = map.getZoom();
    const shown = !!(routeResult && routeResult.legs);
    const marked = shown || !!routeFrom;  // 出発駅（と到着駅）の強調
    const dim = shown ? 0.4 : 1;  // 経路を表示中は、ほかの路線を薄くする
    for (const [id, g] of Object.entries(lineLayers)) {
      const on = lineVisible(id);
      if (on && !map.hasLayer(g)) g.addTo(map);
      if (!on && map.hasLayer(g)) map.removeLayer(g);
      if (on) g.eachLayer((pl) => pl.setStyle({
        weight: lineWeight(z, pl.options._mode) + (pl.options._casing ? 2.5 : 0),
        opacity: (pl.options._casing ? 0.85 : 1) * dim,
      }));
    }
    // 経路は路線の上、駅は線より後に描く（Canvas は追加順に重なる）
    map.removeLayer(routeLayer);
    if (marked) { drawRoute(); routeLayer.addTo(map); }
    map.removeLayer(stationLayer);
    for (const { st, marker } of stationMarkers) {
      const visible = st.lines.some(lineVisible);
      if (visible && !stationLayer.hasLayer(marker)) stationLayer.addLayer(marker);
      if (!visible && stationLayer.hasLayer(marker)) { marker.closeTooltip(); stationLayer.removeLayer(marker); }
      if (visible) marker.setStyle(stationStyle(st, z));
    }
    stationLayer.addTo(map);
    renderLabels();
    renderTimeLabels();
  }

  function labelText(st) {
    if (labelMode === "orig") return esc(st.name_orig);
    if (labelMode === "en") return esc(st.name_en && st.reading && st.reading.yue ? st.name_en : st.name_orig);
    // 両方: 現地の漢字（原表記）を上、日本漢字を下（同じ字なら 1 回）
    if (labelMode === "both") return st.name_orig === st.name_ja ? esc(st.name_orig) : `${esc(st.name_orig)}<small>${esc(st.name_ja)}</small>`;
    return esc(st.name_ja);
  }
  // ラベルの文字の大きさ（style.css の --label-size。画面の幅で変わる）と、文字の幅の見積もり
  const measureCtx = document.createElement("canvas").getContext("2d");
  const isMinor = (st) => ["tram", "light_rail", "funicular"].includes(st.kind);  // 1 割小さい文字（style.css の .minor）
  function labelBox(st, px) {
    if (isMinor(st)) px *= 0.85;
    const font = getComputedStyle(document.body).fontFamily;
    const w = (t, size, weight) => { measureCtx.font = `${weight} ${size}px ${font}`; return measureCtx.measureText(t).width; };
    let lines;
    if (labelMode === "both" && st.name_orig !== st.name_ja) lines = [[st.name_orig, px, 600], [st.name_ja, px * 0.9, 400]];
    else if (labelMode === "orig") lines = [[st.name_orig, px, 600]];
    else if (labelMode === "en") lines = [[st.name_en && st.reading && st.reading.yue ? st.name_en : st.name_orig, px, 600]];
    else lines = [[st.name_ja, px, 600]];
    return { w: Math.max(...lines.map(([t, s, wt]) => w(t, s, wt))) + 4, h: lines.reduce((a, [, s]) => a + s * 1.2, 0) };
  }
  // 駅名の置き場所の候補（駅の点からのずれ。r＝その駅の点の半径）。上から順に、空いている所に置く
  const PLACES = [
    (w, h, r) => [r + 3, -h / 2],              // 右
    (w, h, r) => [r * 0.5, -h - r * 0.7 - 1],  // 右上
    (w, h, r) => [r * 0.5, r * 0.7 + 1],       // 右下
    (w, h, r) => [-w - r - 3, -h / 2],         // 左
    (w, h, r) => [-w - r * 0.5, -h - r * 0.7 - 1],  // 左上
    (w, h, r) => [-w - r * 0.5, r * 0.7 + 1],       // 左下
  ];
  function renderLabels() {
    labelLayer.clearLayers();
    const z = map.getZoom();
    if (!nets.length || labelMode === "none" || z < LABEL_MIN_ZOOM_ANY) return;
    const bounds = map.getBounds().pad(0.2);
    const px = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--label-size")) || 12;
    const rank = (st) => (st.kind === "hsr" ? 0 : st.lines.length > 1 ? 1 : st.kind === "metro" ? 2 : 3);
    const cands = stationMarkers.map((o) => o.st)
      .filter((st) => st.lines.some(lineVisible) && z >= labelMinZoom(st) && bounds.contains([st.lat, st.lon]))
      .sort((a, b) => rank(a) - rank(b) || b.lines.length - a.lines.length);
    // 画面に出ている駅の点も、駅名をかぶせない場所として先に置く
    const placed = [];
    const radius = (st) => stationRadius(z, st.lines.length > 1, st.kind);
    for (const { st } of stationMarkers) {
      if (!st.lines.some(lineVisible) || !bounds.contains([st.lat, st.lon])) continue;
      const p = map.latLngToLayerPoint([st.lat, st.lon]);
      const r = radius(st) + 1;
      placed.push({ x0: p.x - r, x1: p.x + r, y0: p.y - r, y1: p.y + r, own: st.id });
    }
    const hit = (box, id) => placed.some((b) => b.own !== id && box.x0 < b.x1 && b.x0 < box.x1 && box.y0 < b.y1 && b.y0 < box.y1);
    for (const st of cands) {
      const p = map.latLngToLayerPoint([st.lat, st.lon]);
      const { w, h } = labelBox(st, px);
      const r = radius(st);
      let at = null;
      for (const off of PLACES) {
        const [dx, dy] = off(w, h, r);
        const box = { x0: p.x + dx, x1: p.x + dx + w, y0: p.y + dy, y1: p.y + dy + h };
        if (!hit(box, st.id)) { at = [dx, dy]; placed.push(box); break; }
      }
      if (!at) continue;  // どこに置いても重なるなら省く（拡大すると出る）
      const icon = L.divIcon({ className: "", iconSize: [0, 0],
        html: `<div class="station-label${isMinor(st) ? " minor" : ""}" style="transform:translate(${at[0].toFixed(1)}px,${at[1].toFixed(1)}px)">${labelText(st)}</div>` });
      labelLayer.addLayer(L.marker([st.lat, st.lon], { icon, pane: "labels", interactive: false, keyboard: false }));
    }
  }

  // ---------------------------------------------------------------- 「表示する路線」パネル
  function renderLegend() {
    const tabs = $("legend-tabs");
    tabs.innerHTML = "";
    tabs.hidden = nets.length < 2;
    for (const n of nets) {
      const b = document.createElement("button");
      b.type = "button";
      b.role = "tab";
      b.textContent = n.name_ja;
      b.dataset.tab = n.id;
      b.setAttribute("aria-selected", String(n.id === activeTab));
      if (hiddenNets.has(n.id)) b.classList.add("off");
      tabs.appendChild(b);
    }
    const net = nets.find((n) => n.id === activeTab) || nets[0];
    const body = $("legend-body");
    const netOn = !hiddenNets.has(net.id);
    let html = `<div class="legend-head">
        <label class="net-toggle"><input type="checkbox" data-net="${esc(net.id)}" ${netOn ? "checked" : ""}>この路線網を表示</label>
        <span class="legend-actions"><button type="button" data-all="on">全表示</button><button type="button" data-all="off">全非表示</button></span>
      </div>`;
    if (net.lines.some((l) => l.name_en)) {  // 路線名の表記の切替（路線名の一覧の最上部）
      html += `<div class="legend-lang" role="group" aria-label="路線名の表記">`
        + `<button type="button" data-lang="orig" aria-pressed="${legendLang !== "en"}">粤文</button>`
        + `<button type="button" data-lang="en" aria-pressed="${legendLang === "en"}">English</button></div>`;
    }
    const groups = net.groups && net.groups.length ? net.groups : [{ id: null, name: null }];
    for (const g of groups) {
      const lines = net.lines.filter((l) => (g.id ? l.group === g.id : true));
      if (!lines.length) continue;
      if (g.name) html += `<div class="legend-group">${esc(g.name)}</div>`;
      // 英語の路線名がある路線網（香港）は、粤文（原表記）と English を切り替えて 1 行で出す
      const withEn = lines.some((l) => l.name_en);
      const lname = (l) => (withEn ? (legendLang === "en" && l.name_en ? l.name_en : l.name_orig) : l.name_ja);
      html += `<ul class="legend-list${withEn ? " with-en" : ""}${netOn ? "" : " disabled"}">` + lines.map((line) =>
        `<li><label><input type="checkbox" ${hidden.has(line.id) ? "" : "checked"} data-line="${esc(line.id)}">`
        + `<span class="swatch" style="background:${line.color}"></span>${badge(line)}`
        + `<span class="lname">${esc(lname(line))}</span>`
        + `</label></li>`).join("") + "</ul>";
    }
    if ((net.reading_langs || []).includes("yue")) {
      html += `<details class="tones"><summary>広東語の声調（粤拼の数字）</summary><table>`
        + YUE_TONES.map(([d, t, c]) => `<tr><td class="tone-d">${d}</td><td>${t}</td><td class="tone-c">${c}</td></tr>`).join("")
        + `</table><p>1〜3 は高め、4〜6 は低め。2 と 5 は上がる、4 だけ下がる、1・3・6 は平ら。</p></details>`;
    }
    body.innerHTML = html;
  }

  // ---------------------------------------------------------------- 所要時間（駅間ラベル・乗車時間の検索）
  // データは tools/build_routing.py が作る data/routing-<地域>.json。
  // 時間は乗車時間だけ（乗換の徒歩・待ちは足さない）。経路を比べるときだけ乗換 1 回を 5 分とみなす（本人の決定）。
  const TRANSFER_PENALTY = 5;
  // 高鉄の列車どうしの乗り継ぎ（同じ駅で別の高鉄に乗る）は、本数が少なく待ちが長いので、比べるときだけ 20 分とみなす。
  // 直通列車がある組（例: 広州東 → 香港西九龍）で、別の列車の時間をつないだ乗り継ぎの経路が選ばれないように
  const HSR_TRANSFER_PENALTY = 20;
  const TIME_LABEL_MIN_ZOOM = 13;
  const NO_TIME_LABEL = new Set(["tram", "light_rail", "funicular"]);  // 駅間が短く邪魔なので出さない

  function prepareRouting(d) {
    const R = { d, adj: new Map(), linesAt: new Map(), walksAt: new Map(), lineAdj: new Map(), odLines: new Set(), through: new Set(), segKey: new Map() };
    const add = (m, k, v) => { if (!m.has(k)) m.set(k, []); m.get(k).push(v); };
    const addLine = (s, l) => { if (!R.linesAt.has(s)) R.linesAt.set(s, new Set()); R.linesAt.get(s).add(l); };
    for (const [l] of d.od) R.odLines.add(l);
    const odPair = new Set(d.od.map(([l, a, b]) => `${l}|${a}|${b}`));
    for (const [l, a, b, t] of d.segs) {
      if (!lineById[l]) continue;
      R.segKey.set(`${l}|${a}|${b}`, t);
      R.segKey.set(`${l}|${b}|${a}`, t);
      if (!R.lineAdj.has(l)) R.lineAdj.set(l, new Map());
      const la = R.lineAdj.get(l);
      add(la, a, b); add(la, b, a);
      addLine(a, l); addLine(b, l);
      // 高鉄は駅の組ごとの値（od）を使い、無い向きだけ隣の駅との値で補う
      if (!odPair.has(`${l}|${a}|${b}`)) add(R.adj, a, { to: b, line: l, t });
      if (!odPair.has(`${l}|${b}|${a}`)) add(R.adj, b, { to: a, line: l, t });
    }
    for (const [l, a, b, t] of d.od) {
      if (!lineById[l]) continue;
      add(R.adj, a, { to: b, line: l, t });
      addLine(a, l); addLine(b, l);
    }
    for (const [a, b, kind] of d.walks) { add(R.walksAt, a, { to: b, kind }); add(R.walksAt, b, { to: a, kind }); }
    for (const x of d.dirs.through || []) { R.through.add(`${x.line}|${x.to_line}|${x.terminal}`); R.through.add(`${x.to_line}|${x.line}|${x.terminal}`); }
    return R;
  }

  // 最短経路（状態＝駅と乗っている路線）。費用＝乗車時間＋乗換回数×5 分
  function findRoute(from, to, banned = null) {
    const R = routing;
    const ok = (l) => !banned || !banned.has(l.replace("~", ""));  // 別の経路を探すときに使わない路線
    const best = new Map(), prev = new Map();
    const heap = [];
    const push = (x) => {
      heap.push(x);
      let i = heap.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (heap[p].cost <= heap[i].cost) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p; }
    };
    const pop = () => {
      const top = heap[0], last = heap.pop();
      if (heap.length) {
        heap[0] = last;
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1;
          let m = i;
          if (l < heap.length && heap[l].cost < heap[m].cost) m = l;
          if (r < heap.length && heap[r].cost < heap[m].cost) m = r;
          if (m === i) break;
          [heap[m], heap[i]] = [heap[i], heap[m]]; i = m;
        }
      }
      return top;
    };
    const relax = (st, line, cost, ride, xfer, from_, how) => {
      const k = st + "|" + line;
      if (cost >= (best.get(k) ?? Infinity)) return;
      best.set(k, cost);
      prev.set(k, { from: from_, how });
      push({ st, line, cost, ride, xfer, k });
    };
    for (const l of R.linesAt.get(from) || []) if (ok(l)) relax(from, l, 0, 0, 0, null, null);
    let goal = null;
    while (heap.length) {
      const s = pop();
      if (s.cost > best.get(s.k)) continue;
      if (s.st === to) { goal = s; break; }
      for (const e of R.adj.get(s.st) || []) {
        if (e.line !== s.line) continue;
        // 高鉄は駅の組ごとに 1 本の列車。降りた状態（路線 id＋「~」）にして、続けて乗るには乗換（別の列車）を要する
        const next = R.odLines.has(e.line) ? e.line + "~" : s.line;
        relax(e.to, next, s.cost + e.t, s.ride + e.t, s.xfer, s.k, { type: "ride", t: e.t });
      }
      for (const l of R.linesAt.get(s.st) || []) {
        if (l === s.line || !ok(l)) continue;
        const thr = R.through.has(`${s.line}|${l}|${s.st}`);  // 直通運転（深圳 2号線 ↔ 8号線）は乗換に数えない
        const pen = thr ? 0 : (s.line.endsWith("~") && R.odLines.has(l) ? HSR_TRANSFER_PENALTY : TRANSFER_PENALTY);
        relax(s.st, l, s.cost + pen, s.ride, s.xfer + (thr ? 0 : 1), s.k, { type: thr ? "through" : "change" });
      }
      for (const w of R.walksAt.get(s.st) || []) {
        for (const l of R.linesAt.get(w.to) || []) {
          if (ok(l)) relax(w.to, l, s.cost + TRANSFER_PENALTY, s.ride, s.xfer + 1, s.k, { type: "walk", kind: w.kind });
        }
      }
    }
    if (!goal) return null;
    // たどり直して、路線ごとの区間（leg）にまとめる
    const steps = [];
    for (let k = goal.k; k; k = prev.get(k).from) steps.push({ k, how: prev.get(k).how });
    steps.reverse();
    const legs = [];
    let cur = null;
    for (const { k, how } of steps) {
      const [st, line0] = k.split("|");
      const line = line0.replace("~", "");
      if (!how) { cur = { line, stations: [st], t: 0, before: null }; continue; }
      if (how.type === "ride") { cur.stations.push(st); cur.t += how.t; continue; }
      if (cur.stations.length > 1) legs.push(cur);
      cur = { line, stations: [st], t: 0, before: how.type === "walk" ? { type: "walk", kind: how.kind, from: cur.stations[cur.stations.length - 1] } : { type: how.type } };
    }
    if (cur && cur.stations.length > 1) legs.push(cur);
    // 最後が徒歩（例: 尖東 → 尖沙咀）なら、到着駅までの徒歩として残す
    const tail = cur && cur.stations.length === 1 && cur.before && cur.before.type === "walk" ? { ...cur.before, to: cur.stations[0] } : null;
    if (legs.length && legs[0].before && legs[0].before.type !== "walk") legs[0].before = null;
    return { from, to, legs, tail, ride: goal.ride, cost: goal.cost, xfer: legs.filter((l) => l.before && l.before.type !== "through").length };
  }

  // 経路の候補（最大 5）。最短の経路で使った路線を 1 本ずつ（3 本まで）使わないことにして探し直し、違う経路を集める。
  // 乗る駅・降りる駅の並びが同じ経路（線路を共用する別路線。例: 九龍→香港の東涌線と機場快線）は 1 つにまとめ、速い方を残す。
  // 費用（乗車時間＋乗換 1 回 5 分）の短い順。明らかに劣る経路は出さない:
  //   - 最短の費用の 1.25 倍＋10 分を超える
  //   - ほかの候補より乗車時間も乗換回数も多い
  const MAX_ROUTES = 5;
  function findRoutes(from, to) {
    const sig = (r) => r.legs.map((l) => `${l.stations[0]}>${l.stations[l.stations.length - 1]}`).join("|") + (r.tail ? "|walk" : "");
    const found = new Map(), tried = new Set(), queue = [[]];
    let runs = 0;
    while (queue.length && runs < 60) {
      const bans = queue.shift();
      const key = [...bans].sort().join(",");
      if (tried.has(key)) continue;
      tried.add(key);
      runs++;
      const r = findRoute(from, to, bans.length ? new Set(bans) : null);
      if (!r) continue;
      const k = sig(r);
      if (!found.has(k) || r.cost < found.get(k).cost) found.set(k, r);
      if (bans.length < 3) for (const l of new Set(r.legs.map((x) => x.line))) queue.push([...bans, l]);
    }
    // 同じ高鉄・鉄道の路線で別の列車に乗り継ぐ（例: 広深線を平湖で乗り継ぐ）のは不自然なので除く（最短の経路は残す）
    const sameLineHop = (r) => r.legs.some((l, i) => i > 0 && l.line === r.legs[i - 1].line);
    let list = [...found.values()].sort((a, b) => a.cost - b.cost);
    if (!list.length) return [];
    list = [list[0], ...list.slice(1).filter((r) => !sameLineHop(r))];
    const limit = list[0].cost * 1.25 + 10;
    list = list.filter((r) => r.cost <= limit);
    list = list.filter((r) => !list.some((o) => o !== r && o.ride < r.ride && o.xfer < r.xfer));
    return list.slice(0, MAX_ROUTES);
  }

  // ---- 「●●方面」（docs/direction-labels-draft.md）
  const nm = (id) => { const s = stById[id]; return s.name_orig === s.name_ja ? s.name_orig : `${s.name_orig}/${s.name_ja}`; };
  // 路線の上で、u → v と進んだ先にある終着駅（支線の先も含む）
  function forwardTerminals(line, u, v) {
    const adj = routing.lineAdj.get(line);
    if (!adj) return [v];
    const seen = new Set([u, v]), stack = [v], out = [];
    while (stack.length) {
      const x = stack.pop();
      const nb = adj.get(x) || [];
      if (nb.length === 1 && x !== u) out.push(x);
      for (const y of nb) if (!seen.has(y)) { seen.add(y); stack.push(y); }
    }
    return out.length ? out : [v];
  }
  function ahead(line, u, v, target) {  // u → v と進んだ先（v を含む）に target があるか
    if (v === target) return true;
    const adj = routing.lineAdj.get(line);
    const seen = new Set([u, v]), stack = [v];
    while (stack.length) {
      const x = stack.pop();
      for (const y of adj.get(x) || []) {
        if (y === target) return true;
        if (!seen.has(y)) { seen.add(y); stack.push(y); }
      }
    }
    return false;
  }
  const lineOrder = (line) => lineById[line].stations;  // 駅の並び（支線の無い高鉄・環状線の向きの判定に使う）
  function dirLabel(leg) {
    const D = routing.d.dirs, line = leg.line, sts = leg.stations;
    if ((D.none || []).includes(line)) return "";
    const s0 = sts[0], s1 = sts[1], u = sts[sts.length - 2], v = sts[sts.length - 1];
    const loop = (D.loop || {})[line];
    if (loop) {
      const order = lineById[line].stations, n = order.length;
      const i0 = order.indexOf(s0), i1 = order.indexOf(s1);
      const step = (i1 - i0 + n) % n === 1 ? 1 : -1;
      const cw = (step === 1) === (loop.order === "cw");
      const [cn, ja] = cw ? loop.cw : loop.ccw;
      let via = null;
      for (let k = 1; k < n; k++) {
        const x = order[(((i0 + step * k) % n) + n) % n];
        if (stById[x] && stById[x].lines.length > 1) { via = x; break; }
      }
      return `${cn}/${ja}` + (via ? `（${nm(via)}経由）` : "");
    }
    const tram = D.tram;
    if (tram && tram.line === line) {
      if (tram.branch_stations.includes(v) && !tram.branch_stations.includes(s0)) return `${nm(tram.branch)}方面`;
      return `${nm(stById[v].lon >= stById[s0].lon ? tram.east : tram.west)}方面`;
    }
    let terms;
    if (routing.odLines.has(line)) {  // 高鉄は駅の並びの向きで決める（区間は途中駅を飛ばすことがある）
      const order = lineOrder(line);
      terms = [order.indexOf(v) > order.indexOf(s0) ? order[order.length - 1] : order[0]];
    } else {
      terms = forwardTerminals(line, u, v);
    }
    const isOd = routing.odLines.has(line);
    const shown = terms.map((t) => {
      const th = (D.through || []).find((x) => x.line === line && x.terminal === t);
      if (th) return th.show;
      const rp = (D.replace || []).find((x) => x.line === line && x.terminal === t);
      // 置き換える駅（例: 機場）がまだ先にあるときだけ置き換える（機場から博覽館へ乗るときは博覽館）
      if (rp && rp.show !== s0 && (isOd || ahead(line, s0, s1, rp.show))) return rp.show;
      return t;
    });
    let via = "";
    if (terms.length === 1) {
      const vi = (D.via || []).find((x) => x.line === line && x.terminal === terms[0]);
      if (vi && vi.via !== s0 && ahead(line, s0, s1, vi.via)) via = `（${nm(vi.via)}経由）`;
    }
    return [...new Set(shown)].map(nm).join("・") + "方面" + via;
  }

  // ---- 経路の強調表示
  function segPath(line, a, b) {
    const p = routing.d.paths[`${line}|${a}|${b}`];
    if (p) return p;
    const q = routing.d.paths[`${line}|${b}|${a}`];
    if (q) return [...q].reverse();
    return [[stById[a].lat, stById[a].lon], [stById[b].lat, stById[b].lon]];
  }
  function legPath(leg) {
    const pts = [];
    let sts = leg.stations;
    if (routing.odLines.has(leg.line)) {  // 高鉄の駅の組は、途中駅を補ってから線路の形をつなぐ
      const order = lineOrder(leg.line), full = [];
      for (let i = 0; i < sts.length - 1; i++) {
        const a = order.indexOf(sts[i]), b = order.indexOf(sts[i + 1]);
        const seg = a <= b ? order.slice(a, b + 1) : order.slice(b, a + 1).reverse();
        full.push(...(full.length ? seg.slice(1) : seg));
      }
      if (full.length >= 2) sts = full;
    }
    for (let i = 0; i < sts.length - 1; i++) {
      const p = segPath(leg.line, sts[i], sts[i + 1]);
      pts.push(...(pts.length ? p.slice(1) : p));
    }
    return pts;
  }
  function drawRoute() {
    routeLayer.clearLayers();
    const z = map.getZoom();
    // 出発駅＝青、到着駅＝赤を、ふわっとした輪で強調（駅の点はその上に重なる）
    const halo = (id, color) => {
      const s = stById[id];
      if (!s) return;
      for (const [r, op] of [[24, 0.10], [17, 0.18]]) {
        routeLayer.addLayer(L.circleMarker([s.lat, s.lon], { renderer, interactive: false, radius: r, stroke: false, fillColor: color, fillOpacity: op }));
      }
      routeLayer.addLayer(L.circleMarker([s.lat, s.lon], { renderer, interactive: false, radius: 11, color, weight: 3, opacity: 0.85, fill: false }));
    };
    const fromId = routeResult ? routeResult.from : routeFrom;
    if (!routeResult || !routeResult.legs) { halo(fromId, "#0969da"); if (routeResult) halo(routeResult.to, "#cf222e"); return; }
    for (const leg of routeResult.legs) {
      const pts = legPath(leg), line = lineById[leg.line], w = lineWeight(z, "subway") + 3;
      routeLayer.addLayer(L.polyline(pts, { renderer, interactive: false, color: "#ffffff", weight: w + 4, opacity: 1, lineCap: "round", lineJoin: "round" }));
      routeLayer.addLayer(L.polyline(pts, { renderer, interactive: false, color: line.color, weight: w, opacity: 1, lineCap: "round", lineJoin: "round" }));
      if (leg.before && leg.before.type === "walk") {
        const a = stById[leg.before.from], b = stById[leg.stations[0]];
        routeLayer.addLayer(L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { renderer, interactive: false, color: "#59636e", weight: 3, dashArray: "4 5" }));
      }
    }
    if (routeResult.tail) {
      const a = stById[routeResult.tail.from], b = stById[routeResult.tail.to];
      routeLayer.addLayer(L.polyline([[a.lat, a.lon], [b.lat, b.lon]], { renderer, interactive: false, color: "#59636e", weight: 3, dashArray: "4 5" }));
    }
    halo(routeResult.from, "#0969da");
    halo(routeResult.to, "#cf222e");
  }

  // ---- パネル
  function renderRoutePanel() {
    const body = $("route-body");
    if (!routeFrom && !routeResult) {
      body.innerHTML = `<p class="route-hint">出発駅を地図でタップしてください。</p>`;
      return;
    }
    if (!routeResult) {
      body.innerHTML = `<p>出発: <b>${esc(nm(routeFrom))}</b></p><p class="route-hint">到着駅をタップしてください。</p>`;
      return;
    }
    const r = routeResult;
    if (!r.legs) {
      body.innerHTML = `<p class="route-od">${esc(nm(r.from))} → ${esc(nm(r.to))}</p><p>経路が見つかりませんでした。</p>`
        + `<p class="route-hint">別の出発駅をタップすると、続けて調べられます。</p>`;
      return;
    }
    if (!r.legs.length && r.tail) {  // 乗らずに歩いて行ける組（例: 尖沙咀 ↔ 尖東）
      body.innerHTML = `<div class="route-od">${esc(nm(r.from))} → ${esc(nm(r.to))}</div><p>乗車せず、徒歩で乗り換えられる駅です。</p>`;
      return;
    }
    let html = `<div class="route-od">${esc(nm(r.from))} → ${esc(nm(r.to))}</div>`;
    if (routeResults.length > 1) {  // 経路の候補のタブ（費用の短い順）
      html += `<div class="route-tabs" role="tablist">` + routeResults.map((x, i) =>
        `<button type="button" role="tab" data-route="${i}" aria-selected="${x === r}">`
        + `<span class="rt-n">${i + 1}</span>${Math.max(1, Math.round(x.ride))}分<span class="rt-x">乗換${x.xfer}</span></button>`).join("") + `</div>`;
    }
    html += `<div class="route-total">約 <b>${Math.max(1, Math.round(r.ride))}</b> 分（乗車時間）・乗換 ${r.xfer} 回</div><ul class="route-legs">`;
    for (const leg of r.legs) {
      const b = leg.before;
      if (b && b.type === "walk") {
        html += `<li class="route-xfer${b.kind === "border" ? " border" : ""}">${b.kind === "border" ? "出入境あり（手続きの時間は含まず）" : "徒歩で乗換"}`
          + `：${esc(nm(b.from))} → ${esc(nm(leg.stations[0]))}</li>`;
      } else if (b && b.type === "through") {
        html += `<li class="route-xfer">そのまま直通</li>`;
      } else if (b) {
        html += `<li class="route-xfer">乗換（${esc(nm(leg.stations[0]))}）</li>`;
      }
      const line = lineById[leg.line], dir = dirLabel(leg);
      const st0 = leg.stations[0], st1 = leg.stations[leg.stations.length - 1];
      const hk = stById[st0].id.startsWith("hsr_") && [st0, st1].some((x) => /西九龍/.test(stById[x].name_orig)) && ![st0, st1].every((x) => /西九龍/.test(stById[x].name_orig));
      html += `<li class="route-leg" style="border-left-color:${line.color}">`
        + `<div class="leg-line">${badge(line)}<span>${esc(line.name_ja)}</span>${dir ? `<span class="leg-dir">${esc(dir)}</span>` : ""}</div>`
        + `<div class="leg-st"><span class="leg-min">${Math.max(1, Math.round(leg.t))} 分</span>${esc(nm(st0))} → ${esc(nm(st1))}`
        + `${leg.stations.length > 2 ? `<span class="route-hint">（${leg.stations.length - 1} 駅）</span>` : ""}</div>`
        + (hk ? `<div class="route-xfer border">出入境あり（西九龍駅で手続き。時間は含まず）</div>` : "")
        + `</li>`;
    }
    if (r.tail) {
      html += `<li class="route-xfer${r.tail.kind === "border" ? " border" : ""}">${r.tail.kind === "border" ? "出入境あり（手続きの時間は含まず）" : "徒歩"}`
        + `：${esc(nm(r.tail.from))} → ${esc(nm(r.tail.to))}</li>`;
    }
    const hsr = r.legs.some((l) => routing.odLines.has(l.line));
    html += `</ul><p class="route-note">乗車時間の推定（乗換の徒歩・待ち時間は含まず）。${hsr ? "高鉄は列車により異なる。" : ""}</p>`;
    body.innerHTML = html;
  }
  function pickStation(st) {
    if (!routing) return;
    if (!routeFrom || routeResult) {  // 1 回目、または結果を出したあと → 新しい出発駅
      routeFrom = st.id;
      routeResult = null;
      renderRoutePanel();
      refresh();
      return;
    }
    if (st.id === routeFrom) return;
    routeResults = findRoutes(routeFrom, st.id);
    const r = routeResults[0] || null;
    routeResult = r || { from: routeFrom, to: st.id, legs: null };
    renderRoutePanel();
    refresh();
    if (r) fitRoute(r);
  }
  function fitRoute(r) {  // 経路が画面に収まっていなければ合わせる
    const b = L.latLngBounds([]);
    for (const leg of r.legs) for (const p of legPath(leg)) b.extend(p);
    for (const id of [r.from, r.to]) b.extend([stById[id].lat, stById[id].lon]);
    if (b.isValid() && !map.getBounds().contains(b)) map.fitBounds(b, { padding: [40, 40] });
  }
  function clearRoute() {
    routeFrom = null;
    routeResult = null;
    routeResults = [];
    routeLayer.clearLayers();
    map.removeLayer(routeLayer);
  }
  function setRouteMode(on) {
    routeMode = on && !!routing;
    $("route").hidden = !routeMode;
    $("btn-route").setAttribute("aria-pressed", String(routeMode));
    map.getContainer().classList.toggle("picking", routeMode);
    if (routeMode) {
      if (window.matchMedia("(max-width: 640px)").matches && !$("legend").hidden) $("btn-legend").click();  // 狭い画面では凡例と重なるので閉じる
      renderRoutePanel();
    } else {
      clearRoute();
    }
    refresh();
  }

  // ---- 駅間の所要時間ラベル
  function midpoint(pts) {
    let total = 0;
    const seg = [];
    for (let i = 0; i < pts.length - 1; i++) { const d = map.distance(pts[i], pts[i + 1]); seg.push(d); total += d; }
    let acc = 0;
    for (let i = 0; i < seg.length; i++) {
      if (acc + seg[i] >= total / 2) {
        const f = seg[i] ? (total / 2 - acc) / seg[i] : 0;
        return [pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f];
      }
      acc += seg[i];
    }
    return pts[0];
  }
  function renderTimeLabels() {
    timeLayer.clearLayers();
    $("btn-times").setAttribute("aria-pressed", String(timeLabels));
    if (!routing || !timeLabels || map.getZoom() < TIME_LABEL_MIN_ZOOM) return;
    const bounds = map.getBounds().pad(0.1);
    const done = new Set();
    for (const [l, a, b, t] of routing.d.segs) {
      const line = lineById[l];
      if (!line || NO_TIME_LABEL.has(line.mode) || !lineVisible(l)) continue;
      const key = a < b ? a + "|" + b : b + "|" + a;
      if (done.has(key)) continue;  // 線路を共用する区間（上海 3・4号線など）は 1 つだけ
      const sa = stById[a], sb = stById[b];
      if (!bounds.contains([sa.lat, sa.lon]) && !bounds.contains([sb.lat, sb.lon])) continue;
      done.add(key);
      const p = midpoint(segPath(l, a, b));
      const icon = L.divIcon({ className: "", html: `<div class="seg-time">${Math.max(1, Math.round(t))}分</div>`, iconSize: [0, 0] });
      timeLayer.addLayer(L.marker(p, { icon, pane: "labels", interactive: false, keyboard: false }));
    }
  }

  // ---------------------------------------------------------------- 表示範囲
  let pendingFit = null;  // 地図の大きさが 0（裏のタブで開いた等）のときは、表示されてから合わせる
  function moveToNet(id) {
    const net = nets.find((n) => n.id === id);
    if (!net) return;
    store.set("move", id);
    if (location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
    if (map.getSize().x === 0 || map.getSize().y === 0) {
      pendingFit = id;
      map.setView(net.center, net.zoom);
      return;
    }
    const [s, w, n, e] = net.focus_bbox;
    map.fitBounds([[s, w], [n, e]], { padding: [10, 10] });
  }
  map.on("resize", () => {
    if (pendingFit && map.getSize().x > 0) { const id = pendingFit; pendingFit = null; moveToNet(id); }
  });
  function fitAll() {
    const b = L.latLngBounds([]);
    for (const [id, line] of Object.entries(lineById)) {
      if (!lineVisible(id)) continue;
      for (const pl of line.geometry) for (const p of pl) b.extend(p);
    }
    if (b.isValid()) map.fitBounds(b, { padding: [20, 20] });
  }

  // ---------------------------------------------------------------- 操作
  $("region").addEventListener("change", (e) => loadRegion(e.target.value));
  $("move").addEventListener("change", (e) => moveToNet(e.target.value));
  $("btn-focus").addEventListener("click", () => moveToNet($("move").value));
  $("btn-all").addEventListener("click", fitAll);
  $("basemap").addEventListener("change", (e) => setBasemap(e.target.value));
  $("label-mode").addEventListener("change", (e) => { labelMode = e.target.value; store.set("label", labelMode); renderLabels(); });
  $("legend-tabs").addEventListener("click", (e) => {
    const id = e.target.dataset && e.target.dataset.tab;
    if (!id) return;
    activeTab = id;
    store.set("tab", id);
    renderLegend();
  });
  $("legend-body").addEventListener("change", (e) => {
    const t = e.target;
    if (t.dataset.line) { if (t.checked) hidden.delete(t.dataset.line); else hidden.add(t.dataset.line); }
    else if (t.dataset.net) { if (t.checked) hiddenNets.delete(t.dataset.net); else hiddenNets.add(t.dataset.net); renderLegend(); }
    else return;
    saveHidden();
    refresh();
  });
  $("legend-body").addEventListener("click", (e) => {
    const lang = e.target.dataset && e.target.dataset.lang;
    if (lang) { legendLang = lang; store.set("legendLang", lang); renderLegend(); return; }
    const all = e.target.dataset && e.target.dataset.all;
    if (!all) return;
    const net = nets.find((n) => n.id === activeTab) || nets[0];
    for (const l of net.lines) { if (all === "on") hidden.delete(l.id); else hidden.add(l.id); }
    if (all === "on") hiddenNets.delete(net.id);
    saveHidden();
    renderLegend();
    refresh();
  });
  $("btn-legend").addEventListener("click", () => {
    const lg = $("legend");
    lg.hidden = !lg.hidden;
    $("btn-legend").setAttribute("aria-expanded", String(!lg.hidden));
    $("btn-legend").setAttribute("aria-pressed", String(!lg.hidden));
    store.set("legend", lg.hidden ? "0" : "1");
  });
  $("btn-route").addEventListener("click", () => setRouteMode(!routeMode));
  $("route-close").addEventListener("click", () => setRouteMode(false));
  $("route-reset").addEventListener("click", () => { clearRoute(); renderRoutePanel(); refresh(); });
  $("route-body").addEventListener("click", (e) => {
    const b = e.target.closest("[data-route]");
    if (!b) return;
    routeResult = routeResults[+b.dataset.route];
    renderRoutePanel();
    refresh();
    fitRoute(routeResult);
  });
  $("btn-times").addEventListener("click", () => {
    timeLabels = !timeLabels;
    store.set("times", timeLabels ? "1" : "0");
    if (timeLabels && map.getZoom() < TIME_LABEL_MIN_ZOOM) map.setZoom(TIME_LABEL_MIN_ZOOM);  // 拡大しないと見えないので寄せる
    renderTimeLabels();
  });
  map.on("zoomend", refresh);
  map.on("moveend", () => { renderLabels(); renderTimeLabels(); });
  map.on("click", () => stationMarkers.forEach((o) => o.marker.closeTooltip()));

  // ---------------------------------------------------------------- 起動
  (async () => {
    $("label-mode").value = labelMode;
    activeTab = store.get("tab", null);
    const narrow = window.matchMedia("(max-width: 640px)").matches;
    const legendOpen = store.get("legend", narrow ? "0" : "1") === "1";
    $("legend").hidden = !legendOpen;
    $("btn-legend").setAttribute("aria-expanded", String(legendOpen));
    $("btn-legend").setAttribute("aria-pressed", String(legendOpen));
    try {
      catalog = await (await fetch("data/cities.json", { cache: "no-cache" })).json();
      const regionSel = $("region");
      const seen = new Set();
      for (const c of catalog) {
        if (seen.has(c.region)) continue;
        seen.add(c.region);
        regionSel.add(new Option(c.region_name_ja, c.region));
      }
      // URL の #<路線網 id>（例: #guangzhou）か、前回の表示を開く
      const want = location.hash.slice(1) || store.get("move", "");
      const entry = catalog.find((c) => c.id === want)
        || catalog.find((c) => c.region === store.get("region", "")) || catalog[0];
      await loadRegion(entry.region, entry.id === want ? entry.id : store.get("move", entry.id));
      await setBasemap(store.get("basemap", "plain"));  // 表示範囲が決まってから背景を載せる
    } catch (err) {
      console.error(err);
      $("map").innerHTML = '<p style="padding:16px;color:#1f2328">データを読み込めませんでした。'
        + "ローカルで開く場合は <code>python -m http.server</code> で配信してください。</p>";
    }
  })();
})();
