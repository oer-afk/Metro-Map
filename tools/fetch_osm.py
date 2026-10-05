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
ENDPOINT = "https://overpass-api.de/api/interpreter"
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}


def load_config(city: str) -> dict:
    return json.loads((ROOT / "config" / f"{city}.json").read_text(encoding="utf-8"))


def run_query(query: str) -> dict:
    for attempt in range(4):
        r = requests.post(ENDPOINT, data={"data": query}, headers=HEADERS, timeout=400)
        if r.status_code == 200:
            return r.json()
        print(f"  HTTP {r.status_code}; retry in {30 * (attempt + 1)}s", file=sys.stderr)
        time.sleep(30 * (attempt + 1))
    r.raise_for_status()
    raise RuntimeError("unreachable")


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
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    only = sys.argv[2:] or ["routes", "stations"]
    for name, q in (("routes", routes_q), ("stations", stations_q)):
        if name not in only:
            continue
        print(f"fetching {name} ...")
        data = run_query(q)
        data["_fetched_at"] = fetched
        data["_query"] = q
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        print(f"  {len(data.get('elements', []))} elements -> {path.relative_to(ROOT)}")
        time.sleep(5)


if __name__ == "__main__":
    main()
