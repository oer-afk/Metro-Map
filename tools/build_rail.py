"""高速鉄道・在来線の路線網（珠江デルタの「高鉄」）を作る。

使い方:  python tools/build_rail.py prd_rail [--fetch]

地下鉄と違い、OSM に運行系統（route=train）の情報が乏しいため、次の方法で作る（仕様書第2版 6.1）。
  線形: 線路の路線リレーション（route=railway、config の relation）を構成する線路
  駅  : config に書いた駅名（Wikipedia の駅一覧から旅客駅を採ったもの）に一致する railway=station の点
--fetch を付けると Overpass API から raw/<id>/ に取り直す。付けなければ保存済みの raw/ だけで作る。

出力: site/data/<id>.json（地下鉄の路線網と同じ形）、reports/<id>_build.json、reports/<id>_validation.md
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textconv  # noqa: E402
from build_city import (COORD_DIGITS, DEDUP_TRACK_M, SIMPLIFY_M, Grid, _dump_city, chain_ways,  # noqa: E402
                        densify, dist_m, nearest_on_polylines, rdp)
from fetch_osm import run_query  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
STATION_MAX_M = 1500  # 駅の点と線路の距離の上限（これより遠い同名の点は別の駅とみなす）


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def fetch(cfg: dict, raw: Path) -> None:
    rel_ids = ",".join(str(ln["relation"]) for ln in cfg["lines"])
    s, w, n, e = cfg["station_bbox"]
    q_lines = f"""[out:json][timeout:300];
rel(id:{rel_ids});
out body;
way(r);
out tags geom qt;
"""
    q_stations = f"""[out:json][timeout:300];
