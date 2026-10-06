/* 地下鉄学習マップ — 表示ページ
 * 読むのは data/cities.json（路線網の一覧）と data/<id>.json（路線網ごとのデータ）だけ。
 * 路線網の追加は data/ にファイルを置き、cities.json に 1 行足すだけでよい。
 * cities.json の各行は region（地域）を持ち、同じ地域の路線網は同時に表示する。
 */
(() => {
  "use strict";

  const LABEL_MIN_ZOOM = 14;  // これ以上拡大すると駅名を常時表示
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
      const names = [st.name_orig, st.name_en, st.name_ja].filter(Boolean).map(esc).join(sep);
      return `<div class="tip-name">${names}</div>`
        + (r.cmn ? `<div class="tip-reading"><span class="lang">普</span>${esc(r.cmn.roman)}</div>` : "")
        + `<div class="tip-reading"><span class="lang">粤</span>${esc(supTones(r.yue.jyutping))}`
        + `${r.yue.kana ? `（${esc(r.yue.kana)}）` : ""}</div>` + badges;
    }
    const c = r.cmn || {};
    return `<div class="tip-name">${esc(st.name_orig)}${sep}${esc(st.name_ja)}</div>`
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
    if (!st.verified) {           // 未確認の駅は薄く・破線の縁で区別
      s.fillOpacity = transfer ? 0.55 : 0.45;
      s.opacity = 0.7;
      s.dashArray = "2 2";
      if (transfer) s.color = "#8c959f";
    }
    return s;
  }

  // ---------------------------------------------------------------- 地域の読み込み
  async function loadRegion(regionId, moveTo) {
    const entries = catalog.filter((c) => c.region === regionId);
    const datas = await Promise.all(entries.map(async (e) => {
      const res = await fetch("data/" + e.file, { cache: "no-cache" });
      if (!res.ok) throw new Error(`${e.file}: ${res.status}`);
      return res.json();
    }));
    clearLayers();  // 前の地域の表示を先に片付ける（移動中の再描画で古い路線を参照しないように）
    region = regionId;
    nets = datas;
    netOf = {};
    lineById = {};
    for (const n of nets) for (const l of n.lines) { netOf[l.id] = n; lineById[l.id] = l; }
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
    lineLayers = {};
    stationLayer = L.layerGroup();
    labelLayer = L.layerGroup();
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
        if (isTouch) {
          // タッチ端末: タップで表示、別の場所をタップで閉じる
          m.off("mouseover mouseout");
          m.on("click", (e) => {
            L.DomEvent.stopPropagation(e);
            stationMarkers.forEach((o) => o.marker !== m && o.marker.closeTooltip());
            m.openTooltip();
          });
        }
        stationMarkers.push({ st, net, marker: m });
      }
    }
    stationLayer.addTo(map);
    labelLayer.addTo(map);
    renderLegend();
    refresh();
  }

  // 路線の表示切替・ズームに応じた太さ・ラベルを反映
  function refresh() {
    if (!nets.length) return;
    const z = map.getZoom();
    for (const [id, g] of Object.entries(lineLayers)) {
      const on = lineVisible(id);
      if (on && !map.hasLayer(g)) g.addTo(map);
      if (!on && map.hasLayer(g)) map.removeLayer(g);
      if (on) g.eachLayer((pl) => pl.setStyle({ weight: lineWeight(z, pl.options._mode) + (pl.options._casing ? 2.5 : 0) }));
    }
    // 駅は線より後に描く（Canvas は追加順に重なる）
    map.removeLayer(stationLayer);
    for (const { st, marker } of stationMarkers) {
      const visible = st.lines.some(lineVisible);
      if (visible && !stationLayer.hasLayer(marker)) stationLayer.addLayer(marker);
      if (!visible && stationLayer.hasLayer(marker)) { marker.closeTooltip(); stationLayer.removeLayer(marker); }
      if (visible) marker.setStyle(stationStyle(st, z));
    }
    stationLayer.addTo(map);
    renderLabels();
  }

  function labelText(st) {
    if (labelMode === "orig") return esc(st.name_orig);
    if (labelMode === "en") return esc(st.name_en && st.reading && st.reading.yue ? st.name_en : st.name_orig);
    if (labelMode === "both") return st.name_orig === st.name_ja ? esc(st.name_ja) : `${esc(st.name_ja)}<small>${esc(st.name_orig)}</small>`;
    return esc(st.name_ja);
  }
  function renderLabels() {
    labelLayer.clearLayers();
    if (!nets.length || labelMode === "none" || map.getZoom() < LABEL_MIN_ZOOM) return;
    const bounds = map.getBounds().pad(0.2);
    for (const { st } of stationMarkers) {
      if (!st.lines.some(lineVisible)) continue;
      if (!bounds.contains([st.lat, st.lon])) continue;
      const icon = L.divIcon({ className: "", html: `<div class="station-label${st.verified ? "" : " unverified"}">${labelText(st)}</div>`, iconSize: [0, 0] });
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
    const groups = net.groups && net.groups.length ? net.groups : [{ id: null, name: null }];
    for (const g of groups) {
      const lines = net.lines.filter((l) => (g.id ? l.group === g.id : true));
      if (!lines.length) continue;
      if (g.name) html += `<div class="legend-group">${esc(g.name)}</div>`;
      // 英語の路線名がある路線網（香港）は、凡例に英語名も並べる（狭い画面では日本語名の代わりに英語名）
      const withEn = lines.some((l) => l.name_en);
      html += `<ul class="legend-list${withEn ? " with-en" : ""}${netOn ? "" : " disabled"}">` + lines.map((line) =>
        `<li><label><input type="checkbox" ${hidden.has(line.id) ? "" : "checked"} data-line="${esc(line.id)}">`
        + `<span class="swatch" style="background:${line.color}"></span>${badge(line)}`
        + `<span class="lname">${esc(line.name_ja)}</span>`
        + (line.name_en ? `<span class="lname-en">${esc(line.name_en)}</span>` : "")
        + `</label></li>`).join("") + "</ul>";
    }
    if ((net.reading_langs || []).includes("yue")) {
      html += `<details class="tones"><summary>広東語の声調（粤拼の数字）</summary><table>`
        + YUE_TONES.map(([d, t, c]) => `<tr><td class="tone-d">${d}</td><td>${t}</td><td class="tone-c">${c}</td></tr>`).join("")
        + `</table><p>1〜3 は高め、4〜6 は低め。2 と 5 は上がる、4 だけ下がる、1・3・6 は平ら。</p></details>`;
    }
    body.innerHTML = html;
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
  map.on("zoomend", refresh);
  map.on("moveend", renderLabels);
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
