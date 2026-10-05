"""raw/<city>/ の OSM データから表示用データ site/data/<city>.json を作る。

使い方:  python tools/build_city.py shanghai

処理（仕様書 6.2）:
  1. 上り・下り、支線・区間運転で分かれた路線リレーションを 1 路線にまとめる
  2. 路線番号・路線名・色を取り出す（色が欠けていれば overrides/line_colors.json で補う）
  3. 駅を抽出し、末尾の「站」を除き、同名・近接の点を 1 駅に統合する
     （点は railway=station の位置を基に、所属路線の線形上の最寄り点の平均へ寄せる）
  4. 日本漢字表記（OpenCC + overrides）
  5. 読み（pypinyin + overrides、カタカナは対応表）
  6. 付録 A の確認済みデータで上書きし、機械変換との差を reports/ に出す
検証（6.3）は validate.py が行う。
"""
from __future__ import annotations

import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import textconv  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
STOP_ROLES = {"stop", "stop_entry_only", "stop_exit_only", "stop_exit", "stop_entry"}
MERGE_RADIUS_M = 800      # 同名の停車位置を 1 駅にまとめる距離
STATION_MATCH_M = 600     # railway=station の点を採用する距離
DEDUP_TRACK_M = 25        # 並走する上下線の線路を 1 本に間引く距離
SIMPLIFY_M = 4            # 線形の簡略化の許容誤差
COORD_DIGITS = 5          # 出力座標の小数桁（約 1 m）
SNAP_MAX_M = 400          # 駅の点を線形に寄せる上限距離（これより遠い路線は寄せる対象にしない）


# ------------------------------------------------------------------ 幾何
def dist_m(a, b) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    x = (lon2 - lon1) * math.cos((lat1 + lat2) / 2)
    y = lat2 - lat1
    return math.hypot(x, y) * 6371000


def _xy(p, lat0):
    return (p[1] * 111320 * math.cos(math.radians(lat0)), p[0] * 110540)


def point_seg_dist_m(p, a, b) -> float:
    lat0 = p[0]
    px, py = _xy(p, lat0)
    ax, ay = _xy(a, lat0)
    bx, by = _xy(b, lat0)
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def nearest_on_polylines(p, lines):
    """折れ線群の上で p に最も近い点と、その距離 (m) を返す。"""
    lat0 = p[0]
    kx, ky = 111320 * math.cos(math.radians(lat0)), 110540
    px, py = p[1] * kx, p[0] * ky
    best, best_pt = float("inf"), None
    for ln in lines:
        for a, b in zip(ln, ln[1:]):
            ax, ay, bx, by = a[1] * kx, a[0] * ky, b[1] * kx, b[0] * ky
            dx, dy = bx - ax, by - ay
            L = dx * dx + dy * dy
            t = 0 if L == 0 else max(0, min(1, ((px - ax) * dx + (py - ay) * dy) / L))
            qx, qy = ax + t * dx, ay + t * dy
            d = math.hypot(px - qx, py - qy)
            if d < best:
                best, best_pt = d, (qy / ky, qx / kx)
    return best_pt, best


def point_polyline_dist_m(p, lines) -> float:
    best = float("inf")
    for ln in lines:
        for a, b in zip(ln, ln[1:]):
            best = min(best, point_seg_dist_m(p, a, b))
    return best


def rdp(pts, eps_m):
    if len(pts) < 3:
        return pts
    a, b = pts[0], pts[-1]
    idx, dmax = 0, 0.0
    for i in range(1, len(pts) - 1):
        d = point_seg_dist_m(pts[i], a, b)
        if d > dmax:
            idx, dmax = i, d
    if dmax <= eps_m:
        return [a, b]
    return rdp(pts[: idx + 1], eps_m)[:-1] + rdp(pts[idx:], eps_m)


