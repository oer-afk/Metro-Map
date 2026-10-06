"""確認用の駅一覧（仕様 6.2）を作る。本人が確認・修正したものを overrides/verified_<id>.csv にする。

使い方:  python tools/make_verify_draft.py <network_id> [件数=50]

主要エリア（focus_bbox）の中の駅から、乗換駅を優先し、主要エリアの中心に近い順に選ぶ。
出力: reports/<id>_verify_draft.csv（Excel で開ける UTF-8 BOM 付き）

列は付録 A と同じ（原表記,日本漢字,ピンイン,カタカナ,路線）に、修正を書き込む列を足したもの。
修正が無ければ「修正」列は空のままでよい。確認が済んだら修正を反映し、修正列を消して
overrides/verified_<id>.csv として保存する。
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def main() -> None:
    city = sys.argv[1]
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    data = json.loads((ROOT / "site" / "data" / f"{city}.json").read_text(encoding="utf-8"))
    s_, w_, n_, e_ = data["focus_bbox"]
    cy, cx = (s_ + n_) / 2, (w_ + e_) / 2
    ref_of = {ln["id"]: ln["ref"] for ln in data["lines"]}
    inside = [st for st in data["stations"] if s_ <= st["lat"] <= n_ and w_ <= st["lon"] <= e_]

    def dist(st):
        return math.hypot((st["lat"] - cy) * 111, (st["lon"] - cx) * 111 * math.cos(math.radians(cy)))

    picked = sorted(inside, key=lambda st: (-len(st["lines"]), dist(st)))[:limit]
    picked.sort(key=lambda st: (min(int(ref_of[x]) if ref_of[x].isdigit() else 999 for x in st["lines"]), dist(st)))
    out = ROOT / "reports" / f"{city}_verify_draft.csv"
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["原表記", "日本漢字", "ピンイン", "カタカナ", "路線", "修正（日本漢字）", "修正（ピンイン）", "修正（カタカナ）", "メモ"])
        for st in picked:
            r = st["reading"]["cmn"]
            w.writerow([st["name_orig"], st["name_ja"], r["roman"], r["kana"],
                        "/".join(ref_of[x] for x in st["lines"]), "", "", "", ""])
    print(f"{len(picked)} stations (of {len(inside)} in focus area) -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
