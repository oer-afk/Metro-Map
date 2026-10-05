"""照合用の駅一覧（中国語版 Wikipedia）を取得し、路線ごとの駅リストに整形する。

使い方:  python tools/fetch_reference.py shanghai [--offline]

  raw/<city>/wikipedia_zh.wikitext   取得したウィキテキスト（そのまま）
  raw/<city>/reference_stations.csv  line,seq,name,operating（営業中=1、建設中・計画=0）
  raw/<city>/wikipedia_line_colors.lua  路線色の定義（Module:Adjacent stations）
  raw/<city>/reference_colors.json    {路線ref: "#RRGGBB"}

--offline を付けると再取得せず、保存済みの wikitext から CSV だけ作り直す。
このデータは検証（validate.py）にだけ使い、表示データには混ぜない。
"""
from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

# Windows のコンソール（CP932）でも簡体字を出力できるようにする
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}

# 都市ごとの設定: ページ名、見出し→路線ref の対応、駅テンプレートの系統名
REFERENCE = {
    "shanghai": {
        "page": "上海地铁车站列表",
        "stl_system": "上海地铁",
        "color_module": "Module:Adjacent stations/上海地铁",
        "section_re": r"^==\s*(\d+号线|浦江线)\s*==\s*$",
        "section_ref": lambda h: h.replace("号线", "") if h.endswith("号线") else "浦江",
    },
}


def fetch_wikitext(page: str) -> str:
    r = requests.get(
        "https://zh.wikipedia.org/w/api.php",
        params={"action": "parse", "page": page, "prop": "wikitext", "format": "json",
                "variant": "zh-cn", "redirects": 1},
        headers=HEADERS, timeout=60,
    )
    r.raise_for_status()
    return r.json()["parse"]["wikitext"]["*"]


def fetch_raw(title: str) -> str:
    r = requests.get("https://zh.wikipedia.org/w/index.php", params={"title": title, "action": "raw"},
                     headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.text


def parse_colors(lua: str) -> dict:
    """Module:Adjacent stations の lines 表から ["ref"] = { ["color"] = "RRGGBB" } を拾う。"""
    out = {}
    for m in re.finditer(r'\[\"([^"]+)\"\]\s*=\s*\{[^{}]*?\[\"color\"\]\s*=\s*\"([0-9A-Fa-f]{6})\"', lua):
        out.setdefault(m.group(1), "#" + m.group(2).upper())
    return out


def parse(wikitext: str, ref_cfg: dict) -> list[dict]:
    """営業中路線の節だけを読み、表の行ごとに駅名と営業中かどうかを取り出す。

    「建设中」「规划中」のセル（rowspan 付きを含む）がかかる行は operating=0 とする。
    """
    lines = wikitext.splitlines()
    sec_re = re.compile(ref_cfg["section_re"])
    any_sec = re.compile(r"^==[^=].*==\s*$")
    stl_re = re.compile(r"\{\{stl\|" + re.escape(ref_cfg["stl_system"]) + r"\|([^}|]+)")
    status_re = re.compile(r"^\|\s*(?:[^|]*?rowspan\s*=\s*\"?(\d+)\"?[^|]*\|)?\s*(建设中|规划中)\s*$")

    out: list[dict] = []
    ref = None
    rows: list[list[str]] = []
    for ln in lines + ["== end =="]:
        if any_sec.match(ln):
            if ref is not None:
                out.extend(_rows_to_stations(ref, rows, stl_re, status_re))
            m = sec_re.match(ln)
            ref = ref_cfg["section_ref"](m.group(1)) if m else None
            rows = []
            continue
        if ref is None:
            continue
        if ln.startswith("|-") or ln.startswith("{|"):
            rows.append([ln])
        elif rows:
            rows[-1].append(ln)
    return out


def _rows_to_stations(ref, rows, stl_re, status_re):
    res = []
    pending_off = 0  # rowspan 付きの「建设中」がまだかかる行数
    seq = 0
    for row in rows:
        name = None
        # 灰色背景の行・セルは建設中・未開業（このページの凡例）
        off_here = bool(re.search(r"background(-color)?:\s*#ccc", row[0], re.I))
        covered = pending_off > 0
        for cell in row[1:]:
            if name is None and cell.startswith("|"):
                m = stl_re.search(cell)
                if m:
                    name = m.group(1).strip()
                    if re.search(r"background(-color)?:\s*#ccc", cell, re.I):
                        off_here = True
            sm = status_re.match(cell.strip())
            if sm:
                off_here = True
                pending_off = max(pending_off, int(sm.group(1) or 1))
        if pending_off > 0:
            pending_off -= 1  # 駅名の無い行も rowspan の行数に数える
        if name is None:
            continue
        seq += 1
        res.append({"line": ref, "seq": seq, "name": name, "operating": int(not (off_here or covered))})
    return res


def main() -> None:
    city = sys.argv[1]
    offline = "--offline" in sys.argv
    cfg = REFERENCE[city]
    out_dir = ROOT / "raw" / city
    wt_path = out_dir / "wikipedia_zh.wikitext"
    if not offline:
        wt = fetch_wikitext(cfg["page"])
        wt_path.write_text(wt, encoding="utf-8")
        meta = {"page": cfg["page"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (out_dir / "wikipedia_zh.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    lua_path = out_dir / "wikipedia_line_colors.lua"
    if not offline and cfg.get("color_module"):
        lua_path.write_text(fetch_raw(cfg["color_module"]), encoding="utf-8")
    if lua_path.exists():
        colors = parse_colors(lua_path.read_text(encoding="utf-8"))
        (out_dir / "reference_colors.json").write_text(json.dumps(colors, ensure_ascii=False, indent=2), encoding="utf-8")
    wt = wt_path.read_text(encoding="utf-8")
    rows = parse(wt, cfg)
    with (out_dir / "reference_stations.csv").open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["line", "seq", "name", "operating"])
        w.writeheader()
        w.writerows(rows)
    by_line: dict[str, list[int]] = {}
    for r in rows:
        by_line.setdefault(r["line"], [0, 0])[0 if r["operating"] else 1] += 1
    for k, (op, off) in by_line.items():
        print(f"  {k}: operating {op}, not yet {off}")


if __name__ == "__main__":
    main()
