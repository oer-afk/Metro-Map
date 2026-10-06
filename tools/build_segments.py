"""所要時間機能の下準備: 全路線の駅間距離（線路沿い）と推定所要時間を作り、既知の所要時間と照合する。

使い方:  python tools/build_segments.py [--fetch-speeds]

  --fetch-speeds  各路線の Wikipedia 記事から最高速度を取り直す（raw/<id>/line_speeds.json）

出力（アプリにはまだ使わない。仕様が決まったら site/data に載せる）:
  reports/segments/<id>_segments.csv   路線・駅間ごとの距離（線路沿い・直線）と推定所要時間
  reports/segments/calibration.md      モデルの当てはまり（OSM の全線所要時間との比較）

推定モデル（仕様の下書き docs/travel-time-draft.md）:
  駅間の走行時間 = 台形の速度曲線（加速 a → 最高速度 v → 減速 a）。短い駅間は最高速度に届かない
  所要時間 = 走行時間 + 停車時間（発車駅の停車）。路線ごとの v は Wikipedia の最高速度、無ければ種別の既定値
  a・停車時間・最高速度に対する実効の割合 k は、上海の OSM の全線所要時間（duration タグ）に合わせて決める
"""
from __future__ import annotations

import csv
import heapq
import json
import math
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_city import dist_m  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}
OUT = ROOT / "reports" / "segments"

# 路線の Wikipedia 記事名（最高速度を取るため）
WIKI_PAGE = {
    "shanghai": lambda ln: f"上海轨道交通{ln['ref']}号线" if ln["ref"].isdigit() else "上海轨道交通浦江线",
    "guangzhou": lambda ln: (f"广州地铁{ln['ref']}号线" if ln["ref"].isdigit()
                             else {"GF": "广佛线", "APM": "珠江新城旅客自动输送系统"}[ln["ref"]]),
    "shenzhen": lambda ln: f"深圳地铁{ln['ref']}号线" if ln["ref"].isdigit() else "深圳地铁6号线支线",
    "hongkong": lambda ln: {"LR": "香港輕鐵", "TRAM": "香港電車", "PEAK": "山頂纜車"}.get(ln["ref"], ln["name_orig"]),
    "prd_rail": lambda ln: {"GSG": "广深港高速铁路", "GS": "广深铁路"}[ln["ref"]],
}
# 最高速度が取れないときの既定値（km/h）
DEFAULT_VMAX = {"subway": 80, "light_rail": 70, "tram": 30, "funicular": 25, "hsr": 300, "rail": 160}
# 停車時間（秒）の既定値。地下鉄の値は較正で決める
DWELL = {"subway": None, "light_rail": 25, "tram": 20, "funicular": 60, "hsr": 120, "rail": 90}


# ---------------------------------------------------------------- 最高速度
def parse_speed(w: str) -> float | None:
    """路線記事の情報欄から、営業上の最高速度（km/h）を読む。

    「設計」「預留」「未来」などの括弧書きは除き、「實際運營」の値があればそれを使う。
    """
    for key in ("speed_km/h", "max_speed", "speed", "operationspeed_km/h", "最高速度"):
        for m in re.finditer(r"^\|[ 	]*" + re.escape(key) + r"[ 	]*=[ 	]*(.*)$", w, re.M):
            v = re.sub(r"<ref[^>]*/>|<ref.*?</ref>", "", m.group(1))
            v = re.sub(r"[^<|：:]*(未来|未來)[^<|]*", "", v)
            v = re.sub(r"[（(][^）)]*(预留|預留|设计|設計)[^）)]*[）)]", "", v)
            if not v.strip() or v.strip().startswith("|"):
                continue
            for word in ("实际", "實際"):
                if word in v:
                    tail = [float(x) for x in re.findall(r"\d{2,3}(?:\.\d)?", v.split(word)[-1])]
                    if tail:
                        return max(tail)
            nums = [float(x) for x in re.findall(r"\d{2,3}(?:\.\d)?", v)]
            if nums:
                return max(nums)
    return None


def fetch_speed(page: str) -> float | None:
    r = requests.get("https://zh.wikipedia.org/w/api.php",
                     params={"action": "parse", "page": page, "prop": "wikitext", "format": "json", "redirects": 1},
                     headers=HEADERS, timeout=60)
    return parse_speed(r.json().get("parse", {}).get("wikitext", {}).get("*", ""))


