"""香港 輕鐵の次の電車（公式 API）を、全 68 停留所について何回か取得して保存する。

使い方:  python tools/collect_hk_lrt.py [回数=6] [間隔の分=5]

  API: https://rt.data.gov.hk/v1/transport/mtr/lrt/getSchedule?station_id=<停留所 ID>
  停留所の一覧: https://opendata.mtr.com.hk/data/light_rail_routes_and_stops.csv
保存先: raw/hongkong/lrt/<取得時刻>.json
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "hongkong" / "lrt"
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}


def main() -> None:
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    OUT.mkdir(parents=True, exist_ok=True)
    rows = list(csv.DictReader(io.StringIO((ROOT / "raw/hongkong/light_rail_routes_and_stops.csv").read_text(encoding="utf-8-sig"))))
    ids = sorted({r["Stop ID"] for r in rows}, key=int)
    for k in range(times):
        snap = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "responses": {}}
        for sid in ids:
            for _ in range(3):
                try:
                    r = requests.get("https://rt.data.gov.hk/v1/transport/mtr/lrt/getSchedule",
                                     params={"station_id": sid}, headers=HEADERS, timeout=30)
                    snap["responses"][sid] = r.json()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            time.sleep(0.25)
        name = datetime.now().strftime("%Y%m%d-%H%M%S")
        (OUT / f"{name}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        print(f"snapshot {k + 1}/{times}: {len(snap['responses'])} stops", flush=True)
        if k + 1 < times:
            time.sleep(interval * 60)


if __name__ == "__main__":
    main()