def densify(pts, step_m=20):
    out = [pts[0]]
    for a, b in zip(pts, pts[1:]):
        n = max(1, int(dist_m(a, b) // step_m))
        for k in range(1, n + 1):
            out.append((a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n))
    return out


class Grid:
    """近傍点検索用の簡易グリッド（線路の重複判定に使う）。"""

    def __init__(self, cell_deg=0.0005):
        self.c = cell_deg
        self.cells = defaultdict(list)

    def add(self, pts):
        for p in pts:
            self.cells[(int(p[0] / self.c), int(p[1] / self.c))].append(p)

    def near(self, p, r_m):
        i, j = int(p[0] / self.c), int(p[1] / self.c)
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for q in self.cells.get((i + di, j + dj), ()):
                    if dist_m(p, q) <= r_m:
                        return True
        return False


def chain_ways(ways: list[list[tuple]]) -> list[list[tuple]]:
    """端点を共有する線分をつなげて長い折れ線にする（3 本以上が集まる分岐点ではつながない）。"""
    def key(p):
        return (round(p[0], 6), round(p[1], 6))

    segs = [list(w) for w in ways if len(w) >= 2]
    while True:
        ends = defaultdict(list)
        for i, s in enumerate(segs):
            ends[key(s[0])].append(i)
            ends[key(s[-1])].append(i)
        pair = next(((k, ix[0], ix[1]) for k, ix in ends.items() if len(ix) == 2 and ix[0] != ix[1]), None)
        if pair is None:
            return segs
        k, i, j = pair
        a, b = segs[i], segs[j]
        if key(a[-1]) != k:
            a = a[::-1]
        if key(b[0]) != k:
            b = b[::-1]
        segs = [s for n, s in enumerate(segs) if n not in (i, j)] + [a + b[1:]]


# ------------------------------------------------------------------ 入力
def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def line_sort_key(ref: str):
    return (0, int(ref), "") if ref.isdigit() else (1, 0, ref)


def slug_from_pinyin(name: str) -> str:
    plain = textconv._word_pinyin(name.replace(textconv.MIDDOT, ""))
    s = "".join(p for _, p in plain)
    s = s.replace("v", "u")
    s = re.sub(r"[^a-z0-9]", "", s.lower())
    return s or "x"


def main() -> None:
    city = sys.argv[1]
    cfg = load_json(ROOT / "config" / f"{city}.json")
    raw = ROOT / "raw" / city
    routes = load_json(raw / "routes.json")
    stations_raw = load_json(raw / "stations.json")
    renames = {k: v for k, v in load_json(ROOT / "overrides" / f"station_renames_{city}.json").items()
               if not k.startswith("_")} if (ROOT / "overrides" / f"station_renames_{city}.json").exists() else {}
    color_fallback = load_json(ROOT / "overrides" / "line_colors.json").get(city, {})
    report: dict = {"city": city, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    els = {(e["type"], e["id"]): e for e in routes["elements"]}
    rels = [e for e in routes["elements"] if e["type"] == "relation"]
    masters = [r for r in rels if r["tags"].get("type") == "route_master"]
    route_rels = [r for r in rels if r["tags"].get("type") == "route"]

    # ---- 1. 対象リレーションの選別
    excluded = []
    selected = []
    today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    for r in route_rels:
        t = r["tags"]
        why = None
        if t.get("route") not in cfg["route_types"]:
            why = f"route={t.get('route')}"
        elif any(p in (t.get("name") or "") for p in cfg["exclude_relation_name_patterns"]):
            why = "除外パターンに一致"
        elif t.get("route") != "subway" and t.get("network") not in cfg.get("network_include", []):
            why = f"network={t.get('network')}"
        elif t.get("state") in ("proposed", "construction") or t.get("disused") == "yes":
            why = f"state={t.get('state')}"
        elif t.get("opening_date") and t["opening_date"] > today:
            why = f"opening_date={t['opening_date']}"
        if why:
            excluded.append({"id": r["id"], "name": t.get("name"), "reason": why})
        else:
            selected.append(r)
    report["excluded_relations"] = excluded

    # ---- 路線ごとにまとめる（route_master があればそれ、なければ ref）
    rel_master = {}
    for m in masters:
        for mem in m["members"]:
            if mem["type"] == "relation":
                rel_master[mem["ref"]] = m
    groups: dict[str, list] = defaultdict(list)
    for r in selected:
        ref = r["tags"].get("ref") or rel_master.get(r["id"], {}).get("tags", {}).get("ref")
        groups[ref].append(r)

    line_ids = cfg.get("line_ids", {})
    net_prefix = cfg.get("network_name_prefix", "")
    lines_out = []
    stop_records = []  # (line_id, rel_id, seq, node)
    color_notes = []
    for ref in sorted(groups, key=line_sort_key):
        rs = groups[ref]
        m = rel_master.get(rs[0]["id"])
        mt = m["tags"] if m else {}
        lid = line_ids.get(ref, ref)
        name_orig = (mt.get("name") or "").removeprefix(net_prefix) or (f"{ref}号线" if ref.isdigit() else f"{ref}线")
        name_orig = re.sub(r"^.*?(\d+号线|[^\d]+线)$", r"\1", name_orig)
        color = (mt.get("colour") or next((r["tags"].get("colour") for r in rs if r["tags"].get("colour")), None))
        color_src = "osm"
        if not color:
            color = color_fallback.get(lid)
            color_src = "supplemented"
            color_notes.append({"line": lid, "color": color, "note": "OSM に colour が無く overrides/line_colors.json で補完"})
        lines_out.append({
            "id": lid, "ref": ref, "name_orig": name_orig, "name_ja": textconv.to_name_ja(name_orig),
            "color": color.upper() if color else "#888888", "color_source": color_src,
            "mode": rs[0]["tags"].get("route"),
            "_rels": rs,
        })
        for r in rs:
            seq = 0
            for mem in r["members"]:
                if mem["type"] == "node" and mem["role"] in STOP_ROLES:
                    n = els.get(("node", mem["ref"]))
                    if n is None:
                        continue
                    stop_records.append((lid, r["id"], seq, n))
                    seq += 1
    report["color_supplemented"] = color_notes

    # ---- 3. 駅の抽出と統合
    rename_log = []

    def clean_name(raw_name: str) -> str:
        n = textconv.normalize_orig(raw_name)
        if n.endswith("站") and not re.search(cfg.get("keep_zhan_regex", r"$^"), n):
            n = n[:-1]
        if n in renames:
            rename_log.append((n, renames[n]))
            n = renames[n]
        return n

    # railway=station の点（面は中心）
    st_points = defaultdict(list)
    st_en = {}
    for e in stations_raw["elements"]:
        nm = e.get("tags", {}).get("name")
        if not nm:
            continue
        p = (e["lat"], e["lon"]) if "lat" in e else ((e["center"]["lat"], e["center"]["lon"]) if "center" in e else None)
        if p:
            st_points[clean_name(nm)].append(p)
            if e["tags"].get("name:en"):
                st_en.setdefault(clean_name(nm), e["tags"]["name:en"])

    # 営業状況の上書き（OSM の路線リレーションの抜け・未開業駅の混入を直す）
    sp = ROOT / "overrides" / f"station_status_{city}.json"
    status = load_json(sp) if sp.exists() else {}
    excl = {(x["line"], x["name"]) for x in status.get("exclude_stops", [])}
    adds = status.get("add_stops", [])
    report["status_overrides"] = {"exclude_stops": status.get("exclude_stops", []), "add_stops": adds}

    by_name: dict[str, list] = defaultdict(list)
    unnamed = []
    for lid, rid, seq, n in stop_records:
        nm = n.get("tags", {}).get("name")
        if not nm:
            unnamed.append({"line": lid, "relation": rid, "node": n["id"]})
            continue
        if (lid, clean_name(nm)) in excl:
            continue
        by_name[clean_name(nm)].append((lid, rid, seq, n))
    for x in adds:
        pts = st_points.get(x["name"])
        if not pts:
            raise SystemExit(f"add_stops: railway=station の点が見つからない: {x['name']}")
        node = {"id": f"add:{x['line']}:{x['name']}", "lat": sum(q[0] for q in pts) / len(pts),
                "lon": sum(q[1] for q in pts) / len(pts),
                "tags": {"name": x["name"], **({"name:en": st_en[x["name"]]} if x["name"] in st_en else {})}}
        by_name[x["name"]].append((x["line"], None, None, node))
    report["unnamed_stops"] = unnamed
    report["renames_applied"] = sorted({f"{a} → {b}" for a, b in rename_log})

    stations = []  # dict(name, pts, lines, nodes, en)
    for name, recs in by_name.items():
        clusters: list[dict] = []
        for rec in recs:
            p = (rec[3]["lat"], rec[3]["lon"])
            hit = next((c for c in clusters if any(dist_m(p, q) <= MERGE_RADIUS_M for q in c["pts"])), None)
            if hit is None:
                hit = {"name": name, "pts": [], "recs": []}
                clusters.append(hit)
            hit["pts"].append(p)
            hit["recs"].append(rec)
        stations.extend(clusters)

    report["same_name_split"] = [
        {"name": n, "count": sum(1 for s in stations if s["name"] == n)}
        for n in sorted({s["name"] for s in stations}) if sum(1 for s in stations if s["name"] == n) > 1
    ]

    # 代表点・ID・表記
    verified = {}
    with (ROOT / "overrides" / cfg["verified_csv"]).open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            verified[textconv.normalize_orig(row["原表記"])] = row
    manual = {}
    mp = ROOT / "overrides" / f"readings_{city}.json"
    if mp.exists():
        manual = {k: v for k, v in load_json(mp).items() if not k.startswith("_")}

    used_ids = set()
    machine_vs_verified = []
    st_out = []
    node_to_station = {}
    for s in stations:
        cen = (sum(p[0] for p in s["pts"]) / len(s["pts"]), sum(p[1] for p in s["pts"]) / len(s["pts"]))
        cands = [q for q in st_points.get(s["name"], []) if dist_m(q, cen) <= STATION_MATCH_M]
        if cands:
            pos = (sum(q[0] for q in cands) / len(cands), sum(q[1] for q in cands) / len(cands))
            pos_src = "station"
        else:
            pos, pos_src = cen, "stop_position"
        sid = f"{cfg['id_prefix']}_{slug_from_pinyin(s['name'])}"
        base, k = sid, 2
        while sid in used_ids:
            sid = f"{base}_{k}"
            k += 1
        used_ids.add(sid)
        for rec in s["recs"]:
            node_to_station[rec[3]["id"]] = sid
        name_ja = textconv.to_name_ja(s["name"])
        reading = textconv.reading_cmn(s["name"])
        en = next((r[3]["tags"].get("name:en") for r in s["recs"] if r[3]["tags"].get("name:en")), None)
        is_verified = False
        if s["name"] in manual:
            mo = manual[s["name"]]
            name_ja = mo.get("name_ja", name_ja)
            reading = {"roman": mo.get("roman", reading["roman"]), "kana": mo.get("kana", reading["kana"])}
        if s["name"] in verified:
            v = verified[s["name"]]
            diffs = {}
            if name_ja != v["日本漢字"]:
                diffs["name_ja"] = [name_ja, v["日本漢字"]]
            if reading["roman"] != v["ピンイン"]:
                diffs["roman"] = [reading["roman"], v["ピンイン"]]
            if reading["kana"] != v["カタカナ"]:
                diffs["kana"] = [reading["kana"], v["カタカナ"]]
            if diffs:
                machine_vs_verified.append({"name": s["name"], **diffs})
            name_ja = v["日本漢字"]
            reading = {"roman": v["ピンイン"], "kana": v["カタカナ"]}
            is_verified = True
        st_out.append({
            "id": sid, "name_orig": s["name"], "name_ja": name_ja, "reading": reading,
            "name_en": en, "lat": round(pos[0], COORD_DIGITS), "lon": round(pos[1], COORD_DIGITS),
            "lines": [], "verified": is_verified, "_pos_src": pos_src,
        })
    report["machine_vs_verified"] = machine_vs_verified
    st_by_id = {s["id"]: s for s in st_out}
    name_to_sid = {}
    for s_ in st_out:
        name_to_sid.setdefault(s_["name_orig"], s_["id"])

    # ---- 路線の駅順と線形
    for ln in lines_out:
        patterns = []
        for r in ln["_rels"]:
            seq = []
            for mem in r["members"]:
                if mem["type"] == "node" and mem["role"] in STOP_ROLES and mem["ref"] in node_to_station:
                    sid = node_to_station[mem["ref"]]
                    if not seq or seq[-1] != sid:
                        seq.append(sid)
            for x in adds:  # 抜けている駅を前後の駅の間に差し込む
                if x["line"] != ln["id"]:
                    continue
                sid_new = node_to_station[f"add:{x['line']}:{x['name']}"]
                a_id, b_id = (name_to_sid.get(n) for n in x["between"])
                for i in range(len(seq) - 1):
                    if {seq[i], seq[i + 1]} == {a_id, b_id}:
                        seq.insert(i + 1, sid_new)
                        break
            if seq:
                patterns.append(seq)
        # 逆向き・同一の運転系統を除き、駅を最も多く含む系統を本線にする
        uniq = []
        for p in sorted(patterns, key=len, reverse=True):
            if any(p == q or p == q[::-1] for q in uniq):
                continue
            uniq.append(p)
        main_seq = uniq[0]
        loop = len(main_seq) > 2 and main_seq[0] == main_seq[-1]
        order = list(dict.fromkeys(main_seq))
        branches = []
        for p in uniq[1:]:
            extra = [s for s in p if s not in order]
            if not extra:
                continue  # 区間運転・急行など（駅は本線に含まれる）
            # 本線との分岐駅を前後に 1 駅含めて持つ
            idx = [i for i, s in enumerate(p) if s not in order]
            a, b = max(0, idx[0] - 1), min(len(p), idx[-1] + 2)
            br = p[a:b]
            if br[0] not in order and br[-1] in order:
                br = br[::-1]  # 分岐駅が先頭になる向きにそろえる
            branches.append(br)
            order.extend(extra)
        ln["stations"] = order
        if branches:
            ln["branches"] = branches
        if loop:
            ln["loop"] = True
        for sid in order:
            if ln["id"] not in st_by_id[sid]["lines"]:
                st_by_id[sid]["lines"].append(ln["id"])

        # 線形: 各リレーションの線路（role が空）を集め、並走線を間引き、つないで簡略化
        ways = {}
        for r in ln["_rels"]:
            for mem in r["members"]:
                if mem["type"] == "way" and mem["role"] in ("", "route", "forward", "backward"):
                    w = els.get(("way", mem["ref"]))
                    if w and w.get("geometry"):
                        ways[w["id"]] = [(g["lat"], g["lon"]) for g in w["geometry"]]
        wl = sorted(ways.values(), key=lambda pts: -sum(dist_m(a, b) for a, b in zip(pts, pts[1:])))
        grid = Grid()
        kept = []
        for pts in wl:
            dense = densify(pts)
            near = sum(1 for p in dense if grid.near(p, DEDUP_TRACK_M))
            if near / len(dense) >= 0.9:
                continue
            kept.append(pts)
            grid.add(dense)
        chained = chain_ways(kept)
        geom = []
        for c in chained:
            simp = rdp(c, SIMPLIFY_M)
            geom.append([[round(p[0], COORD_DIGITS), round(p[1], COORD_DIGITS)] for p in simp])
        ln["geometry"] = geom
        ln["_ways_total"] = len(ways)
        ln["_ways_kept"] = len(kept)

    # 駅の点を所属路線の線形に寄せる: 各路線の線形上の最寄り点の平均（単独駅は線上、乗換駅は路線間）
    geom_by_line = {ln["id"]: ln["geometry"] for ln in lines_out}
    moved = []
    for s in st_out:
        if not s["lines"]:
            continue
        p0 = (s["lat"], s["lon"])
        snaps = []
        for lid in s["lines"]:
            q, d = nearest_on_polylines(p0, geom_by_line[lid])
            if q is not None and d <= SNAP_MAX_M:
                snaps.append(q)
        if snaps:
            q = (sum(x[0] for x in snaps) / len(snaps), sum(x[1] for x in snaps) / len(snaps))
            moved.append(dist_m(p0, q))
            s["lat"], s["lon"] = round(q[0], COORD_DIGITS), round(q[1], COORD_DIGITS)
    report["station_snap"] = {"snapped": len(moved), "max_moved_m": round(max(moved, default=0)),
                               "median_moved_m": round(sorted(moved)[len(moved) // 2]) if moved else 0}

    # 駅の所属路線を路線順に
    order_idx = {ln["id"]: i for i, ln in enumerate(lines_out)}
    for s in st_out:
        s["lines"].sort(key=lambda x: order_idx[x])
    st_out = [s for s in st_out if s["lines"]]

    # ---- 出力
    fetched = routes.get("_fetched_at", "")[:10]
    out = {
        "id": cfg["id"], "name_ja": cfg["name_ja"], "name_orig": cfg["name_orig"],
        "script": cfg["script"], "reading_lang": cfg["reading_lang"],
        "center": cfg["center"], "zoom": cfg["zoom"], "focus_bbox": cfg["focus_bbox"],
        "source": {"name": "OpenStreetMap", "license": "ODbL 1.0", "extracted": fetched},
        "lines": [{k: v for k, v in ln.items() if not k.startswith("_")} for ln in lines_out],
        "stations": [{k: v for k, v in s.items() if not k.startswith("_")} for s in st_out],
    }
    data_dir = ROOT / "site" / "data"
    (data_dir / f"{city}.json").write_text(_dump_city(out), encoding="utf-8")

    # cities.json に 1 行で登録（既存があれば置き換え）
    cpath = data_dir / "cities.json"
    cities = load_json(cpath) if cpath.exists() else []
    entry = {"id": cfg["id"], "name_ja": cfg["name_ja"], "name_orig": cfg["name_orig"], "file": f"{city}.json"}
    cities = [c for c in cities if c["id"] != cfg["id"]] + [entry]
    cpath.write_text("[\n" + ",\n".join("  " + json.dumps(c, ensure_ascii=False) for c in cities) + "\n]\n",
                     encoding="utf-8")

    report["lines"] = [{"id": ln["id"], "name": ln["name_orig"], "color": ln["color"], "mode": ln["mode"],
                        "relations": len(ln["_rels"]), "stations": len(ln["stations"]),
                        "branches": len(ln.get("branches", [])), "loop": ln.get("loop", False),
                        "ways": f'{ln["_ways_kept"]}/{ln["_ways_total"]}', "polylines": len(ln["geometry"])}
                       for ln in lines_out]
    report["stations_total"] = len(st_out)
    report["stations_verified"] = sum(1 for s in st_out if s["verified"])
    report["station_position_source"] = {
        "station": sum(1 for s in st_out if s["_pos_src"] == "station"),
        "stop_position": sum(1 for s in st_out if s["_pos_src"] == "stop_position"),
    }
    rep_dir = ROOT / "reports"
    rep_dir.mkdir(exist_ok=True)
    (rep_dir / f"{city}_build.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 機械変換と付録 A の差（変換規則の改善用）
    with (rep_dir / f"{city}_machine_vs_verified.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["原表記", "項目", "機械変換", "確認済み"])
        for d in machine_vs_verified:
            for k in ("name_ja", "roman", "kana"):
                if k in d:
                    w.writerow([d["name"], k, d[k][0], d[k][1]])
    # 全駅の表記・読み一覧（人の確認用）
    with (rep_dir / f"{city}_stations.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "原表記", "日本漢字", "ピンイン", "カタカナ", "路線", "確認済み"])
        for s in sorted(st_out, key=lambda s: (s["verified"], s["reading"]["roman"])):
            w.writerow([s["id"], s["name_orig"], s["name_ja"], s["reading"]["roman"], s["reading"]["kana"],
                        "/".join(s["lines"]), "1" if s["verified"] else ""])
    print(f"lines {len(lines_out)}, stations {len(st_out)} (verified {report['stations_verified']})")
    print(f"machine≠verified: {len(machine_vs_verified)}; renames: {report['renames_applied']}")


def _dump_city(obj: dict) -> str:
    """読みやすさとサイズの両立: 駅は 1 駅 1 行、線形は 1 折れ線 1 行。"""
    head = {k: v for k, v in obj.items() if k not in ("lines", "stations")}
    parts = ["{"]
    for k, v in head.items():
        parts.append(f'  {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)},')
    parts.append('  "lines": [')
    lns = []
    for ln in obj["lines"]:
        meta = {k: v for k, v in ln.items() if k != "geometry"}
        g = ",\n".join("        " + json.dumps(pl, separators=(",", ":")) for pl in ln["geometry"])
        lns.append("    {\n" + ",\n".join(f'      {json.dumps(k)}: {json.dumps(v, ensure_ascii=False)}' for k, v in meta.items())
                   + ',\n      "geometry": [\n' + g + "\n      ]\n    }")
    parts.append(",\n".join(lns))
    parts.append("  ],")
    parts.append('  "stations": [')
    parts.append(",\n".join("    " + json.dumps(s, ensure_ascii=False) for s in obj["stations"]))
    parts.append("  ]")
    parts.append("}")
    return "\n".join(parts) + "\n"


if __name__ == "__main__":
    main()
