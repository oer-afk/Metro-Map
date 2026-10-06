"""香港 MTR（重鉄 10 路線）の次の列車の到着予定（公式 API）を、全駅について何回か取得して保存する。

使い方:  python tools/collect_hk_nexttrain.py [回数=6] [間隔の分=5]

  API: https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php?line=<路線>&sta=<駅>（data.gov.hk、香港政府の公開データ）
  駅の一覧: https://opendata.mtr.com.hk/data/mtr_lines_and_stations.csv（MTR の公開データ）
保存先: raw/hongkong/nexttrain/<取得時刻>.json（1 回分＝全駅の応答）
駅間の所要時間への変換は tools/build_segments.py が行う。
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
OUT = ROOT / "raw" / "hongkong" / "nexttrain"
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def stations() -> list[tuple[str, str]]:
    path = ROOT / "raw" / "hongkong" / "mtr_lines_and_stations.csv"
    if not path.exists():
        r = requests.get("https://opendata.mtr.com.hk/data/mtr_lines_and_stations.csv", headers=HEADERS, timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    rows = list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    return sorted({(r["Line Code"], r["Station Code"]) for r in rows if r["Line Code"]})


def main() -> None:
    times = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    interval = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    OUT.mkdir(parents=True, exist_ok=True)
    pairs = stations()
    for k in range(times):
        snap = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "responses": {}}
        for line, sta in pairs:
            for attempt in range(3):
                try:
                    r = requests.get("https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php",
                                     params={"line": line, "sta": sta, "lang": "EN"}, headers=HEADERS, timeout=30)
                    snap["responses"][f"{line}-{sta}"] = r.json()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(2)
            time.sleep(0.25)
        name = datetime.now().strftime("%Y%m%d-%H%M%S")
        (OUT / f"{name}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
        print(f"snapshot {k + 1}/{times}: {len(snap['responses'])} stations -> {name}.json", flush=True)
        if k + 1 < times:
            time.sleep(interval * 60)


if __name__ == "__main__":
    main()
