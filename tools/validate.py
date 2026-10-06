"""表示データの検証（仕様書 6.3）。結果を reports/<city>_validation.md に書く。

使い方:  python tools/validate.py shanghai

照合内容:
  - 路線数・各路線の駅数・駅名を、Wikipedia の駅一覧（営業中のみ）と照合
  - 駅の点が自路線の線形から離れすぎていないか
  - 改称の適用状況、開業前の駅・路線が混ざっていないか
  - 路線色（OSM 採用値）と Wikipedia の色の差
  - 付録 A（確認済み）の所属路線と OSM の結果の差
  - 未確認の駅数
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textconv  # noqa: E402
from build_city import point_polyline_dist_m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# Windows のコンソール（CP932）でも簡体字を出力できるようにする
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
FAR_FROM_LINE_M = 150


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def key(name: str) -> str:
    """簡体・繁体の揺れを吸収した比較用キー（Wikipedia の本文に繁体字の駅名が混じるため）。"""
    # 簡体字にそろえ、異体字（荔／茘）と末尾の「站」の有無の差も吸収する
    s = textconv.to_simplified(textconv.normalize_orig(name)).removesuffix("站")
    return s.translate(VARIANTS)


VARIANTS = str.maketrans({"茘": "荔"})


def hex_dist(a: str, b: str) -> float:
    ra = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    rb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return sum((x - y) ** 2 for x, y in zip(ra, rb)) ** 0.5


def main() -> None:
    city = sys.argv[1]
    cfg = load(ROOT / "config" / f"{city}.json")
    data = load(ROOT / "site" / "data" / f"{city}.json")
    build = load(ROOT / "reports" / f"{city}_build.json")
    raw = ROOT / "raw" / city
    st = {s["id"]: s for s in data["stations"]}
    name_of = {s["id"]: s["name_orig"] for s in data["stations"]}
    ref_line = {ln["ref"]: ln for ln in data["lines"]}
    ref_of = {ln["id"]: ln["ref"] for ln in data["lines"]}

    def lname(ref: str) -> str:
        ref = ref_of.get(ref, ref)  # 路線 ID（sh_9）でも ref（9）でも受ける
        return f"{ref}号線" if ref.isdigit() else ref

    ref_rows = []
    with (raw / "reference_stations.csv").open(encoding="utf-8") as f:
        ref_rows = list(csv.DictReader(f))
    ref_by_line: dict[str, list[str]] = {}
    not_yet: dict[str, list[str]] = {}
    for r in ref_rows:
        nm = textconv.normalize_orig(r["name"])
        (ref_by_line if r["operating"] == "1" else not_yet).setdefault(r["line"], [])
        if r["operating"] == "1":
            if nm not in ref_by_line[r["line"]]:
                ref_by_line[r["line"]].append(nm)
        else:
            not_yet[r["line"]].append(nm)

    md = [f"# 検証結果：{data['name_ja']}", ""]
    md.append(f"- OSM 取得日: {data['source']['extracted']}　/　Wikipedia 取得: "
              f"{load(raw / 'wikipedia_zh.meta.json')['fetched_at'][:10]}（中国語版「{load(raw / 'wikipedia_zh.meta.json')['page']}」）")
    md.append(f"- 路線数: OSM {len(data['lines'])} ／ Wikipedia（営業中）{len(ref_by_line)}")
    md.append(f"- 駅数: {len(data['stations'])}（うち確認済み {sum(s['verified'] for s in data['stations'])}、"
              f"**未確認 {sum(not s['verified'] for s in data['stations'])}**）")
    md.append("")

    # ---- 路線ごとの駅数・駅名
    md += ["## 路線ごとの駅数と駅名の差", "",
           "| 路線 | OSM | Wikipedia | OSM のみ | Wikipedia のみ |", "|---|---:|---:|---|---|"]
    issues = 0
    notes = []
    for ref in sorted(set(ref_line) | set(ref_by_line), key=lambda r: (not r.isdigit(), int(r) if r.isdigit() else 0, r)):
        osm = [name_of[s] for s in ref_line[ref]["stations"]] if ref in ref_line else []
        wiki = ref_by_line.get(ref, [])
        osm_k = {key(n) for n in osm}
        wiki_k = {key(n) for n in wiki}
        only_osm = [n for n in osm if key(n) not in wiki_k]
        only_wiki = [n for n in wiki if key(n) not in osm_k]
        note = cfg.get("validation_notes", {}).get(ref)  # 理由の分かっている差（config に書く）
        if (only_osm or only_wiki or len(osm) != len(wiki)) and not note:
            issues += 1
        mark = "" if not (only_osm or only_wiki) else (" ※" if note else " ⚠")
        if note:
            notes.append(f"- ※ {lname(ref)}: {note}")
        md.append(f"| {ref}{mark} | {len(osm)} | {len(wiki)} | {'、'.join(only_osm) or '—'} | {'、'.join(only_wiki) or '—'} |")
    md.append("")
    md += notes + ([""] if notes else [])
    md.append(f"差のある路線（理由の分かっているものを除く）: {issues}")
    md.append("")

    # ---- 開業前の駅が混ざっていないか
    md += ["## 開業前（建設中・計画）の駅の混入", ""]
    mixed = []
    for ref, names in not_yet.items():
        osm = {key(name_of[s]) for s in ref_line[ref]["stations"]} if ref in ref_line else set()
        for n in names:
            if key(n) in osm:
                mixed.append(f"{lname(ref)} {n}")
    md.append("- 混入なし" if not mixed else "- 混入あり: " + "、".join(mixed))
    md.append(f"- Wikipedia 上で建設中・計画として載っている既存路線の駅: "
              + ("、".join(f"{lname(k)} {len(v)}駅" for k, v in not_yet.items()) or "なし"))
    md.append("- 営業前の路線は、OSM の取得対象（営業中の路線リレーション）に入っていないことを上の路線数の一致で確認する。")
    md.append("")

    # ---- 駅と線形の距離
    md += ["## 駅の点と自路線の線形の距離", "", f"{FAR_FROM_LINE_M} m 超を列挙。", ""]
    far = []
    for ln in data["lines"]:
        geom = ln["geometry"]
        for sid in ln["stations"]:
            s = st[sid]
            d = point_polyline_dist_m((s["lat"], s["lon"]), geom)
            if d > FAR_FROM_LINE_M:
                far.append((lname(ln["id"]), s["name_orig"], round(d), "乗換駅" if len(s["lines"]) > 1 else "⚠"))
    md.append("乗換駅は複数路線の駅を 1 点に統合しているため、各路線のホームから離れることがある（仕様どおり）。")
    md.append("")
    if far:
        md += ["| 路線 | 駅 | 距離 (m) | 種別 |", "|---|---|---:|---|"] + [f"| {a} | {b} | {c} | {t} |" for a, b, c, t in far]
    else:
        md.append("- 該当なし")
    md.append("")

    # ---- 営業状況の上書き
    so = build.get("status_overrides", {})
    md += ["## 営業状況の上書き（overrides/station_status_*.json）", ""]
    for x in so.get("exclude_stops", []):
        md.append(f"- 除外: {lname(x['line'])} {x['name']} — {x['reason']}")
    for x in so.get("add_stops", []):
        where = f"{'〜'.join(x['between'])} 間" if "between" in x else f"{x['after']} の先"
        md.append(f"- 追加: {lname(x['line'])} {x['name']}（{where}） — {x['reason']}")
    if not so.get("exclude_stops") and not so.get("add_stops"):
        md.append("- なし")
    md.append("")

    # ---- 改称
    md += ["## 駅名の改称", ""]
    ren = build.get("renames_applied", [])
    md.append("- OSM に旧名が残っていたため置き換えた駅: " + ("、".join(ren) if ren else "なし"))
    all_names = {s["name_orig"] for s in data["stations"]}
    for old, new in cfg.get("rename_checks", []):  # 既知の改称が反映されているか（config に書く）
        md.append(f"- {old} → {new}: データ上は「{new if new in all_names else '（なし）'}」"
                  f"{'、旧名なし' if old not in all_names else '、⚠旧名が残存'}")
    md.append("")

    # ---- 色
    md += ["## 路線色", "",
           "OSM の colour（運営会社の Pantone 指定の換算値とみられる）を採用。Wikipedia の色（路線図からの採色）と比べて差が大きいものに ⚠。", "",
           "| 路線 | 採用（OSM） | Wikipedia | 差 |", "|---|---|---|---|"]
    rc = load(raw / "reference_colors.json") if (raw / "reference_colors.json").exists() else {}
    for ln in data["lines"]:
        w = rc.get(ln["ref"])
        d = hex_dist(ln["color"], w) if w else None
        flag = " ⚠" if d is not None and d > 60 else ""
        md.append(f"| {ln['ref']} | {ln['color']} | {w or '—'} | {round(d) if d is not None else '—'}{flag} |")
    sup = build.get("color_supplemented", [])
    md.append("")
    md.append("- 補完した色: " + ("、".join(f"{c['line']} {c['color']}" for c in sup) if sup else "なし（全路線 OSM に colour あり）"))
    md.append("")

    # ---- 付録 A の所属路線
    md += ["## 確認済み一覧の所属路線と OSM の差", ""]
    by_name = {s["name_orig"]: s for s in data["stations"]}
    rows = []
    vpath = ROOT / "overrides" / cfg["verified_csv"]
    vrows = list(csv.DictReader(vpath.open(encoding="utf-8"))) if vpath.exists() else []
    if not vrows:
        md.append("- 確認済みの一覧はまだ無い（本人確認待ち）")
    for r in vrows:
        if True:
            nm = textconv.normalize_orig(r["原表記"])
            s = by_name.get(nm)
            ap = r["路線"].split("/")
            if s is None:
                rows.append(f"| {nm} | {r['路線']} | （OSM に無し） |")
            elif sorted(ap) != sorted(ref_of[x] for x in s["lines"]):
                rows.append(f"| {nm} | {r['路線']} | {'/'.join(ref_of[x] for x in s['lines'])} |")
    if vrows:
        md += (["| 駅 | 確認済み一覧 | OSM |", "|---|---|---|"] + rows) if rows else ["- 差なし"]
    md.append("")

    # ---- 付録 A と機械変換
    mv = build.get("machine_vs_verified", [])
    md += ["## 確認済み一覧と機械変換の差", "",
           f"- 差のあった駅: {len(mv)}（詳細は `{city}_machine_vs_verified.csv`）", ""]

    # ---- 統合と位置
    md += ["## 駅の統合・位置", ""]
    md.append(f"- 同名で 800 m 以上離れ別駅として残したもの: {build.get('same_name_split') or 'なし'}")
    ps = build.get("station_position_source", {})
    md.append(f"- 駅の位置: railway=station の点 {ps.get('station')} 駅、停車位置の平均 {ps.get('stop_position')} 駅")
    md.append(f"- 名前のない停車位置: {len(build.get('unnamed_stops', []))}")
    md.append("")

    out = ROOT / "reports" / f"{city}_validation.md"
    out.write_text("\n".join(md), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