def load_speeds(net: dict, refetch: bool) -> dict:
    """路線ごとの最高速度。保存済みの路線記事（raw/<id>/wiki_lines/）があればそれを読み、
    無ければ Wikipedia から取る。取れない路線は overrides/line_speeds.json で補う。"""
    p = ROOT / "raw" / net["id"] / "line_speeds.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    over = json.loads((ROOT / "overrides/line_speeds.json").read_text(encoding="utf-8")).get(net["id"], {})
    speeds = {}
    for ln in net["lines"]:
        page = WIKI_PAGE[net["id"]](ln)
        cached = ROOT / "raw" / net["id"] / "wiki_lines" / f"{ln['ref']}.wikitext"
        if cached.exists():
            v, src = parse_speed(cached.read_text(encoding="utf-8")), "wiki_lines"
        elif refetch or ln["ref"] not in old:
            try:
                v, src = fetch_speed(page), "wikipedia"
            except Exception as e:  # noqa: BLE001
                print(f"  {page}: {type(e).__name__}", file=sys.stderr)
                v, src = None, "wikipedia"
            time.sleep(0.7)
        else:
            v, src = old[ln["ref"]].get("vmax_kmh"), old[ln["ref"]].get("src", "wikipedia")
        if v is None and ln["ref"] in over:
            v, src = over[ln["ref"]]["vmax_kmh"], "overrides/line_speeds.json"
        speeds[ln["ref"]] = {"page": page, "vmax_kmh": v, "src": src}
    p.write_text(json.dumps(speeds, ensure_ascii=False, indent=2), encoding="utf-8")
    return speeds


# ---------------------------------------------------------------- 線路沿いの距離
def track_graph(geometry):
    """折れ線群を、約 50 m 間隔の点のグラフにする。

    折れ線に沿って隣の点とつなぐほか、別の折れ線の点が 35 m 以内ならつなぐ（上下線が別に描かれた区間、
    間引きで生じた切れ目、T 字の分岐）。さらに折れ線の端は 150 m 以内の点とつなぐ（線路データの細切れ）。
    """
    from build_city import densify, Grid

    pts, adj = [], defaultdict(list)
    owner = []
    for i, pl in enumerate(geometry):
        dense = densify([tuple(p) for p in pl], 50)
        base = len(pts)
        pts += dense
        owner += [i] * len(dense)
        for k in range(len(dense) - 1):
            d = dist_m(dense[k], dense[k + 1])
            adj[base + k].append((base + k + 1, d))
            adj[base + k + 1].append((base + k, d))
    cell = 0.002
    grid = defaultdict(list)
    for idx, p in enumerate(pts):
        grid[(int(p[0] / cell), int(p[1] / cell))].append(idx)

    def near(idx, r):
        p = pts[idx]
        ci, cj = int(p[0] / cell), int(p[1] / cell)
        span = 1 if r <= 220 else 2
        for di in range(-span, span + 1):
            for dj in range(-span, span + 1):
                for j in grid.get((ci + di, cj + dj), ()):
                    if owner[j] != owner[idx]:
                        d = dist_m(p, pts[j])
                        if d <= r:
                            yield j, d

    ends = set()
    pos = 0
    for pl_i, pl in enumerate(geometry):
        n = sum(1 for o in owner if o == pl_i)
        ends |= {pos, pos + n - 1}
        pos += n
    for idx in range(len(pts)):
        for j, d in near(idx, 150 if idx in ends else 35):
            adj[idx].append((j, d))
            adj[j].append((idx, d))
    return adj, pts


def along_track(adj, pts, a, b):
    """駅 a・b に最も近い点の間の、グラフ上の最短距離（駅から点までの距離を足す）。"""
    if not pts:
        return None
    ia = min(range(len(pts)), key=lambda i: dist_m(a, pts[i]))
    ib = min(range(len(pts)), key=lambda i: dist_m(b, pts[i]))
    if dist_m(a, pts[ia]) > 500 or dist_m(b, pts[ib]) > 500:
        return None
    dist = {ia: 0.0}
    pq = [(0.0, ia)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == ib:
            return d + dist_m(a, pts[ia]) + dist_m(b, pts[ib])
        if d > dist.get(u, 1e18):
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, 1e18):
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return None


# ---------------------------------------------------------------- 時間モデル
def run_time(d: float, vmax_ms: float, acc: float) -> float:
    d_acc = vmax_ms ** 2 / (2 * acc)
    if d >= 2 * d_acc:
        return 2 * vmax_ms / acc + (d - 2 * d_acc) / vmax_ms
    return 2 * math.sqrt(d / acc)


