/* 地下鉄学習マップ — 表示ページ
 * 読むのは data/cities.json と data/<city>.json の 2 種類だけ。
 * 都市の追加は data/ にファイルを置き、cities.json に 1 行足すだけでよい。
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

  const $ = (id) => document.getElementById(id);
  const store = {
    get(k, d) { try { return localStorage.getItem("metro-map:" + k) ?? d; } catch { return d; } },
    set(k, v) { try { localStorage.setItem("metro-map:" + k, v); } catch { /* 保存できなくても動く */ } },
  };
  const isTouch = window.matchMedia("(hover: none)").matches;

  // ---------------------------------------------------------------- 地図
  const map = L.map("map", { zoomControl: true, preferCanvas: true, minZoom: 8, maxZoom: 18, zoomSnap: 0.25, zoomDelta: 0.5 });
  map.attributionControl.setPrefix(false);
  window.metroMap = map;  // 開発者ツールからの確認用
  const renderer = L.canvas({ tolerance: isTouch ? 10 : 4 });
  map.createPane("lines").style.zIndex = 410;
  map.createPane("stations").style.zIndex = 420;
  map.createPane("labels").style.zIndex = 430;

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
  let city = null;            // 読み込んだ都市データ
  let lineById = {};
  let hidden = new Set();     // 非表示の路線 id
  let lineLayers = {};        // 路線 id → L.LayerGroup
  let stationLayer = L.layerGroup();
  let labelLayer = L.layerGroup();
  let stationMarkers = [];    // { st, marker }
  let labelMode = store.get("label", "ja");

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
    return `<span class="badge" style="background:${line.color};color:${textColor(line.color)}">${esc(line.ref)}</span>`;
  }
  // 吹き出し: 原表記 ／ 日本漢字、読み（ローマ字＋カナ）、路線バッジ。これ以外は出さない。
  function tipHtml(st) {
    const names = `${esc(st.name_orig)}<span class="sep">／</span>${esc(st.name_ja)}`;
    return `<div class="tip-name">${names}</div>`
      + `<div class="tip-reading">${esc(st.reading.roman)}（${esc(st.reading.kana)}）</div>`
      + `<div class="badges">${st.lines.map((id) => badge(lineById[id])).join("")}</div>`;
  }
  function lineWeight(z) {
    return z <= 10 ? 2 : z <= 11 ? 2.5 : z <= 12 ? 3 : z <= 13 ? 4 : z <= 15 ? 5 : 6.5;
  }
  function stationRadius(z, transfer) {
    const r = z <= 10 ? 1.5 : z <= 11 ? 2 : z <= 12 ? 2.5 : z <= 13 ? 3.5 : z <= 15 ? 4.5 : 6;
    return transfer ? r + 2 : r;
  }
  function stationStyle(st, z) {
    const transfer = st.lines.length > 1;
    const visibleLines = st.lines.filter((id) => !hidden.has(id));
    const color = lineById[visibleLines[0] || st.lines[0]].color;
    const s = transfer
      ? { color: "#3a3f45", weight: z >= 13 ? 2 : 1.5, fillColor: "#ffffff", fillOpacity: 1 }
      : { color: "#ffffff", weight: z >= 13 ? 1.5 : 1, fillColor: color, fillOpacity: 1 };
    s.radius = stationRadius(z, transfer);
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

  // ---------------------------------------------------------------- 都市の読み込み
  async function loadCity(entry) {
    const res = await fetch("data/" + entry.file, { cache: "no-cache" });
    if (!res.ok) throw new Error(`${entry.file}: ${res.status}`);
    city = await res.json();
    lineById = Object.fromEntries(city.lines.map((l) => [l.id, l]));
    hidden = new Set(JSON.parse(store.get("hidden:" + city.id, "[]")).filter((id) => lineById[id]));
    store.set("city", city.id);
    if (location.hash !== "#" + city.id) history.replaceState(null, "", "#" + city.id);
    document.title = `${city.name_ja}の地下鉄 — 地下鉄学習マップ`;
    fitFocus();  // 先に表示範囲を決める（ラベル描画が地図の範囲を使うため）
    build();
  }

  function build() {
    Object.values(lineLayers).forEach((g) => map.removeLayer(g));
    map.removeLayer(stationLayer);
    map.removeLayer(labelLayer);
    lineLayers = {};
    stationLayer = L.layerGroup();
    labelLayer = L.layerGroup();
    stationMarkers = [];
    const z = map.getZoom() || city.zoom;

    // 路線（白い縁取り＋路線色）
    for (const line of city.lines) {
      const g = L.layerGroup();
      for (const pl of line.geometry) {
        g.addLayer(L.polyline(pl, { pane: "lines", renderer, color: "#ffffff", weight: lineWeight(z) + 2.5,
          opacity: 0.85, interactive: false, lineCap: "round", lineJoin: "round", _casing: true }));
      }
      for (const pl of line.geometry) {
        g.addLayer(L.polyline(pl, { pane: "lines", renderer, color: line.color, weight: lineWeight(z),
          opacity: 1, interactive: false, lineCap: "round", lineJoin: "round" }));
      }
      lineLayers[line.id] = g;
      if (!hidden.has(line.id)) g.addTo(map);
    }

    // 駅（乗換駅を上に描く）
    const sorted = [...city.stations].sort((a, b) => a.lines.length - b.lines.length);
    for (const st of sorted) {
      const m = L.circleMarker([st.lat, st.lon], { pane: "stations", renderer, ...stationStyle(st, z) });
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
      stationMarkers.push({ st, marker: m });
    }
    stationLayer.addTo(map);
    labelLayer.addTo(map);
    renderLegend();
    refresh();
  }

  // 路線の表示切替・ズームに応じた太さ・ラベルを反映
  function refresh() {
    if (!city) return;
    const z = map.getZoom();
    for (const line of city.lines) {
      const g = lineLayers[line.id];
      if (!g) continue;  // 都市の切替中（まだ描いていない）
      const on = !hidden.has(line.id);
      if (on && !map.hasLayer(g)) g.addTo(map);
      if (!on && map.hasLayer(g)) map.removeLayer(g);
      g.eachLayer((pl) => pl.setStyle({ weight: pl.options._casing ? lineWeight(z) + 2.5 : lineWeight(z) }));
    }
    for (const { st, marker } of stationMarkers) {
      const visible = st.lines.some((id) => !hidden.has(id));
      if (visible && !stationLayer.hasLayer(marker)) stationLayer.addLayer(marker);
      if (!visible && stationLayer.hasLayer(marker)) { marker.closeTooltip(); stationLayer.removeLayer(marker); }
      if (visible) marker.setStyle(stationStyle(st, z));
    }
    renderLabels();
  }

  function renderLabels() {
    labelLayer.clearLayers();
    if (labelMode === "none" || map.getZoom() < LABEL_MIN_ZOOM) return;
    const bounds = map.getBounds().pad(0.2);
    for (const { st } of stationMarkers) {
      if (!st.lines.some((id) => !hidden.has(id))) continue;
      if (!bounds.contains([st.lat, st.lon])) continue;
      let html;
      if (labelMode === "orig") html = esc(st.name_orig);
      else if (labelMode === "both") html = st.name_orig === st.name_ja ? esc(st.name_ja) : `${esc(st.name_ja)}<small>${esc(st.name_orig)}</small>`;
      else html = esc(st.name_ja);
      const icon = L.divIcon({ className: "", html: `<div class="station-label${st.verified ? "" : " unverified"}">${html}</div>`, iconSize: [0, 0] });
      labelLayer.addLayer(L.marker([st.lat, st.lon], { icon, pane: "labels", interactive: false, keyboard: false }));
    }
  }

  function renderLegend() {
    const ul = $("legend-list");
    ul.innerHTML = "";
    for (const line of city.lines) {
      const li = document.createElement("li");
      li.innerHTML = `<label><input type="checkbox" ${hidden.has(line.id) ? "" : "checked"} data-line="${esc(line.id)}">`
        + `<span class="swatch" style="background:${line.color}"></span>${badge(line)}`
        + `<span>${esc(line.name_ja)}</span></label>`;
      ul.appendChild(li);
    }
  }
  function saveHidden() { store.set("hidden:" + city.id, JSON.stringify([...hidden])); }

  // ---------------------------------------------------------------- 表示範囲
  function fitFocus() {
    const [s, w, n, e] = city.focus_bbox;
    map.fitBounds([[s, w], [n, e]], { padding: [10, 10] });
  }
  function fitAll() {
    const b = L.latLngBounds([]);
    for (const line of city.lines) {
      if (hidden.has(line.id)) continue;
      for (const pl of line.geometry) for (const p of pl) b.extend(p);
    }
    if (b.isValid()) map.fitBounds(b, { padding: [20, 20] });
  }

  // ---------------------------------------------------------------- 操作
  $("btn-focus").addEventListener("click", fitFocus);
  $("btn-all").addEventListener("click", fitAll);
  $("basemap").addEventListener("change", (e) => setBasemap(e.target.value));
  $("label-mode").addEventListener("change", (e) => { labelMode = e.target.value; store.set("label", labelMode); renderLabels(); });
  $("legend-list").addEventListener("change", (e) => {
    const id = e.target.dataset.line;
    if (!id) return;
    if (e.target.checked) hidden.delete(id); else hidden.add(id);
    saveHidden();
    refresh();
  });
  document.querySelectorAll("[data-all]").forEach((b) => b.addEventListener("click", () => {
    hidden = b.dataset.all === "on" ? new Set() : new Set(city.lines.map((l) => l.id));
    saveHidden();
    renderLegend();
    refresh();
  }));
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
    const narrow = window.matchMedia("(max-width: 640px)").matches;
    const legendOpen = store.get("legend", narrow ? "0" : "1") === "1";
    $("legend").hidden = !legendOpen;
    $("btn-legend").setAttribute("aria-expanded", String(legendOpen));
    $("btn-legend").setAttribute("aria-pressed", String(legendOpen));
    try {
      const cities = await (await fetch("data/cities.json", { cache: "no-cache" })).json();
      const sel = $("city");
      for (const c of cities) sel.add(new Option(c.name_ja, c.id));
      const want = location.hash.slice(1) || store.get("city", cities[0].id);
      const entry = cities.find((c) => c.id === want) || cities[0];
      sel.value = entry.id;
      sel.addEventListener("change", () => loadCity(cities.find((c) => c.id === sel.value)));
      await loadCity(entry);
      await setBasemap(store.get("basemap", "plain"));  // 表示範囲が決まってから背景を載せる
    } catch (err) {
      console.error(err);
      $("map").innerHTML = '<p style="padding:16px;color:#1f2328">データを読み込めませんでした。'
        + "ローカルで開く場合は <code>python -m http.server</code> で配信してください。</p>";
    }
  })();
})();
