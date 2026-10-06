"""路線データ・駅間距離・所要時間を、作るときに使っていない情報源と照合する。

使い方:  python tools/verify_times.py      （build_segments.py → build_times.py の後）
出力:    reports/segments/verification.md

照合の内容:
  A. 駅の並び（隣り合う駅の組）: 本地宝の時刻表の駅順（上海・広州・深圳）、MTR 公式の駅一覧（香港 MTR・輕鐵）
     ※ 駅の並びは OSM から作っているので、どちらも独立した情報源
  B. 路線の長さ・駅数: 中国語版 Wikipedia の路線記事の情報欄（linelength・stations）
  C. 所要時間: 情報源どうし（OSM の全線所要時間 ↔ 最終値、MTR の経路検索 ↔ 次の電車 API）
  D. あり得ない値: 駅間の平均速度（最高速度を超える・遅すぎる）、直線距離に対する遠回り
"""
from __future__ import annotations

import csv
import json
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_times as BT  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "reports" / "segments"
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def bendibao_refs(title: str) -> list[str]:
    """本地宝のページ名 → 路線の ref（当方の表記）"""
    if "有轨电车" in title:
        return []
    if "支线" in title and "6号线" in title:
        return ["6B"]
    if "APM" in title:
        return ["APM"]
    if "广佛" in title:
        return ["GF"]
    return re.findall(r"(\d+)号线", title)


def wiki_field(w: str, keys: tuple) -> str | None:
    for k in keys:
        m = re.search(r"^\|\s*" + re.escape(k) + r"\s*=[ \t]*(.*)$", w, re.M)
        if m and m.group(1).strip() and not m.group(1).strip().startswith("|"):
            return re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", m.group(1))
    return None


def first_num(s: str | None) -> float | None:
    if not s:
        return None
    s = re.sub(r"[（(][^）)]*(未來|未来|規劃|规划|远期|遠期|在建)[^）)]*[）)]", "", s)
    m = re.search(r"\{\{convert\|([\d.]+)", s) or re.search(r"([\d.]+)", s)
    return float(m.group(1)) if m else None


