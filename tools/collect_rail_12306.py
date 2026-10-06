"""高鉄（広深港高速鉄道・広深線）の駅の組ごとの所要時間を、中国鉄路 12306 の列車検索から集める。

使い方:  python tools/collect_rail_12306.py [日付=YYYY-MM-DD]（省略時は次の火曜日）

  列車検索: https://kyfw.12306.cn/otn/leftTicket/queryG（指定した 2 駅間の全列車と所要時間）
  駅コード: https://kyfw.12306.cn/otn/resources/js/framework/station_name.js
保存先: raw/prd_rail/12306_<日付>.json  {"<発>|<着>": [{"code": 列車番号, "dep": 発, "arr": 着, "min": 分}, …]}
列車ごとに停車駅が違うため、経路計算では駅の組ごとの所要時間（中央値）を使う。
"""
from __future__ import annotations

import json
import re
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    if len(sys.argv) > 1:
        day = sys.argv[1]
    else:
        d = date.today() + timedelta(days=1)
        while d.weekday() != 1:
            d += timedelta(days=1)
        day = d.isoformat()
    cfg = json.loads((ROOT / "config/prd_rail.json").read_text(encoding="utf-8"))
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (metro-map-learning; personal study)"
    js = s.get("https://kyfw.12306.cn/otn/resources/js/framework/station_name.js", timeout=60).text
    codes = {m.group(1): m.group(2) for m in re.finditer(r"\|([^|]+)\|([A-Z]{3})\|", js)}
    s.get("https://kyfw.12306.cn/otn/leftTicket/init", timeout=60)
    out = {}
    for ln in cfg["lines"]:
        names = [st["name"].removesuffix("站").replace("龍", "龙") for st in ln["stations"]]
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                for x, y in ((a, b), (b, a)):
                    if x not in codes or y not in codes:
                        print(f"  code missing: {x} / {y}")
                        continue
                    for attempt in range(3):
                        r = s.get("https://kyfw.12306.cn/otn/leftTicket/queryG",
                                  params={"leftTicketDTO.train_date": day, "leftTicketDTO.from_station": codes[x],
                                          "leftTicketDTO.to_station": codes[y], "purpose_codes": "ADULT"}, timeout=60)
                        if r.status_code == 200 and r.text.startswith("{"):
                            break
                        time.sleep(5)
                    trains = []
                    for row in (r.json().get("data") or {}).get("result", []):
                        f = row.split("|")
                        # f[3]=列車番号 f[6]/f[7]=乗る駅/降りる駅のコード f[8]/f[9]=発/着 f[10]=所要（時:分）
                        if len(f) > 10 and f[6] == codes[x] and f[7] == codes[y] and re.fullmatch(r"\d\d:\d\d", f[10] or ""):
                            h, m = map(int, f[10].split(":"))
                            trains.append({"code": f[3], "dep": f[8], "arr": f[9], "min": h * 60 + m})
                    out[f"{x}|{y}"] = trains
                    print(f"{x}→{y}: {len(trains)} trains", flush=True)
                    time.sleep(1.5)
    p = ROOT / "raw/prd_rail" / f"12306_{day}.json"
    p.write_text(json.dumps({"date": day, "pairs": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {p.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
