"""駅間の所要時間を、複数の情報源から路線ごとに精緻化する（所要時間機能の下準備）。

使い方:  python tools/build_times.py

前提: tools/build_segments.py を先に実行（reports/segments/<id>_segments.csv にモデルの推定値）。

情報源（確かなものから順に使う）:
  A. 実測の時刻（駅間ごと）
     - 香港 MTR: 次の列車の到着予定（公式 API）を全駅で何回か取得したもの（raw/hongkong/nexttrain/）
       隣り合う駅で同じ行き先の列車の到着予定の差 ＝ 駅間の走行＋停車
     - 香港 電車・山頂纜車: 運輸署の GTFS の停車時刻（raw/hongkong/gtfs_tram_peak/）
     - 深圳: 公式の各駅の始発・終電時刻（Wikipedia「Module:线路时刻表/深圳地铁」、raw/shenzhen/wiki_timetable.lua）
  B. 路線全体の所要時間（OSM の duration タグ。上海・広州 18号線）→ モデルの配分に係数を掛けて合わせる
  C. どちらも無い路線 → 同じ路線網・同じ種別の路線で求めた係数の中央値
出力:
  reports/segments/<id>_times.csv   区間ごとの最終値と情報源
  reports/segments/accuracy.md      路線ごとの情報源と、実測がある路線での誤差の検証
"""
from __future__ import annotations

import csv
import glob
import itertools
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_city import dist_m  # noqa: E402
import textconv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEG = ROOT / "reports" / "segments"
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def robust(vals: list[float]) -> float:
    """外れ値（中央値から 1.5 分以上・5 割以上離れた値）を除いた平均。分単位の丸めは平均でならす。"""
    med = statistics.median(vals)
    keep = [v for v in vals if abs(v - med) <= max(1.5, med * 0.5)]
    return statistics.mean(keep or vals)


VARIANTS = str.maketrans({"茘": "荔"})


def vkey(name: str) -> str:
    """異体字（荔／茘）の違いを吸収した駅名の比較用キー"""
    return name.translate(VARIANTS)


