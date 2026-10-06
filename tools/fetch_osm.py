"""Overpass API から都市の地下鉄データを取得し raw/<city>/ に保存する。

使い方:  python tools/fetch_osm.py shanghai [routes|stations]   （省略時は両方）

取得物（いずれも Overpass の JSON をそのまま保存）:
  routes.json   路線リレーション（route=subway 等）と親の route_master、
                構成要素の線路（ジオメトリ付き）と駅ノード、駅を含む stop_area
  stations.json 行政区内の地下鉄駅（railway=station のノード・面。面は中心点）
加工（build_city.py）は raw/ だけを読むので、再取得せずにやり直せる。
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

# Windows のコンソール（CP932）でも簡体字を出力できるようにする
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
# 本サーバーは混雑時に 504 を返すことが多いので、予備サーバーへ順に切り替える
ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}


def load_config(city: str) -> dict:
    return json.loads((ROOT / "config" / f"{city}.json").read_text(encoding="utf-8"))


def run_query(query: str) -> dict:
    for attempt in range(9):
        ep = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            r = requests.post(ep, data={"data": query}, headers=HEADERS, timeout=400)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                return r.json()
            print(f"  {ep}: HTTP {r.status_code}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  {ep}: {type(e).__name__}", file=sys.stderr)
        time.sleep(10 * (attempt // len(ENDPOINTS) + 1))
    raise RuntimeError("Overpass API に接続できませんでした（時間をおいて再実行してください）")


def main() -> None:
    city = sys.argv[1]
    cfg = load_config(city)
    area = cfg["overpass_area"]
    route_filter = "|".join(cfg["route_types"])
    out_dir = ROOT / "raw" / city
    out_dir.mkdir(parents=True, exist_ok=True)

    routes_q = f"""[out:json][timeout:300];
{area}->.a;
rel["route"~"^({route_filter})$"](area.a)->.r;
rel(br.r)["type"="route_master"]->.m;
way(r.r)->.w;
node(r.r)->.n;
rel(bn.n)["public_transport"="stop_area"]->.sa;
.m out body;
.r out body;
.sa out body;
.w out tags geom qt;
.n out body qt;
"""
    stations_q = f"""[out:json][timeout:300];
{area}->.a;
(
  nwr["railway"="station"]["station"~"^(subway|light_rail)$"](area.a);
  nwr["public_transport"="station"]["subway"="yes"](area.a);
);
out body center qt;
"""
    # 路線リレーションに入っていない線路（新しい延伸区間など）を、線路の名前で追加取得する
    extra = cfg.get("extra_track_ways", [])
    extra_q = None
    if extra:
        parts = "".join(f'way["railway"="subway"]["name"="{x["way_name"]}"](area.a);' for x in extra)
        extra_q = f"""[out:json][timeout:300];
{area}->.a;
({parts});
out tags geom qt;
"""
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    only = sys.argv[2:] or ["routes", "stations", "extra_ways"]
    for name, q in (("routes", routes_q), ("stations", stations_q), ("extra_ways", extra_q)):
        if name not in only or q is None:
            continue
        print(f"fetching {name} ...")
        data = run_query(q)
        if name == "extra_ways":  # どの路線の線路かを付けておく
            by_name = {x["way_name"]: x["line"] for x in extra}
            for e in data["elements"]:
                e["_line"] = by_name.get(e.get("tags", {}).get("name"))
        data["_fetched_at"] = fetched
        data["_query"] = q
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(data.get('elements', []))} elements -> {path.relative_to(ROOT)}")
        time.sleep(5)


if __name__ == "__main__":
    main()