(
  node["railway"~"^(station|halt)$"]({s},{w},{n},{e});
  way["railway"="station"]({s},{w},{n},{e});
);
out body center qt;
"""
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for name, q in (("lines", q_lines), ("stations", q_stations)):
        print(f"fetching {name} ...")
        data = run_query(q)
        data["_fetched_at"] = fetched
        data["_query"] = q
        (raw / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(data.get('elements', []))} elements")


def main() -> None:
    net_id = sys.argv[1]
    cfg = load(ROOT / "config" / f"{net_id}.json")
    raw = ROOT / "raw" / net_id
    raw.mkdir(parents=True, exist_ok=True)
    if "--fetch" in sys.argv:
        fetch(cfg, raw)
    lines_raw = load(raw / "lines.json")
    st_raw = load(raw / "stations.json")
    textconv.add_city_words(net_id)
    report: dict = {"network": net_id, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    els = {(e["type"], e["id"]): e for e in lines_raw["elements"]}

    # 駅の候補: railway=station の点（名前のゆれ「○○站」「○○」と、香港の中英併記を吸収）
    def names_of(tags: dict) -> set[str]:
        out = set()
        for k in ("name", "name:zh", "name:zh-Hans", "name:zh-Hant", "official_name", "old_name"):
            v = tags.get(k)
            if not v:
                continue
            v = re.sub(r"\s+[A-Za-z].*$", "", textconv.normalize_orig(v))  # 「香港西九龍 Hong Kong West Kowloon」→ 前半
            out |= {v, v.removesuffix("站"), v + "站"}
        return out

    cands = []
    for e in st_raw["elements"]:
        t = e.get("tags", {})
        if t.get("station") in ("subway", "light_rail") or t.get("subway") == "yes":
            continue  # 地下鉄の駅は除く（同名の地下鉄駅と取り違えないように）
        p = (e["lat"], e["lon"]) if "lat" in e else ((e["center"]["lat"], e["center"]["lon"]) if "center" in e else None)
        if p:
            cands.append((names_of(t), p, t))

    lines_out, st_out, problems = [], [], []
    for ln in cfg["lines"]:
        rel = els.get(("relation", ln["relation"]))
        if rel is None:
            raise SystemExit(f"relation {ln['relation']} が raw にありません（--fetch で取り直す）")
        ways = [[(g["lat"], g["lon"]) for g in els[("way", m["ref"])]["geometry"]]
                for m in rel["members"] if m["type"] == "way" and ("way", m["ref"]) in els
                and els[("way", m["ref"])].get("geometry")]
        # 複線・並走の線路を 1 本に間引いてからつなぐ（地下鉄と同じ処理）
        ways.sort(key=lambda pts: -sum(dist_m(a, b) for a, b in zip(pts, pts[1:])))
        grid, kept = Grid(), []
        for pts in ways:
            dense = densify(pts)
            if sum(1 for p in dense if grid.near(p, DEDUP_TRACK_M)) / len(dense) >= 0.9:
                continue
            kept.append(pts)
            grid.add(dense)
        geom = [[[round(p[0], COORD_DIGITS), round(p[1], COORD_DIGITS)] for p in rdp(c, SIMPLIFY_M)]
                for c in chain_ways(kept)]
        lid = f"{cfg['id_prefix']}_{ln['ref'].lower()}"
        station_ids = []
        for spec in ln["stations"]:
            want = {spec["name"], spec["name"].removesuffix("站")}
            if spec.get("former"):
                want |= {spec["former"], spec["former"].removesuffix("站")}
            hits = [(nearest_on_polylines(p, geom)[1], p, t) for names, p, t in cands if names & want]
            hits = [h for h in hits if h[0] <= STATION_MAX_M]
            if not hits:
                problems.append(f"{ln['name_orig']}: {spec['name']} の駅の点が見つからない（線路から {STATION_MAX_M} m 以内）")
                continue
            d, p, t = min(hits, key=lambda h: h[0])
            q, _ = nearest_on_polylines(p, geom)  # 駅の点を線路の上に寄せる
            hk = bool(spec.get("hk"))
            name = spec["name"]
            en = t.get("name:en")
            if hk:
                textconv.set_style(hk=True)
                reading = {"cmn": {"roman": textconv.reading_cmn(textconv.to_simplified(name))["roman"]},
                           "yue": textconv.reading_yue(name)}
                name_ja = textconv.to_name_ja_hant(name)
                textconv.set_style(hk=False)
            else:
                reading = {"cmn": textconv.reading_cmn(name)}
                name_ja = textconv.to_name_ja(name)
            slug = re.sub(r"[^a-z0-9]", "", (en or "").lower()) if hk else \
                re.sub(r"[^a-z0-9]", "", "".join(x for _, x in textconv._word_pinyin(name)).lower())
            sid = f"{cfg['id_prefix']}_{slug}"
            station_ids.append(sid)
            st_out.append({
                "id": sid, "name_orig": name, "name_ja": name_ja, "name_en": en, "kind": "hsr",
                **({"script": "hant"} if hk else {}),
                "reading": reading, "lat": round(q[0], COORD_DIGITS), "lon": round(q[1], COORD_DIGITS),
                "lines": [lid], "verified": False, "_dist_m": round(d),
                **({"_former": spec["former"]} if spec.get("former") else {}),
            })
        lines_out.append({
            "id": lid, "ref": ln["ref"], "badge": ln["badge"], "name_orig": ln["name_orig"],
            "name_ja": textconv.to_name_ja(ln["name_orig"]), "color": ln["color"], "color_source": "config",
            "mode": ln["mode"], "stations": station_ids, "geometry": geom,
        })

    # 主要エリア（移動=高鉄）は、全駅と線形が収まる範囲を計算して上書きする（仕様 3.1）
    pts = [p for ln in lines_out for pl in ln["geometry"] for p in pl] + [[s["lat"], s["lon"]] for s in st_out]
    bbox = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]
    bbox = [round(bbox[0] - 0.02, 3), round(bbox[1] - 0.02, 3), round(bbox[2] + 0.02, 3), round(bbox[3] + 0.02, 3)]
    out = {
        "id": cfg["id"], "region": cfg["region"], "name_ja": cfg["name_ja"], "name_orig": cfg["name_orig"],
        "script": cfg["script"], "reading_langs": cfg["reading_langs"],
        "center": [round((bbox[0] + bbox[2]) / 2, 3), round((bbox[1] + bbox[3]) / 2, 3)], "zoom": cfg["zoom"],
        "focus_bbox": bbox,
        "source": {"name": "OpenStreetMap", "license": "ODbL 1.0", "extracted": lines_raw.get("_fetched_at", "")[:10]},
        "lines": lines_out,
        "stations": [{k: v for k, v in s.items() if not k.startswith("_")} for s in st_out],
    }
    data_dir = ROOT / "site" / "data"
    (data_dir / f"{net_id}.json").write_text(_dump_city(out), encoding="utf-8")
    cpath = data_dir / "cities.json"
    cities = load(cpath) if cpath.exists() else []
    entry = {"id": cfg["id"], "region": cfg["region"], "region_name_ja": cfg["region_name_ja"],
             "name_ja": cfg["name_ja"], "name_orig": cfg["name_orig"], "file": f"{net_id}.json", "order": cfg["order"]}
    cities = sorted([c for c in cities if c["id"] != cfg["id"]] + [entry], key=lambda c: c.get("order", 999))
    cpath.write_text("[\n" + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in cities) + "\n]\n",
                     encoding="utf-8")

    # 検証（仕様 6.3）: config の駅（Wikipedia の旅客駅）が全部見つかったか、駅と線路の距離、同名の地下鉄駅との距離
    metro = {}
    for c in cities:
        if c["region"] == cfg["region"] and c["id"] != cfg["id"]:
            for s in load(data_dir / c["file"])["stations"]:
                metro.setdefault(textconv.to_simplified(s["name_orig"]).removesuffix("站"), []).append((s["lat"], s["lon"], c["name_ja"]))
    md = [f"# 検証結果：{cfg['name_ja']}（{'・'.join(ln['name_orig'] for ln in cfg['lines'])}）", "",
          f"- OSM 取得日: {out['source']['extracted']}",
          f"- 路線 {len(lines_out)}、駅 {len(st_out)}（すべて未確認）", "",
          "## 駅（config の駅一覧＝Wikipedia の旅客駅と照合）", "",
          "| 路線 | 駅 | 線路からの距離 (m) | 同名の地下鉄駅との距離 |", "|---|---|---:|---|"]
    for ln in cfg["lines"]:
        lid = f"{cfg['id_prefix']}_{ln['ref'].lower()}"
        for s in st_out:
            if s["lines"] == [lid]:
                key = textconv.to_simplified(s["name_orig"]).removesuffix("站")
                near = [f"{m[2]} {round(dist_m((s['lat'], s['lon']), (m[0], m[1])))} m" for m in metro.get(key, [])]
                md.append(f"| {ln['name_orig']} | {s['name_orig']}{'（旧 ' + s['_former'] + '）' if s.get('_former') else ''} "
                          f"| {s['_dist_m']} | {'、'.join(near) or '—'} |")
    md += ["", "## 問題", ""] + ([f"- {p}" for p in problems] or ["- なし（config の全駅が線路の近くに見つかった）"])
    md += ["", "## 色", "", f"- {cfg['_notes']['colors']}", "", "## 駅の選び方", "", f"- {cfg['_notes']['stations']}"]
    rep = ROOT / "reports"
    (rep / f"{net_id}_validation.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    report.update({"lines": [{"id": l["id"], "stations": len(l["stations"]), "polylines": len(l["geometry"])} for l in lines_out],
                   "problems": problems, "focus_bbox": bbox})
    (rep / f"{net_id}_build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
