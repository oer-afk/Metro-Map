"""香港 MTR の公式の経路検索（Trip Planner）から、各路線の駅ごとの累積所要時間を集める。

使い方:  python tools/collect_hk_planner.py

  API: https://www.mtr.com.hk/share/customer/jp/api/HRRoutes/?o=<発駅 ID>&d=<着駅 ID>&lang=C
       応答の routes[].path[] に、経路上の各駅までの累積時間（分、平日朝の標準）が入る。
  駅 ID: raw/hongkong/mtr_lines_and_stations.csv（MTR の公開データ）
各路線・各方向（支線を含む）について、始点 → 終点を検索する。
検索結果が別の路線を通る（乗換を含む）場合は、その路線の中だけで 2 つに分けて検索し直す。
保存先: raw/hongkong/planner.json  {"<路線>|<方向>": [{"code": 駅コード, "t": 累積分, "first": 検索の最初の区間か}, …]}
  検索の最初の区間（起点 → 次の駅）は、乗車の余裕とみられる分だけ平均 1.2 分長い（2026-10-06 の照合）。
  build_times.py はこの区間（"first": true の駅に着く区間）を使わず、逆向きの検索の値を使う。
"""
from __future__ import annotations

import csv
import io
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def query(o: str, d: str) -> dict:
    for _ in range(3):
        try:
            r = requests.get("https://www.mtr.com.hk/share/customer/jp/api/HRRoutes/",
                             params={"o": o, "d": d, "lang": "C"}, headers=HEADERS, timeout=30)
            return r.json()
        except Exception:  # noqa: BLE001
            time.sleep(3)
    return {}


def ride(o_id: str, d_id: str, id2code: dict) -> list[dict] | None:
    """o → d の検索で、乗換なし（RIDE のみ・同じ lineID）の経路の各駅の累積時間。乗換を含めば None"""
    res = query(o_id, d_id)
    routes = res.get("routes") or []
    if not routes:
        return None
    path = routes[0]["path"]
    if routes[0].get("interchangeStationsNo"):
        return None
    if any(p.get("linkType") not in ("RIDE", "END", None) for p in path):
        return None
    return [{"code": id2code.get(str(p["ID"])), "t": float(p["time"]), "first": i == 1} for i, p in enumerate(path)]


def main() -> None:
    rows = list(csv.DictReader(io.StringIO((ROOT / "raw/hongkong/mtr_lines_and_stations.csv").read_text(encoding="utf-8-sig"))))
    id2code = {r["Station ID"]: r["Station Code"] for r in rows if r["Line Code"]}
    code2id = {v: k for k, v in id2code.items()}
    seqs = defaultdict(list)
    for r in rows:
        if r["Line Code"]:
            seqs[(r["Line Code"], r["Direction"])].append((float(r["Sequence"]), r["Station Code"]))
    out = {}
    for (line, d), seq in sorted(seqs.items()):
        codes = [c for _, c in sorted(seq)]
        res = ride(code2id[codes[0]], code2id[codes[-1]], id2code)
        if res is None or [x["code"] for x in res] != codes:
            # 別の路線を通る経路が返ったときは、半分ずつ検索してつなぐ
            mid = len(codes) // 2
            a = ride(code2id[codes[0]], code2id[codes[mid]], id2code)
            b = ride(code2id[codes[mid]], code2id[codes[-1]], id2code)
            if a and b and [x["code"] for x in a] + [x["code"] for x in b[1:]] == codes:
                res = a + [{"code": x["code"], "t": a[-1]["t"] + x["t"], "first": x["first"]} for x in b[1:]]
            else:
                res = None
        out[f"{line}|{d}"] = res
        print(f"{line} {d}: {'ok ' + str(res[-1]['t']) + ' 分' if res else '取れず'}", flush=True)
        time.sleep(0.5)
    (ROOT / "raw/hongkong/planner.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