def main_length(sts: list, branches: list) -> int:
    """駅の並び（本線＋支線で初めて出る駅）のうち、本線の駅数。

    build_city.py は、支線ごとに「本線・先の支線に無い駅」（1 駅以上）を並びの末尾に足す（向きは運転系統の向き）。
    両端が本線につながる支線（香港の電車・輕鐵）や、本線と離れた区間（広州 12号線の西段）もあるので、
    支線の駅数からは逆算しない。先頭 m 駅を本線としたとき、支線ごとに足される駅の組が並びの残りと
    順に一致する m のうち、最も小さいものを本線の駅数とする（大きい m は支線の駅を本線に含めてしまう）。
    """
    for m in range(1, len(sts) + 1):
        seen, pos, ok = set(sts[:m]), m, True
        for b in branches:
            ex = [x for x in dict.fromkeys(b) if x not in seen]
            if not ex or set(sts[pos:pos + len(ex)]) != set(ex):
                ok = False
                break
            seen |= set(ex)
            pos += len(ex)
        if ok and pos == len(sts):
            return m
    return max(1, len(sts) - sum(len(b) - 1 for b in branches))


def line_pairs(ln: dict) -> list[tuple[str, str]]:
    """路線の隣り合う駅の組（本線・支線・環状線の最後と最初）。"""
    sts = ln["stations"]
    branches = ln.get("branches", [])
    main_len = main_length(sts, branches)
    main = sts[:main_len]
    pairs = list(zip(main, main[1:]))
    if ln.get("loop"):
        pairs.append((main[-1], main[0]))
    for br in branches:
        pairs += list(zip(br, br[1:]))
    return pairs


