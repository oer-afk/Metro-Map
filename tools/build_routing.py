"""所要時間検索（乗車時間の経路計算）と駅間ラベル用のデータを、地域ごとに 1 ファイルにまとめる。

使い方:  python tools/build_routing.py      （build_segments.py → build_times.py の後）
入力:
  site/data/cities.json, site/data/<id>.json        路線網（駅・路線）
  reports/segments/<id>_times.csv                     駅間の所要時間の最終値（final_min）
  reports/segments/<id>_paths.json                    駅間の線路沿いの形（経路の強調表示用）
  reports/segments/prd_rail_od.csv                    高鉄の駅の組ごとの所要時間（12306 の中央値）
  overrides/transfers.json                            路線網・種別をまたぐ乗換（歩き・出入境）
  overrides/direction_labels.json                     「●●方面」の表示の決まり
出力:
  site/data/routing-<地域>.json
    segs:   [[路線, 駅a, 駅b, 分], …]   隣り合う駅の間（上下とも同じ値。駅間ラベルと経路計算に使う）
    od:     [[路線, 発, 着, 分], …]     高鉄（列車で停車駅が違うので、駅の組ごとの値で経路を計算する）
    paths:  {"路線|駅a|駅b": [[緯度, 経度], …]}
    walks:  [[駅a, 駅b, "walk"|"border"], …]
    dirs:   方面の表示の決まり（環状線の回る向きを含む）
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_segments import main_length  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "reports" / "segments"
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def loop_order(net: dict, line: dict) -> str:
    """環状線の駅の並び順が時計回り（cw）か反時計回り（ccw）か（駅を結んだ多角形の符号付き面積）"""
    st = {s["id"]: s for s in net["stations"]}
    sts = line["stations"][:main_length(line["stations"], line.get("branches", []))]
    pts = [(st[x]["lon"], st[x]["lat"]) for x in sts]
    area = sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))
    return "ccw" if area > 0 else "cw"


def main() -> None:
    cities = load(ROOT / "site/data/cities.json")
    regions = defaultdict(list)
    for c in cities:
        regions[c["region"]].append(c)
    transfers = load(ROOT / "overrides/transfers.json")["transfers"]
    labels = load(ROOT / "overrides/direction_labels.json")

    for reg, entries in regions.items():
        nets = [load(ROOT / "site/data" / e["file"]) for e in entries]
        station_ids = {s["id"] for n in nets for s in n["stations"]}
        line_ids = {ln["id"] for n in nets for ln in n["lines"]}
        segs, od, paths = [], [], {}
        for n in nets:
            nid = n["id"]
            rows = list(csv.DictReader(open(SEG / f"{nid}_times.csv", encoding="utf-8-sig")))
            for r in rows:
                segs.append([r["line"], r["from"], r["to"], round(float(r["final_min"]), 2)])
            p = SEG / f"{nid}_paths.json"
            if p.exists():
                paths.update(load(p))
            odp = SEG / f"{nid}_od.csv"
            if odp.exists():
                line_of = {}
                for ln in n["lines"]:
                    for x in ln["stations"]:
                        line_of.setdefault(x, set()).add(ln["id"])
                for r in csv.DictReader(open(odp, encoding="utf-8-sig")):
                    common = line_of.get(r["from"], set()) & line_of.get(r["to"], set())
                    if common and r["median_min"]:
                        od.append([sorted(common)[0], r["from"], r["to"], round(float(r["median_min"]), 1)])

        walks = [[t["a"], t["b"], t["kind"]] for t in transfers if t["a"] in station_ids and t["b"] in station_ids]
        dirs = {k: v for k, v in labels.items() if not k.startswith("_")}
        dirs["replace"] = [x for x in dirs["replace"] if x["line"] in line_ids]
        dirs["via"] = [x for x in dirs["via"] if x["line"] in line_ids]
        dirs["through"] = [x for x in dirs["through"] if x["line"] in line_ids]
        dirs["none"] = [x for x in dirs["none"] if x in line_ids]
        loops = {}
        for n in nets:
            for ln in n["lines"]:
                if ln.get("loop") and ln["id"] in dirs["loop"]:
                    loops[ln["id"]] = {**dirs["loop"][ln["id"]], "order": loop_order(n, ln)}
        dirs["loop"] = loops
        tram = dirs.get("tram")
        if tram and tram["line"] in line_ids:
            # 跑馬地の支線の駅（そこで降りる区間は「跑馬地方面」）
            net = next(n for n in nets if any(ln["id"] == tram["line"] for ln in n["lines"]))
            ln = next(ln for ln in net["lines"] if ln["id"] == tram["line"])
            tram["branch_stations"] = sorted({x for b in ln.get("branches", []) if tram["branch"] in b for x in b[1:]})
        else:
            dirs.pop("tram", None)

        out = {"region": reg, "segs": segs, "od": od, "paths": paths, "walks": walks, "dirs": dirs}
        dst = ROOT / "site/data" / f"routing-{reg}.json"
        dst.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{reg}: {len(segs)} segs, {len(od)} od, {len(paths)} paths, {len(walks)} walks -> {dst.name} ({dst.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
