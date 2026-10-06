"""全駅の表記と読み（日本漢字・ピンイン・カナ・粤拼）を 1 つの一覧に書き出す（外部のレビュー用）。

使い方:  python tools/export_readings.py
出力:    reports/reading_review/stations_readings.csv（全路線網、Excel で開ける UTF-8 BOM 付き）
         reports/reading_review/stations_readings_<id>.csv（路線網ごと。分けて渡したいとき用）
         依頼文は reports/reading_review/review_request.md（手で書いたもの。表記の決まりを含む）
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "reports" / "reading_review"
COLS = ["路線網", "駅ID", "種別", "原表記", "日本漢字", "英語名", "路線", "ピンイン", "普通話カナ", "粤拼", "広東語カナ", "確認済み"]
KIND = {"metro": "地下鉄", "light_rail": "輕鐵", "tram": "電車", "funicular": "山頂纜車", "hsr": "高鉄"}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cities = json.loads((ROOT / "site/data/cities.json").read_text(encoding="utf-8"))
    every = []
    for c in cities:
        net = json.loads((ROOT / "site/data" / c["file"]).read_text(encoding="utf-8"))
        badge = {ln["id"]: ln["badge"] for ln in net["lines"]}
        rows = []
        for s in net["stations"]:
            r = s.get("reading", {})
            cmn, yue = r.get("cmn", {}), r.get("yue", {})
            rows.append({
                "路線網": net["name_ja"], "駅ID": s["id"], "種別": KIND.get(s["kind"], s["kind"]),
                "原表記": s["name_orig"], "日本漢字": s["name_ja"], "英語名": s.get("name_en") or "",
                "路線": "・".join(badge.get(x, x) for x in s["lines"]),
                "ピンイン": cmn.get("roman", ""), "普通話カナ": cmn.get("kana", ""),
                "粤拼": yue.get("jyutping", ""), "広東語カナ": yue.get("kana", ""),
                "確認済み": "済" if s.get("verified") else "",
            })
        with (OUT / f"stations_readings_{net['id']}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
        every += rows
        print(f"{net['id']}: {len(rows)}")
    with (OUT / "stations_readings.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(every)
    print(f"total: {len(every)} -> {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