def main() -> None:
    refetch = "--fetch-speeds" in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    cities = json.loads((ROOT / "site" / "data" / "cities.json").read_text(encoding="utf-8"))
    nets = {c["id"]: json.loads((ROOT / "site" / "data" / c["file"]).read_text(encoding="utf-8")) for c in cities}

    # 1) 全路線の駅間距離
    seg_rows = {}
    speeds = {}
    for nid, net in nets.items():
        speeds[nid] = load_speeds(net, refetch)
        st = {s["id"]: s for s in net["stations"]}
        rows = []
        for ln in net["lines"]:
            adj, gpts = track_graph(ln["geometry"])
            for a, b in line_pairs(ln):
                pa, pb = (st[a]["lat"], st[a]["lon"]), (st[b]["lat"], st[b]["lon"])
                straight = dist_m(pa, pb)
                d = along_track(adj, gpts, pa, pb)
                method = "線路沿い"
                if d is None or d < straight * 0.95 or d > straight * 3:
                    d, method = straight * 1.15, "直線×1.15（線路がつながらない区間）"
                rows.append({"line": ln["id"], "ref": ln["ref"], "mode": ln["mode"], "from": a, "to": b,
                             "from_name": st[a]["name_orig"], "to_name": st[b]["name_orig"],
                             "dist_m": round(d), "straight_m": round(straight), "method": method})
        seg_rows[nid] = rows
        print(f"{nid}: {len(rows)} segments, fallback {sum(1 for r in rows if r['method'] != '線路沿い')}")

    # 2) 較正: 上海の OSM 全線所要時間（duration）に、加速度・停車時間・実効速度の割合を合わせる
    routes = json.loads((ROOT / "raw" / "shanghai" / "routes.json").read_text(encoding="utf-8"))
    sh = nets["shanghai"]
    st_sh = {s["id"]: s for s in sh["stations"]}
    by_ref = {ln["ref"]: ln for ln in sh["lines"]}
    seg_by = {(r["ref"], frozenset((r["from"], r["to"]))): r["dist_m"] for r in seg_rows["shanghai"]}
    name2id = {s["name_orig"]: s["id"] for s in sh["stations"]}
    samples = []  # (ref, 区間の駅間距離のリスト, OSM の分, 名前)
    els = {(e["type"], e["id"]): e for e in routes["elements"]}
    for e in routes["elements"]:
        t = e.get("tags", {})
        if e["type"] != "relation" or t.get("type") != "route" or not t.get("duration") or t.get("ref") not in by_ref:
            continue
        mm = re.fullmatch(r"(?:(\d+):)?(\d+)(?::(\d+))?", t["duration"].strip())
        if not mm:
            continue
        minutes = int(mm.group(1) or 0) * 60 + int(mm.group(2)) + (int(mm.group(3)) / 60 if mm.group(3) else 0)
        seq = []
        for m in e["members"]:
            if m["type"] == "node" and m["role"].startswith("stop") and ("node", m["ref"]) in els:
                nm = els[("node", m["ref"])]["tags"].get("name", "")
                sid = name2id.get(nm) or name2id.get(nm.replace("・", "·"))
                if sid and (not seq or seq[-1] != sid):
                    seq.append(sid)
        dists = [seg_by.get((t["ref"], frozenset(p))) for p in zip(seq, seq[1:])]
        if len(seq) >= 3 and all(dists) and minutes >= 5:
            samples.append((t["ref"], dists, minutes, t.get("name")))

    def predict(dists, vmax_kmh, acc, dwell, k):
        v = vmax_kmh * k / 3.6
        return (sum(run_time(d, v, acc) for d in dists) + dwell * (len(dists) - 1)) / 60

    vmax_of = lambda nid, ln: (speeds[nid].get(ln["ref"], {}).get("vmax_kmh") or DEFAULT_VMAX.get(ln["mode"], 80))  # noqa: E731
    def fit(smp):
        best = None
        for acc in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            for dwell in range(20, 75, 5):
                for k in (0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0):
                    err = [predict(ds, vmax_of("shanghai", by_ref[ref]), acc, dwell, k) / mins - 1 for ref, ds, mins, _ in smp]
                    score = sum(x * x for x in err)
                    if best is None or score < best[0]:
                        best = (score, acc, dwell, k, err)
        return best

    # 1 回目の当てはめで誤差が 40% を超える系統は、OSM の値が不自然とみなして除く（区間運転に全線の値など）
    _, a0, d0, k0, e0 = fit(samples)
    dropped = [smp for smp, e in zip(samples, e0) if abs(e) > 0.4]
    samples = [smp for smp, e in zip(samples, e0) if abs(e) <= 0.4]
    _, ACC, DW, K, errs = fit(samples)

    md = ["# 所要時間モデルの較正（上海・OSM の全線所要時間との比較）", "",
          f"- 比較に使えた運転系統: {len(samples)}（OSM の duration タグがあり、駅間がすべて求まったもの）",
          f"- 除外した系統: {len(dropped)}（1 回目の当てはめで誤差 40% 超。OSM の値が不自然なもの）: "
          + "、".join(f"{n}（OSM {m:.0f} 分）" for _, _, m, n in dropped),
          f"- 当てはめた値: 加速度・減速度 {ACC} m/s²、停車時間 {DW} 秒、最高速度に対する実効の割合 {K}",
          f"- 誤差: 平均 {sum(abs(x) for x in errs) / len(errs) * 100:.1f}%、最大 {max(abs(x) for x in errs) * 100:.1f}%", "",
          "| 系統 | 最高速度 | 駅数 | OSM（分） | 推定（分） | 差 |", "|---|---:|---:|---:|---:|---:|"]
    for (ref, ds, mins, name), e in sorted(zip(samples, errs), key=lambda x: -abs(x[1])):
        p = predict(ds, vmax_of("shanghai", by_ref[ref]), ACC, DW, K)
        md.append(f"| {name} | {vmax_of('shanghai', by_ref[ref]):.0f} | {len(ds) + 1} | {mins:.0f} | {p:.1f} | {e * 100:+.0f}% |")

    # 3) 全路線の推定所要時間（地下鉄は較正値、その他は種別の既定値）
    total = 0
    for nid, rows in seg_rows.items():
        net = nets[nid]
        lines = {ln["id"]: ln for ln in net["lines"]}
        for r in rows:
            ln = lines[r["line"]]
            v = vmax_of(nid, ln)
            acc = ACC if r["mode"] in ("subway", "light_rail") else (0.5 if r["mode"] in ("hsr", "rail") else 0.8)
            k = K if r["mode"] in ("subway",) else 0.9
            dw = DW if DWELL.get(r["mode"]) is None else DWELL[r["mode"]]
            r["vmax_kmh"] = v
            r["run_s"] = round(run_time(r["dist_m"], v * k / 3.6, acc))
            r["dwell_s"] = dw
            r["time_s"] = r["run_s"] + dw
        with (OUT / f"{nid}_segments.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["line", "ref", "mode", "from", "to", "from_name", "to_name", "dist_m",
                                              "straight_m", "method", "vmax_kmh", "run_s", "dwell_s", "time_s"])
            w.writeheader()
            w.writerows(rows)
        total += len(rows)
    md += ["", "## 路線ごとの最高速度（Wikipedia の路線記事から。取れない路線は種別の既定値）", "",
           "| 路線網 | 路線 | 記事 | 最高速度 |", "|---|---|---|---:|"]
    for nid, sp in speeds.items():
        for ref, v in sp.items():
            md.append(f"| {nets[nid]['name_ja']} | {ref} | {v['page']} | {v['vmax_kmh'] or '（既定値）'} |")
    (OUT / "calibration.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md[:5]))
    print(f"segments total: {total}")


if __name__ == "__main__":
    main()