def main() -> None:
    cities = load(ROOT / "site/data/cities.json")
    nets = {c["id"]: load(ROOT / "site/data" / c["file"]) for c in cities}
    md = ["# 照合: 路線データ・駅間距離・所要時間（作るときに使っていない情報源と比べる）", "",
          "`python tools/verify_times.py` で作り直す。", ""]
    summary = []

    # 区間の最終値
    rows = {nid: list(csv.DictReader(open(SEG / f"{nid}_times.csv", encoding="utf-8-sig"))) for nid in nets}
    pairs_of = {nid: defaultdict(set) for nid in nets}  # 路線 ref → {frozenset(駅名キー 2 つ)}
    for nid, rs in rows.items():
        for r in rs:
            pairs_of[nid][r["ref"]].add(frozenset((BT.nkey(r["from_name"]), BT.nkey(r["to_name"]))))

    # ---------------------------------------------------------------- A. 駅の並び
    md += ["## A. 駅の並び（隣り合う駅の組）", "",
           "当方の駅間（OSM から作成）と、独立した駅順の一覧を比べる。「先方のみ」は当方に無い隣接（駅の抜け・順序の違い）、",
           "「当方のみ」は先方に無い隣接（先方の表が一部区間だけの場合も出る）。", "",
           "| 路線網 | 路線 | 照合先 | 一致 | 先方のみ | 当方のみ |", "|---|---|---|---:|---:|---:|"]
    detail = []
    a_bad = 0

    def compare(nid, ref, label, ref_pairs):
        nonlocal a_bad
        ours = pairs_of[nid].get(ref, set())
        if not ours:
            return
        only_ref, only_ours = ref_pairs - ours, ours - ref_pairs
        badge = next((ln["badge"] for ln in nets[nid]["lines"] if ln["ref"] == ref), ref)
        md.append(f"| {nets[nid]['name_ja']} | {badge} | {label} | {len(ref_pairs & ours)} | {len(only_ref)} | {len(only_ours)} |")
        if only_ref or only_ours:
            a_bad += bool(only_ref)
            detail.append(f"- {nets[nid]['name_ja']} {badge}（{label}）: "
                          + ("先方のみ " + "、".join("–".join(sorted(p)) for p in sorted(only_ref, key=sorted)) if only_ref else "")
                          + (" ／ " if only_ref and only_ours else "")
                          + ("当方のみ " + "、".join("–".join(sorted(p)) for p in sorted(only_ours, key=sorted)) if only_ours else ""))

    for nid in ("shanghai", "guangzhou", "shenzhen"):
        p = ROOT / "raw" / nid / "bendibao_timetable.json"
        if not p.exists():
            continue
        ref_pairs = defaultdict(set)
        for k, page in load(p).items():
            if k.startswith("_"):
                continue
            refs = bendibao_refs(page["title"])
            for panel in page["panels"].values():
                for t in panel["tables"]:
                    names = [BT.nkey(r[0]) for r in t["rows"] if r and r[0]]
                    for a, b in zip(names, names[1:]):
                        if a != b:
                            for ref in refs:
                                ref_pairs[ref].add(frozenset((a, b)))
        if nid == "shenzhen":  # 本地宝は 2号線・8号線を 1 ページにまとめているので、当方の 2 路線の和と比べる
            both = ref_pairs.pop("2", set()) | ref_pairs.pop("8", set())
            pairs_of[nid]["2+8"] = pairs_of[nid]["2"] | pairs_of[nid]["8"]
            ref_pairs["2+8"] = both
        for ref, rp in sorted(ref_pairs.items(), key=lambda t: (len(t[0]), t[0])):
            compare(nid, ref, "本地宝の駅順", rp)

    hk = list(csv.DictReader(open(ROOT / "raw/hongkong/mtr_lines_and_stations.csv", encoding="utf-8-sig")))
    seqs = defaultdict(list)
    for r in hk:
        if r["Line Code"]:
            seqs[(r["Line Code"], r["Direction"])].append((float(r["Sequence"]), BT.nkey(r["Chinese Name"])))
    ref_pairs = defaultdict(set)
    for (line, _d), seq in seqs.items():
        names = [n for _, n in sorted(seq)]
        ref_pairs[line] |= {frozenset(p) for p in zip(names, names[1:])}
    for ref, rp in ref_pairs.items():
        compare("hongkong", ref, "MTR 公式の駅一覧", rp)
    lr = list(csv.DictReader(open(ROOT / "raw/hongkong/light_rail_routes_and_stops.csv", encoding="utf-8-sig")))
    seqs = defaultdict(list)
    for r in lr:
        seqs[(r["Line Code"], r["Direction"])].append((float(r["Sequence"]), BT.nkey(r["Chinese Name"])))
    rp = set()
    for seq in seqs.values():
        names = [n for _, n in sorted(seq)]
        rp |= {frozenset(p) for p in zip(names, names[1:]) if p[0] != p[1]}
    compare("hongkong", "LR", "輕鐵 公式の路線・停留所一覧", rp)
    md += [""] + (detail or ["- 食い違いなし"]) + [""]

    # ---------------------------------------------------------------- B. 路線の長さ・駅数
    md += ["## B. 路線の長さ・駅数（中国語版 Wikipedia の情報欄）", "",
           "当方の長さ＝駅間の線路沿いの距離の和（支線を含む。車庫線は含まない）。8% 以上の差・駅数の違いに印（※）。", "",
           "| 路線網 | 路線 | 長さ 当方（km） | Wikipedia（km） | 差 | 駅数 当方 | Wikipedia | |", "|---|---|---:|---:|---:|---:|---:|---|"]
    len_err, b_flags = [], []
    for nid, net in nets.items():
        dist = defaultdict(float)
        for r in rows[nid]:
            dist[r["ref"]] += float(r["dist_m"]) / 1000
        for ln in net["lines"]:
            p = ROOT / "raw" / nid / "wiki_lines" / f"{ln['ref']}.wikitext"
            if not p.exists():
                continue
            w = p.read_text(encoding="utf-8")
            wl = first_num(wiki_field(w, ("linelength_km", "linelength", "length")))
            ws = first_num(wiki_field(w, ("stations",)))
            ours_len, ours_st = dist.get(ln["ref"], 0), len(ln["stations"])
            e = ours_len / wl - 1 if wl else None
            mark = []
            if e is not None:
                len_err.append(abs(e))
                if abs(e) >= 0.08:
                    mark.append("長さ")
            if ws and int(ws) != ours_st:
                mark.append("駅数")
            if mark:
                b_flags.append(f"{net['name_ja']} {ln['badge']}")
            md.append(f"| {net['name_ja']} | {ln['badge']} | {ours_len:.1f} | {wl if wl else '—'} | "
                      f"{f'{e * 100:+.1f}%' if e is not None else '—'} | {ours_st} | {int(ws) if ws else '—'} | "
                      f"{'※' + '・'.join(mark) if mark else ''} |")
    md += ["", f"- 長さの差: 中央値 {statistics.median(len_err) * 100:.1f}%、8% 以上 {sum(e >= 0.08 for e in len_err)}/{len(len_err)} 路線", ""]

    # ---------------------------------------------------------------- C. 所要時間（情報源どうし）
    md += ["## C. 所要時間を情報源どうしで比べる", ""]
    # C1. OSM の運転系統の所要時間 ↔ 最終値（その路線を OSM 以外で作った場合は独立の照合）
    md += ["### C1. OSM の全線所要時間（duration タグ）と最終値", "",
           "最終値を OSM 以外（実測・公表値）で作った路線だけ。OSM は誰でも書き込めるので、大きな差は OSM 側の誤りのこともある。", "",
           "| 路線網 | 系統 | OSM（分） | 最終値（分） | 差 | 最終値の根拠 |", "|---|---|---:|---:|---:|---|"]
    c_err = []
    for nid, net in nets.items():
        segs = {(r["line"], frozenset((r["from"], r["to"]))): r for r in rows[nid]}
        final = {k: float(r["final_min"]) for k, r in segs.items()}
        for lid, lst in BT.osm_totals(nid, net, segs).items():
            src = next(r["source"] for k, r in segs.items() if k[0] == lid)
            if src.startswith(("OSM", "推定")):
                continue
            for keys, mins, name in lst:
                pred = sum(final[(lid, k)] for k in keys)
                e = pred / mins - 1
                c_err.append(abs(e))
                md.append(f"| {net['name_ja']} | {name} | {mins} | {pred:.1f} | {e * 100:+.1f}% | {src[:30]} |")
    if c_err:
        md += ["", f"- 平均 {statistics.mean(c_err) * 100:.1f}%、10% 超 {sum(e > 0.1 for e in c_err)}/{len(c_err)}", ""]

    # C2. MTR の経路検索（最初の区間を除く）↔ 次の電車 API（実際の到着予定）。最終値は両者の平均なので、ここでは元の 2 つを比べる
    net = nets["hongkong"]
    hk_rows = rows["hongkong"]
    model_pair = {frozenset((r["from"], r["to"])): float(r["time_s"]) / 60  # build_times.py と同じ（列車の対応づけの目安）
                  for r in csv.DictReader(open(SEG / "hongkong_segments.csv", encoding="utf-8-sig"))}
    nt, pl = BT.hk_nexttrain(net, model_pair), BT.hk_planner(net)
    md += ["### C2. 香港 MTR: 公式の経路検索（標準所要時間、各検索の最初の区間を除く）と、次の電車 API（実際の到着予定）", "",
           "どちらも公式だが作り方が独立。最終値は両者の平均（食い違う区間は次の電車）。同じ区間どうしの合計で比べる。", "",
           "| 路線 | 区間 | 経路検索（分） | 次の電車（分） | 差 | 最終値（分） |", "|---|---:|---:|---:|---:|---:|"]
    by_line = defaultdict(lambda: [0.0, 0.0, 0, 0.0])
    for r in hk_rows:
        k = frozenset((r["from"], r["to"]))
        if pl.get(k) and len(nt.get(k, [])) >= 4:
            a = by_line[r["ref"]]
            a[0] += statistics.mean(pl[k])
            a[1] += statistics.median(nt[k])
            a[2] += 1
            a[3] += float(r["final_min"])
    nt_err = []
    for ref, (a, b, n, f) in by_line.items():
        if n >= 3:
            nt_err.append(b / a - 1)
            md.append(f"| {ref} | {n} | {a:.1f} | {b:.1f} | {(b / a - 1) * 100:+.1f}% | {f:.1f} |")
    if nt_err:
        md += ["", f"- 次の電車の方が平均 {statistics.mean(nt_err) * 100:+.1f}%（範囲 {min(nt_err) * 100:+.1f}%〜{max(nt_err) * 100:+.1f}%）",
               "- 経路検索の各検索の最初の区間は、次の電車より平均 2.0 分長い（乗車の余裕）。MTR の公表の全線所要時間はこれを含むので、",
               "  最終値（乗車時間）は公表値より 1〜4 分短くなる（南港島線・東涌線で 1 割以上）。", ""]

    # ---------------------------------------------------------------- D. あり得ない値
    md += ["## D. あり得ない値の点検（区間ごと）", "",
           "- 平均速度（距離 ÷ 所要時間）が最高速度の 95% を超える、または 12 km/h 未満（地下鉄・高鉄、800 m 以上の区間）",
           "- 線路沿いの距離が直線距離の 1.6 倍を超える（1 km 以上の区間）", "",
           "| 路線網 | 路線 | 区間 | 距離（m） | 直線（m） | 所要（分） | 平均速度（km/h） | 最高速度 | 指摘 | 根拠 |",
           "|---|---|---|---:|---:|---:|---:|---:|---|---|"]
    d_n = 0
    line_speed = []
    for nid, net in nets.items():
        tot = defaultdict(lambda: [0.0, 0.0])
        for r in rows[nid]:
            d, st, t, vmax = float(r["dist_m"]), float(r["straight_m"]), float(r["final_min"]), float(r["vmax_kmh"])
            v = d / 1000 / (t / 60) if t > 0 else 999
            tot[r["ref"]][0] += d
            tot[r["ref"]][1] += t
            why = []
            if r["mode"] in ("subway", "hsr", "rail", "light_rail") and d >= 800:
                if v > vmax * 0.95:
                    why.append("速すぎる")
                if v < 12:
                    why.append("遅すぎる")
            if d >= 1000 and st > 0 and d / st > 1.6:
                why.append(f"遠回り {d / st:.1f} 倍")
            if why:
                d_n += 1
                md.append(f"| {net['name_ja']} | {r['ref']} | {r['from_name']}–{r['to_name']} | {d:.0f} | {st:.0f} | {t:.1f} | {v:.0f} | {vmax:.0f} | "
                          f"{'・'.join(why)} | {r['source'][:24]} |")
        for ref, (d, t) in tot.items():
            line_speed.append((net["name_ja"], ref, d / 1000, t, d / 1000 / (t / 60)))
    if not d_n:
        md.append("| — | — | 指摘なし | | | | | | | |")
    md += ["", "### 路線ごとの平均速度（停車時間込み）", "", "| 路線網 | 路線 | 長さ（km） | 所要（分） | 平均速度（km/h） |", "|---|---|---:|---:|---:|"]
    for n, ref, d, t, v in sorted(line_speed, key=lambda x: -x[4]):
        md.append(f"| {n} | {ref} | {d:.1f} | {t:.1f} | {v:.1f} |")

    summary = [f"- A. 駅の並び: 先方の隣接が当方に無い路線 {a_bad}（詳細は A）",
               f"- B. 長さ・駅数で印の付いた路線: {len(b_flags)}（{'、'.join(b_flags)}）",
               f"- C1. OSM の全線所要時間との差: 平均 {statistics.mean(c_err) * 100:.1f}%" if c_err else "- C1. 該当なし",
               f"- D. あり得ない値の区間: {d_n}"]
    md[4:4] = ["## まとめ", ""] + summary + [""]
    (SEG / "verification.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