def load(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def hm(s: str) -> int | None:
    m = re.match(r"\s*(\d{1,2}):(\d{2})", s or "")
    if not m:
        return None
    h, mm = int(m.group(1)), int(m.group(2))
    return (h + (24 if h < 4 else 0)) * 60 + mm


# ---------------------------------------------------------------- A. 実測
def hk_nexttrain(net, model_pair=None) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（香港 MTR）"""
    rows = list(csv.DictReader(open(ROOT / "raw/hongkong/mtr_lines_and_stations.csv", encoding="utf-8-sig")))
    by_name = {vkey(s["name_orig"]): s["id"] for s in net["stations"] if s["kind"] == "metro"}
    code2id = {r["Station Code"]: by_name.get(vkey(r["Chinese Name"])) for r in rows if r["Line Code"]}
    seqs = defaultdict(list)
    for r in rows:
        if r["Line Code"]:
            seqs[(r["Line Code"], r["Direction"])].append((float(r["Sequence"]), r["Station Code"]))
    out = defaultdict(list)
    for path in sorted(glob.glob(str(ROOT / "raw/hongkong/nexttrain/*.json"))):
        snap = load(path)["responses"]
        for (line, d), seq in seqs.items():
            # 駅一覧の方向 UT/DT は API の UP/DOWN に対応し、並び順が進行方向の順（支線は LMC-UT など）
            key = "UP" if d.endswith("UT") else "DOWN"
            codes = [c for _, c in sorted(seq)]
            for a, b in zip(codes, codes[1:]):
                ra = snap.get(f"{line}-{a}", {}).get("data", {}).get(f"{line}-{a}", {})
                rb = snap.get(f"{line}-{b}", {}).get("data", {}).get(f"{line}-{b}", {})
                if not (code2id.get(a) and code2id.get(b)):
                    continue
                exp = (model_pair or {}).get(frozenset((code2id[a], code2id[b]))) or 3.0
                ta = [(hm(x["time"][11:16]), x["dest"]) for x in ra.get(key, [])]
                tb = [(hm(x["time"][11:16]), x["dest"]) for x in rb.get(key, [])]
                if len(ta) < 2 or len(tb) < 2:
                    continue
                # 並びの照合: A 駅の到着予定の列を Δ 分ずらしたとき、B 駅の列（同じ行き先）と最も多く重なる Δ を採る。
                # 1 本ずつ「近い差」を選ぶと、運転間隔が短い路線で前の列車と取り違えて短めに偏るため。
                best = None
                lo, hi = max(1, int(exp * 0.4)), int(exp * 2.2) + 2
                for dlt in range(lo, hi + 1):
                    hits = sum(1 for t, dst in ta if any(abs(u - t - dlt) <= 0 and dd == dst for u, dd in tb))
                    near = sum(1 for t, dst in ta if any(abs(u - t - dlt) <= 1 and dd == dst for u, dd in tb))
                    score = (hits + 0.5 * near, -abs(dlt - exp))
                    if best is None or score > best[0]:
                        best = (score, dlt)
                (score, _), dlt = best
                if score < 1.5:
                    continue  # 重なりが少ない（列の取得時刻のずれ等）ときは使わない
                # 重なった組の差の平均（丸めの向きの違いで、分未満の値がならされる）
                pairs = [u - t for t, dst in ta for u, dd in tb if dd == dst and abs(u - t - dlt) <= 1]
                out[frozenset((code2id[a], code2id[b]))].append(statistics.mean(pairs))
    return out


def hk_lrt(net, model_pair=None) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（香港 輕鐵。次の電車の公式 API を、MTR と同じ「並びの照合」で駅間時間に直す）"""
    rows = list(csv.DictReader(open(ROOT / "raw/hongkong/light_rail_routes_and_stops.csv", encoding="utf-8-sig")))
    by_name = {vkey(s["name_orig"]): s["id"] for s in net["stations"] if s["kind"] == "light_rail"}
    id2st = {r["Stop ID"]: by_name.get(vkey(r["Chinese Name"])) for r in rows}
    seqs = defaultdict(list)
    for r in rows:
        seqs[(r["Line Code"], r["Direction"])].append((float(r["Sequence"]), r["Stop ID"]))
    out = defaultdict(list)

    def arrivals(resp, route):
        base = resp.get("system_time", "")
        t0 = hm(base[11:16]) if base else None
        if t0 is None:
            return []
        res = []
        for pf in resp.get("platform_list", []):
            for x in pf.get("route_list", []):
                if x.get("route_no") != route:
                    continue
                txt = x.get("time_en", "")
                m = re.match(r"(\d+)\s*min", txt)
                mins = int(m.group(1)) if m else (0 if txt in ("Arriving", "Departing") else None)
                if mins is not None:
                    res.append((t0 + mins, x.get("dest_en")))
        return res

    for path in sorted(glob.glob(str(ROOT / "raw/hongkong/lrt/*.json"))):
        snap = load(path)["responses"]
        for (route, _d), seq in seqs.items():
            stops = [sid for _, sid in sorted(seq)]
            for a, b in zip(stops, stops[1:]):
                ia, ib = id2st.get(a), id2st.get(b)
                if not (ia and ib) or ia == ib:
                    continue
                ta, tb = arrivals(snap.get(a, {}), route), arrivals(snap.get(b, {}), route)
                if not ta or not tb:
                    continue
                exp = (model_pair or {}).get(frozenset((ia, ib))) or 1.5
                best = None
                for dlt in range(0, int(exp * 2.5) + 3):
                    hits = sum(1 for t, dst in ta if any(u - t == dlt and dd == dst for u, dd in tb))
                    near = sum(1 for t, dst in ta if any(abs(u - t - dlt) <= 1 and dd == dst for u, dd in tb))
                    score = (hits + 0.5 * near, -abs(dlt - exp))
                    if best is None or score > best[0]:
                        best = (score, dlt)
                (score, _), dlt = best
                if score < 1.0:
                    continue
                pairs = [u - t for t, dst in ta for u, dd in tb if dd == dst and abs(u - t - dlt) <= 1]
                if pairs:
                    out[frozenset((ia, ib))].append(max(0.3, statistics.mean(pairs)))
    return out


def hk_planner(net) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（香港 MTR 公式の経路検索の累積時間＝平日朝の標準。上下で 2 件）"""
    rows = list(csv.DictReader(open(ROOT / "raw/hongkong/mtr_lines_and_stations.csv", encoding="utf-8-sig")))
    by_name = {vkey(s["name_orig"]): s["id"] for s in net["stations"] if s["kind"] == "metro"}
    code2id = {r["Station Code"]: by_name.get(vkey(r["Chinese Name"])) for r in rows if r["Line Code"]}
    out = defaultdict(list)
    for seq in load(ROOT / "raw/hongkong/planner.json").values():
        if not seq:
            continue
        for x, y in zip(seq, seq[1:]):
            a, b = code2id.get(x["code"]), code2id.get(y["code"])
            if a and b and y["t"] > x["t"]:
                out[frozenset((a, b))].append(y["t"] - x["t"])
    return out


def hk_gtfs(net) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（香港 電車・山頂纜車、停留所は位置で対応づけ）"""
    d = ROOT / "raw/hongkong/gtfs_tram_peak"
    stops = {s["stop_id"]: (float(s["stop_lat"]), float(s["stop_lon"])) for s in csv.DictReader(open(d / "stops.txt", encoding="utf-8"))}
    ours = [s for s in net["stations"] if s["kind"] in ("tram", "funicular")]

    def nearest(p):
        s = min(ours, key=lambda s: dist_m(p, (s["lat"], s["lon"])))
        return s["id"] if dist_m(p, (s["lat"], s["lon"])) <= 150 else None

    sid = {k: nearest(v) for k, v in stops.items()}
    trips = defaultdict(list)
    for r in csv.DictReader(open(d / "stop_times.txt", encoding="utf-8")):
        trips[r["trip_id"]].append((int(r["stop_sequence"]), r["stop_id"], r["arrival_time"]))
    out = defaultdict(list)
    spans = []  # (停留所 id の並び, 分)。時刻のある停留所から次の時刻のある停留所まで
    for seq in trips.values():
        seq.sort()
        timed = [(i, x) for i, x in enumerate(seq) if x[2]]
        for (i, (_, _, ta)), (j, (_, _, tb)) in zip(timed, timed[1:]):
            ids = [sid.get(x[1]) for x in seq[i:j + 1]]
            if all(ids) and len(set(ids)) == len(ids) and j - i >= 1:
                h1, m1, s1 = map(int, ta.split(":"))
                h2, m2, s2 = map(int, tb.split(":"))
                dt = (h2 * 3600 + m2 * 60 + s2 - h1 * 3600 - m1 * 60 - s1) / 60
                if 0 < dt <= 60:
                    spans.append((ids, dt))
        for (_, a, ta), (_, b, tb) in zip(seq, seq[1:]):
            ia, ib = sid.get(a), sid.get(b)
            if ia and ib and ia != ib and ta and tb:  # 時刻が空の停留所（目安の時刻のみの便）は飛ばす
                h1, m1, s1 = map(int, ta.split(":"))
                h2, m2, s2 = map(int, tb.split(":"))
                dt = (h2 * 3600 + m2 * 60 + s2 - h1 * 3600 - m1 * 60 - s1) / 60
                if 0 < dt <= 20:
                    out[frozenset((ia, ib))].append(dt)
    out["__spans__"] = spans
    return out


def sz_timetable(net) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（深圳、公式の始発・終電時刻）"""
    t = (ROOT / "raw/shenzhen/wiki_timetable.lua").read_text(encoding="utf-8")
    by_name = {s["name_orig"]: s["id"] for s in net["stations"]}
    out = defaultdict(list)
    for b in re.split(r"\n\t\t\{\s*\n\t\t\tline\s*=\s*'", t)[1:]:
        sts = re.findall(r"'([^']+)'", re.search(r"stations\s*=\s*\{(.*?)\}", b, re.S).group(1))
        data = {}
        for m in re.finditer(r"\['([^']+)'\]\s*=\s*(\{.*\})\s*,?\s*$", b, re.M):
            try:
                data[m.group(1)] = json.loads(m.group(2).strip().rstrip(",").replace("{", "[").replace("}", "]").replace("'", '"'))
            except ValueError:
                pass
        for day in (0, 1):
            for kind in (0, 1):
                for d in (0, 1):
                    vals = []
                    for s in sts:
                        try:
                            v = data[s][day][kind]
                            if isinstance(v[0], list):
                                v = v[-1]
                            vals.append(hm(v[d]))
                        except (KeyError, IndexError, TypeError):
                            vals.append(None)
                    for i in range(len(sts) - 1):
                        a, c = (vals[i], vals[i + 1]) if d == 0 else (vals[i + 1], vals[i])
                        ia, ic = by_name.get(sts[i]), by_name.get(sts[i + 1])
                        if a is not None and c is not None and ia and ic and 0 < c - a <= 10:
                            out[frozenset((ia, ic))].append(c - a)
    return out


def nkey(name: str) -> str:
    """駅名の比較用キー（「站」・中黒・空白の違いを吸収）"""
    return re.sub(r"[·・•\s]|站$", "", vkey(name))


def bendibao(net) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（本地宝が転載している各駅の始発・終電の通過時刻。工作日・休息日）

    列ごと（始発／終電 × 方向）に、隣り合う駅の時刻の差をとる。途中駅から出る始発などで時刻が戻る所は、
    差が 0 以下か 10 分を超えるので捨てる。
    """
    p = ROOT / "raw" / net["id"] / "bendibao_timetable.json"
    if not p.exists():
        return {}
    by_name = {}
    for st in net["stations"]:
        if st["kind"] == "metro" or st["kind"] == "light_rail":
            by_name.setdefault(nkey(st["name_orig"]), st["id"])
    out = defaultdict(list)
    for pid, page in load(p).items():
        if pid.startswith("_"):
            continue
        for tab in ("workday", "weekend"):
            for t in page["panels"].get(tab, {}).get("tables", []):
                names = [r[0] for r in t["rows"]]
                ids = [by_name.get(nkey(n)) for n in names]
                for ci, (_kind, dname) in enumerate(t["cols"]):
                    vals = [hm(r[ci + 1]) if len(r) > ci + 1 else None for r in t["rows"]]
                    term = dname.removeprefix("往").removeprefix("开往")
                    rev = bool(names) and nkey(term) == nkey(names[0])  # 1 行目の駅に向かう列は、下から上へ進む
                    for i in range(len(names) - 1):
                        a, c = (vals[i], vals[i + 1]) if not rev else (vals[i + 1], vals[i])
                        if a is not None and c is not None and ids[i] and ids[i + 1] and ids[i] != ids[i + 1] and 0 < c - a <= 10:
                            out[frozenset((ids[i], ids[i + 1]))].append(c - a)
    return out


def rail_12306(net) -> dict:
    """{frozenset(駅 id 2 つ): [分, …]}（高鉄。12306 の列車検索の、隣り合う駅の組の所要時間）

    あわせて reports/segments/prd_rail_od.csv に、全ての駅の組の中央値・最速・本数を書く（経路計算はこちらを使う。
    列車ごとに停車駅が違うため、隣の駅との差を足すと各駅停車の時間になり、実際より長くなる）。
    """
    files = sorted(glob.glob(str(ROOT / "raw/prd_rail/12306_*.json")))
    if not files:
        return {}
    pairs = load(files[-1])["pairs"]

    def key(name):
        return textconv.to_simplified(name).removesuffix("站")

    by_name = {key(s["name_orig"]): s["id"] for s in net["stations"]}
    out = defaultdict(list)
    od_rows = []
    for k, trains in pairs.items():
        x, y = k.split("|")
        mins = [t["min"] for t in trains if 0 < t["min"] < 600]  # 99:59 などの「時刻なし」を除く
        a, b = by_name.get(x), by_name.get(y)
        if not (a and b and mins):
            continue
        od_rows.append({"from": a, "to": b, "from_name": x, "to_name": y, "n": len(mins),
                        "median_min": statistics.median(mins), "fastest_min": min(mins)})
        out[frozenset((a, b))] += mins
    with (SEG / "prd_rail_od.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["from", "to", "from_name", "to_name", "n", "median_min", "fastest_min"])
        w.writeheader()
        w.writerows(od_rows)
    # 隣り合う駅の組だけを返す（隣でない組は segs に無いので統合で使われない）。代表値は中央値
    return {k: [statistics.median(v)] for k, v in out.items()}


# ---------------------------------------------------------------- B. 路線全体の所要時間（OSM）
def osm_totals(nid, net, segs) -> dict:
    """{路線 id: [(区間のリスト, 分)]}。運転系統の停車駅の並びに沿って、モデルの区間を足す対象にする"""
    p = ROOT / "raw" / nid / "routes.json"
    if not p.exists():
        return {}
    routes = load(p)
    els = {(e["type"], e["id"]): e for e in routes["elements"]}
    name2id = {s["name_orig"]: s["id"] for s in net["stations"]}
    ref2line = {ln["ref"]: ln["id"] for ln in net["lines"]}
    out = defaultdict(list)
    for e in routes["elements"]:
        t = e.get("tags", {})
        if e["type"] != "relation" or t.get("type") != "route" or not t.get("duration") or t.get("ref") not in ref2line:
            continue
        mm = re.fullmatch(r"(?:(\d+):)?(\d+)(?::(\d+))?", t["duration"].strip())
        if not mm:
            continue
        minutes = int(mm.group(1) or 0) * 60 + int(mm.group(2))
        seq = []
        for m in e["members"]:
            if m["type"] == "node" and m["role"].startswith("stop") and ("node", m["ref"]) in els:
                sid = name2id.get(els[("node", m["ref"])]["tags"].get("name", "").replace("・", "·"))
                if sid and (not seq or seq[-1] != sid):
                    seq.append(sid)
        lid = ref2line[t["ref"]]
        keys = [frozenset(p) for p in zip(seq, seq[1:])]
        if len(seq) >= 3 and all((lid, k) in segs for k in keys):
            out[lid].append((keys, minutes, t.get("name")))
    return out


def path_keys(lid, segs, net, a_name, b_name):
    """路線 lid の上で、駅名 a から b までたどる区間のキーの並び（支線・環状線も可）。無ければ None"""
    ids = {s["name_orig"]: s["id"] for s in net["stations"] if lid in s["lines"]}  # その路線の駅だけ（屯門の MTR と輕鐵を取り違えない）
    a, b = ids.get(a_name), ids.get(b_name)
    if not a or not b:
        return None
    adj = defaultdict(list)
    for (l, k) in segs:
        if l == lid:
            x, y = tuple(k)
            adj[x].append(y)
            adj[y].append(x)
    prev, queue = {a: None}, [a]
    while queue:
        u = queue.pop(0)
        if u == b:
            break
        for v in adj[u]:
            if v not in prev:
                prev[v] = u
                queue.append(v)
    if b not in prev:
        return None
    keys, u = [], b
    while prev[u] is not None:
        keys.append(frozenset((u, prev[u])))
        u = prev[u]
    return keys


# ---------------------------------------------------------------- モデルの当てはめ（全路線網の地下鉄）
def run_time(d: float, vmax_ms: float, acc: float) -> float:
    """台形の速度曲線で d m を走る秒数（build_segments.py と同じ）"""
    d_acc = vmax_ms ** 2 / (2 * acc)
    if d >= 2 * d_acc:
        return 2 * vmax_ms / acc + (d - 2 * d_acc) / vmax_ms
    return 2 * math.sqrt(d / acc)


def seg_min(r: dict, p: tuple) -> float:
    acc, dwell, k = p
    return (run_time(float(r["dist_m"]), float(r["vmax_kmh"]) * k / 3.6, acc) + dwell) / 60


GRID = list(itertools.product([0.3, 0.4, 0.5, 0.6, 0.8, 1.0], range(0, 65, 5), [0.7, 0.8, 0.9, 1.0]))


def fit_params(anchors: list) -> tuple:
    """地下鉄の駅間モデル（加減速度・停車時間・最高速度の実効割合）を、実測・公表値のある全路線で決める。

    anchors: [(路線網, 路線 id, [区間の行], 正解の分)]
    評価は「1 路線ずつ抜き、同じ路線網の他路線の係数の中央値で推定したときの誤差」の平均（＝実測の無い路線での精度）。
    """
    def loo(p):
        ratio = {(n, l): t / sum(seg_min(r, p) for r in rs) for n, l, rs, t in anchors}
        errs = {}
        for (n, l), x in ratio.items():
            oth = [y for (m, o), y in ratio.items() if m == n and o != l]
            if oth:
                errs[(n, l)] = statistics.median(oth) / x - 1
        return errs
    best = min(GRID, key=lambda p: statistics.mean(abs(e) for e in loo(p).values()))
    return best, loo(best)


# ---------------------------------------------------------------- 統合
def main() -> None:
    cities = load(ROOT / "site/data/cities.json")
    nets = {c["id"]: load(ROOT / "site/data" / c["file"]) for c in cities}
    net_of = nets
    measured_src = {
        # 香港 MTR は公式の経路検索（標準所要時間）を主に使う。次の列車の API は検証用（accuracy.md）
        "hongkong": [("MTR 公式の経路検索（標準所要時間）", hk_planner), ("輕鐵 公式 API（次の電車）", hk_lrt),
                     ("運輸署 GTFS", hk_gtfs)],
        "shenzhen": [("深圳地鉄 公式時刻（始発・終電）", sz_timetable), ("本地宝（公式時刻の転載）", bendibao)],
        "guangzhou": [("本地宝（公式時刻の転載）", bendibao)],
        "shanghai": [("本地宝（公式時刻の転載）", bendibao)],
        "prd_rail": [("中国鉄路 12306 の列車検索（中央値）", rail_12306)],
    }
    md = ["# 所要時間の精緻化: 路線ごとの情報源と精度", ""]
    acc_rows = []
    ref_rows = []  # 公表値との照合（最終値）
    totals_cfg = load(ROOT / "overrides/line_totals.json")
    G = {}
    for nid, net in nets.items():
        rows = list(csv.DictReader(open(SEG / f"{nid}_segments.csv", encoding="utf-8-sig")))
        segs = {(r["line"], frozenset((r["from"], r["to"]))): r for r in rows}
        model = {k: float(r["time_s"]) / 60 for k, r in segs.items()}
        meas = {}
        meas_src = {}
        span_meas = defaultdict(list)  # 路線 id → [(区間のキーの並び, 分, 情報源)]
        model_pair = {k[1]: v for k, v in model.items()}
        for label, fn in measured_src.get(nid, []):
            res = fn(net, model_pair) if fn in (hk_nexttrain, hk_lrt) else fn(net)
            for ids, mins in res.pop("__spans__", []):
                keys = [frozenset(p) for p in zip(ids, ids[1:])]
                for lid in {k[0] for k in segs}:
                    if all((lid, k) in segs for k in keys):
                        span_meas[lid].append((keys, mins, label))
                        break
            for pair, vals in res.items():
                for k in segs:
                    if k[1] == pair and k not in meas:
                        meas[k] = vals
                        meas_src[k] = label
        totals = osm_totals(nid, net, segs)
        lines = {ln["id"]: ln for ln in net["lines"]}
        G[nid] = (rows, segs, model, meas, meas_src, span_meas, totals, lines)

    # 地下鉄のモデルを、全路線網の実測・公表値に当てはめ直す（build_segments.py の較正は上海の OSM だけ）
    anchors = []
    for nid, (rows, segs, model, meas, meas_src, span_meas, totals, lines) in G.items():
        for lid, ln in lines.items():
            if ln["mode"] != "subway" or lid == "hk_drl":  # 迪士尼線は 1 区間で公表値と公式の経路検索が食い違う
                continue
            keys = [k for k in segs if k[0] == lid]
            mk = [k for k in keys if k in meas and meas[k]]
            if len(mk) >= max(3, len(keys) // 3):
                anchors.append((nid, lid, [segs[k] for k in mk], sum(robust(meas[k]) for k in mk)))
                continue
            pub = [t for t in totals_cfg.get(nid, []) if t["line"] == ln["ref"]]
            for t in pub[:1]:
                ks = path_keys(lid, segs, net_of[nid], t["from"], t["to"])
                if ks:
                    anchors.append((nid, lid, [segs[(lid, k)] for k in ks], t["min"]))
            if pub:
                continue
            ok = [(ks, mn) for ks, mn, _ in totals.get(lid, []) if 0.75 <= mn / sum(model[(lid, k)] for k in ks) <= 1.25]
            if ok:
                ks, mn = ok[0]
                anchors.append((nid, lid, [segs[(lid, k)] for k in ks], mn))
    PARAMS, loo_err = fit_params(anchors)
    for nid, (rows, segs, model, *_rest) in G.items():
        for k, r in segs.items():
            if r["mode"] == "subway":
                model[k] = seg_min(r, PARAMS)

    for nid, net in nets.items():
        rows, segs, model, meas, meas_src, span_meas, totals, lines = G[nid]

        # 路線ごとの係数 s（モデルに掛ける値）とその根拠
        scale, basis, rejected = {}, {}, {}
        for lid in lines:
            keys = [k for k in segs if k[0] == lid]
            mk = [k for k in keys if k in meas and len(meas[k]) >= 1]
            prefer = any(t["line"] == lines[lid]["ref"] and t.get("prefer") for t in totals_cfg.get(nid, []))
            if prefer:
                for k in keys:  # 情報源どうしが食い違い、公表値を優先する路線（line_totals.json の prefer）
                    meas.pop(k, None)
                mk = []
            if len(mk) >= max(3, len(keys) // 3):
                scale[lid] = sum(robust(meas[k]) for k in mk) / sum(model[k] for k in mk)
                cnt = defaultdict(int)
                for k in mk:
                    cnt[meas_src[k]] += 1
                srcs = "・".join(f"{a} {n}" for a, n in sorted(cnt.items(), key=lambda t: -t[1])) if len(cnt) > 1 else mk and meas_src[mk[0]]
                basis[lid] = f"実測（{srcs}、{len(mk)}/{len(keys)} 区間）"
            elif any(t["line"] == lines[lid]["ref"] for t in totals_cfg.get(nid, [])):
                rat = []
                for t in totals_cfg[nid]:
                    if t["line"] == lines[lid]["ref"]:
                        ks = path_keys(lid, segs, net, t["from"], t["to"])
                        if ks:
                            rat.append(t["min"] / sum(model[(lid, k)] for k in ks))
                if rat:
                    scale[lid] = statistics.mean(rat)
                    basis[lid] = f"公表の所要時間（{len(rat)} 件、line_totals.json）"
            if lid in scale:
                pass
            elif len(span_meas.get(lid, [])) >= 5:
                sp = span_meas[lid]
                scale[lid] = sum(mn for _, mn, _ in sp) / sum(sum(model[(lid, k)] for k in ks) for ks, _, _ in sp)
                basis[lid] = f"実測の区間時間（{sp[0][2]}、{len(sp)} 件）"
            elif lid in totals:
                rat = [mins / sum(model[(lid, k)] for k in ks) for ks, mins, _ in totals[lid]]
                # OSM の値は誰でも書き込めるので、較正済みのモデルから 25% 以上ずれる値は使わない
                # （上海 1号線・5号線は、区間運転の値や古い値が全線の値として入っている）
                ok = [x for x in rat if 0.75 <= x <= 1.25]
                if ok:
                    med = statistics.median(ok)
                    ok = [x for x in ok if abs(x / med - 1) <= 0.15]
                    scale[lid] = statistics.mean(ok)
                    basis[lid] = f"OSM の全線所要時間（{len(ok)} 系統）"
                else:
                    rejected[lid] = rat
        # 実測も全線の値も無い路線: 同じ路線網・同じ種別の係数の中央値（無ければ全体の中央値）
        all_s = list(scale.values())
        for lid, ln in lines.items():
            if lid not in scale:
                same = [scale[x] for x in scale if lines[x]["mode"] == ln["mode"]]
                scale[lid] = statistics.median(same or all_s or [1.0])
                basis[lid] = "推定（同じ路線網・種別の係数の中央値）" if same else "推定（全体の係数）"
                if lid in rejected:
                    basis[lid] += "。OSM の値は不自然なので不使用（" + "・".join(f"{x:.2f}" for x in rejected[lid]) + "）"

        # 区間の最終値: 実測がある区間は「実測の平均」と「係数を掛けたモデル」の平均（分単位の丸めをならす）
        out_rows = []
        for k, r in segs.items():
            lid = k[0]
            m = model[k] * scale[lid]
            if k in meas and meas[k]:
                v = robust(meas[k])
                final, src = v, meas_src[k]  # 公式の累積時間の差は、どの 2 駅間でも公式値に一致するので混ぜない
            else:
                final, src = m, basis[lid]
            out_rows.append({**r, "model_min": round(model[k], 2), "scale": round(scale[lid], 3),
                             "measured_min": round(robust(meas[k]), 2) if k in meas and meas[k] else "",
                             "measured_n": len(meas.get(k, [])), "final_min": round(final, 2), "source": src})
        final_by = {(r["line"], frozenset((r["from"], r["to"]))): r["final_min"] for r in out_rows}
        ref2lid = {ln["ref"]: lid for lid, ln in lines.items()}
        for t in totals_cfg.get(nid, []):
            lid = ref2lid.get(t["line"])
            ks = path_keys(lid, segs, net, t["from"], t["to"]) if lid else None
            if not ks:
                ref_rows.append((net["name_ja"], t["line"], f"{t['from']}→{t['to']}", t["min"], None, None, "区間が見つからない"))
                continue
            pred = sum(final_by[(lid, k)] for k in ks)
            used = basis[lid].startswith("公表")
            # 公表値で較正した路線は、その路線の公表値を使わずに推定した値（同じ路線網・種別の他路線の係数）も出す
            others = [scale[x] for x in scale if x != lid and lines[x]["mode"] == lines[lid]["mode"]
                      and basis[x].startswith(("実測", "OSM", "公表"))]
            hold = sum(model[(lid, k)] for k in ks) * statistics.median(others) if (used and others) else None
            ref_rows.append((net["name_ja"], lines[lid]["badge"], f"{t['from']}→{t['to']}", t["min"], pred, hold, basis[lid]))
        with (SEG / f"{nid}_times.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out_rows[0].keys()))
            w.writeheader()
            w.writerows(out_rows)

        # 検証（ホールドアウト）: 実測がある路線で、その路線の実測を使わずに推定した全線時間と、実測の全線時間を比べる
        for lid, ln in lines.items():
            keys = [k for k in segs if k[0] == lid]
            mk = [k for k in keys if k in meas and meas[k]]
            if len(mk) >= max(3, len(keys) // 3):
                truth = sum(robust(meas[k]) for k in mk)
                others = [scale[x] for x in scale if x != lid and lines[x]["mode"] == ln["mode"]
                          and basis[x].startswith(("実測", "OSM"))]
                if not others:
                    continue
                pred = sum(model[k] for k in mk) * statistics.median(others)
                acc_rows.append((net["name_ja"], ln["badge"], len(mk), truth, pred, pred / truth - 1))
        md += [f"## {net['name_ja']}", "", "| 路線 | 係数 | 根拠 |", "|---|---:|---|"]
        md += [f"| {lines[l]['badge']} | {scale[l]:.3f} | {basis[l]} |" for l in lines]
        md.append("")
    acc_, dw_, k_ = PARAMS
    md += ["## 地下鉄の駅間モデルの当てはめ（全路線網）", "",
           f"- 当てはめに使った路線: {len(anchors)}（実測・公表値・OSM の全線所要時間のある地下鉄）",
           f"- 決めた値: 加減速度 {acc_} m/s²、停車時間 {dw_} 秒、最高速度に対する実効の割合 {k_}",
           "- 決め方: 1 路線ずつ抜き、同じ路線網の他路線の係数の中央値で推定したときの誤差（下の表）の平均が最小になる値", "",
           "| 路線網 | 路線 | 抜いて推定したときの差 |", "|---|---|---:|"]
    badge = {lid: (nets[n]["name_ja"], ln["badge"]) for n in nets for lid, ln in G[n][7].items()}
    for (n, l), e in sorted(loo_err.items(), key=lambda t: -abs(t[1])):
        md.append(f"| {badge[l][0]} | {badge[l][1]} | {e * 100:+.1f}% |")
    le = [abs(e) for e in loo_err.values()]
    md += ["", f"- 平均 {statistics.mean(le) * 100:.1f}%、最大 {max(le) * 100:.1f}%、10% を超える路線 {sum(e > 0.10 for e in le)}/{len(le)}", ""]
    md += ["## 検証: 実測がある路線を「実測なし」として推定した場合の誤差（同じ路線網・種別の他路線の係数を使用）", "",
           "| 路線網 | 路線 | 区間 | 実測（分） | 推定（分） | 差 |", "|---|---|---:|---:|---:|---:|"]
    for n, b, c, t, p, e in sorted(acc_rows, key=lambda x: -abs(x[5])):
        md.append(f"| {n} | {b} | {c} | {t:.1f} | {p:.1f} | {e * 100:+.1f}% |")
    if acc_rows:
        errs = [abs(x[5]) for x in acc_rows]
        md += ["", f"- 平均 {statistics.mean(errs) * 100:.1f}%、最大 {max(errs) * 100:.1f}%（{len(errs)} 路線）"]
    md += ["", "## 照合: 公表されている区間の所要時間（overrides/line_totals.json）と最終値", "",
           "実測で作った路線は、公表値と独立に比べている。公表値で較正した路線は一致して当然なので、",
           "その路線の公表値を使わずに推定した場合（ホールドアウト）の差も出す。", "",
           "| 路線網 | 路線 | 区間 | 公表（分） | 最終値（分） | 差 | 公表値なしで推定した場合 | 根拠 |",
           "|---|---|---|---:|---:|---:|---:|---|"]
    ind = []
    for n, b, sec, mn, pred, hold, bs in ref_rows:
        if pred is None:
            md.append(f"| {n} | {b} | {sec} | {mn} | — | — | — | {bs} |")
            continue
        e = pred / mn - 1
        if not bs.startswith("公表"):
            ind.append(abs(e))
        h = f"{hold:.1f}（{(hold / mn - 1) * 100:+.1f}%）" if hold else "—"
        md.append(f"| {n} | {b} | {sec} | {mn} | {pred:.1f} | {e * 100:+.1f}% | {h} | {bs} |")
    if ind:
        md += ["", f"- 実測で作った路線の、公表値との差: 平均 {statistics.mean(ind) * 100:.1f}%、最大 {max(ind) * 100:.1f}%（{len(ind)} 件）"]
    holds = [abs(h / mn - 1) for _, _, _, mn, _, h, _ in ref_rows if h]
    if holds:
        md += [f"- 公表値で較正した路線を公表値なしで推定した場合の差: 平均 {statistics.mean(holds) * 100:.1f}%、最大 {max(holds) * 100:.1f}%（{len(holds)} 件）"]
    # 本地宝（第三者の転載）の確かさ: 深圳の公式時刻（Wikipedia のモジュール）と、同じ区間で比べる
    sz = nets["shenzhen"]
    off, bdb = sz_timetable(sz), bendibao(sz)
    st_line = defaultdict(set)
    for ln in sz["lines"]:
        for x in ln["stations"]:
            st_line[x].add(ln["badge"])
    per_line = defaultdict(lambda: [0.0, 0.0, 0])
    seg_err = []
    for pair in set(off) & set(bdb):
        a, b = robust(off[pair]), robust(bdb[pair])
        seg_err.append(abs(b - a))
        for lb in set.intersection(*(st_line[x] for x in pair)):
            per_line[lb][0] += a
            per_line[lb][1] += b
            per_line[lb][2] += 1
    if seg_err:
        md += ["", "## 照合: 本地宝（公式時刻の転載）と深圳の公式時刻（同じ区間どうし）", "",
               "| 路線 | 区間 | 公式（分） | 本地宝（分） | 差 |", "|---|---:|---:|---:|---:|"]
        le = []
        for lb, (a, b, n) in sorted(per_line.items(), key=lambda t: -t[1][2]):
            if n < 5:  # 乗換駅をまたぐ 1〜2 区間だけの重なりは路線の比較にならない
                continue
            le.append(abs(b / a - 1))
            md.append(f"| {lb} | {n} | {a:.1f} | {b:.1f} | {(b / a - 1) * 100:+.1f}% |")
        md += ["", f"- 区間ごとの差: 平均 {statistics.mean(seg_err):.2f} 分、1 分を超える区間 {sum(e > 1 for e in seg_err)}/{len(seg_err)}",
               f"- 路線の合計の差: 平均 {statistics.mean(le) * 100:.1f}%、最大 {max(le) * 100:.1f}%"]
    (SEG / "accuracy.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
