"""照合用の駅一覧（中国語版 Wikipedia）を取得し、路線ごとの駅リストに整形する。

使い方:  python tools/fetch_reference.py <network_id> [--offline]

設定は config/<network_id>.json の "reference"（page, stl_system, color_module, section_ref_map）。

  raw/<id>/wikipedia_zh.wikitext        取得したウィキテキスト（そのまま）
  raw/<id>/wiki_templates/*.wikitext    路線ごとの駅一覧テンプレート（広州・深圳のように表がテンプレートにある場合）
  raw/<id>/reference_stations.csv       line,seq,name,operating（営業中=1、建設中・計画=0）
  raw/<id>/wikipedia_line_colors.lua    路線色の定義（Module:Adjacent stations）
  raw/<id>/reference_colors.json        {路線ref: "#RRGGBB"}

--offline を付けると再取得せず、保存済みのウィキテキストから CSV だけ作り直す。
このデータは検証（validate.py）にだけ使い、表示データには混ぜない。
"""
from __future__ import annotations

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent

# Windows のコンソール（CP932）でも簡体字を出力できるようにする
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")
HEADERS = {"User-Agent": "metro-map-learning/0.1 (personal study; static map)"}
# 未開業を表す書き方（上海: 建设中・灰色背景。広州: 預計2026年・预留站・有待確定・斜体の駅名）
NOT_OPEN = (r"(建设中|建設中|在建|规划中|規劃中|未开通|未開通|暂缓开通|暫緩開通|预留站|預留站|有待确定|有待確定"
            r"|(?:预计|預計)\s*\d{4}\s*年)(?![：:])")
GREY = re.compile(r"background(-color)?\s*:\s*#(ccc|cccccc|ddd|dddddd)\b", re.I)


def _get(url: str, params: dict) -> requests.Response:
    for attempt in range(4):
        r = requests.get(url, params=params, headers=HEADERS, timeout=60)
        if r.status_code == 200:
            return r
        time.sleep(5 * (attempt + 1))
    r.raise_for_status()
    return r


def fetch_wikitext(page: str) -> str:
    r = _get("https://zh.wikipedia.org/w/api.php",
             {"action": "parse", "page": page, "prop": "wikitext", "format": "json",
              "variant": "zh-cn", "redirects": 1})
    return r.json()["parse"]["wikitext"]["*"]


def fetch_raw(title: str) -> str:
    return _get("https://zh.wikipedia.org/w/index.php", {"title": title, "action": "raw"}).text


def parse_colors(lua: str) -> dict:
    """Module:Adjacent stations の lines 表から ["ref"] = { ["color"] = "RRGGBB" } を拾う。"""
    out = {}
    for m in re.finditer(r'\[\"([^"]+)\"\]\s*=\s*\{[^{}]*?\[\"color\"\]\s*=\s*\"([0-9A-Fa-f]{6})\"', lua):
        out.setdefault(m.group(1), "#" + m.group(2).upper())
    return out


def section_ref(heading: str, ref_map: dict) -> str | None:
    """節の見出しを路線 ref に直す。対象外の節は None。"""
    h = heading.strip()
    if h in ref_map:
        return ref_map[h]
    m = re.fullmatch(r"(\d+)号线", h)
    return m.group(1) if m else None


def split_sections(wikitext: str, ref_map: dict) -> list[tuple[str, str]]:
    out, ref, buf = [], None, []
    for ln in wikitext.splitlines() + ["== end =="]:
        m = re.match(r"^==([^=].*?)==\s*$", ln)
        if m:
            if ref is not None:
                out.append((ref, "\n".join(buf)))
            ref, buf = section_ref(m.group(1), ref_map), []
            continue
        if ref is not None:
            buf.append(ln)
    return out


def parse_rows(ref: str, text: str, stl_re) -> list[dict]:
    """表の行ごとに駅名と営業中かどうかを取り出す。

    「建设中」などのセル（rowspan 付きを含む）がかかる行、灰色背景の行は operating=0。
    """
    rows: list[list[str]] = []
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)  # コメントアウトされた行（計画中の駅など）は読まない
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("|-") or s.startswith("{|"):
            rows.append([s])
        elif rows:
            rows[-1].append(s)
    status_re = re.compile(r"^[|!]\s*(?:[^|]*?rowspan\s*=\s*\"?(\d+)\"?[^|]*\|)?\s*" + NOT_OPEN)
    res, pending_off, seq = [], 0, 0
    section_off = False  # 「后通段（在建）」のような見出し行より後は、その路線としては未開業
    for row in rows:
        cells = [c for c in row[1:] if c]
        if cells and all(c.startswith("!") for c in cells) and not stl_re.search(" ".join(cells))                 and any("colspan" in c for c in cells):
            head = " ".join(cells)
            if re.search(r"后通段|後通段|（在建）|\(在建\)", head) and "接續" not in head and "接续" not in head:
                section_off = True
            elif re.search(r"[號号][線线]", head):
                section_off = False
            continue
        name = None
        off_here = bool(GREY.search(row[0]))
        covered = pending_off > 0
        for cell in row[1:]:
            if name is None and cell[:1] in "|!":
                m = stl_re.search(cell)
                if m and not re.search(r"[：:]\s*\{\{stl", cell):  # 「○○站：{{stl…}}」は乗換案内なので除く
                    name = m.group(1).strip()
                    if GREY.search(cell) or re.search(r"''\s*\{\{stl\|", cell):  # 灰色・斜体の駅名は未開業
                        off_here = True
            sm = status_re.match(cell)
            if sm:
                off_here = True
                pending_off = max(pending_off, int(sm.group(1) or 1))
        if pending_off > 0:
            pending_off -= 1  # 駅名の無い行も rowspan の行数に数える
        if name is None:
            continue
        seq += 1
        res.append({"line": ref, "seq": seq, "name": name, "operating": int(not (off_here or covered or section_off))})
    return res


def main() -> None:
    city = sys.argv[1]
    offline = "--offline" in sys.argv
    cfg = json.loads((ROOT / "config" / f"{city}.json").read_text(encoding="utf-8"))["reference"]
    out_dir = ROOT / "raw" / city
    tpl_dir = out_dir / "wiki_templates"
    wt_path = out_dir / "wikipedia_zh.wikitext"
    if not offline:
        wt_path.write_text(fetch_wikitext(cfg["page"]), encoding="utf-8")
        meta = {"page": cfg["page"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        (out_dir / "wikipedia_zh.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    lua_path = out_dir / "wikipedia_line_colors.lua"
    if not offline and cfg.get("color_module"):
        lua_path.write_text(fetch_raw(cfg["color_module"]), encoding="utf-8")
    if lua_path.exists():
        colors = parse_colors(lua_path.read_text(encoding="utf-8"))
        (out_dir / "reference_colors.json").write_text(json.dumps(colors, ensure_ascii=False, indent=2), encoding="utf-8")

    systems = cfg.get("stl_systems", [cfg["stl_system"]])  # 広州7号線の佛山区間は {{stl|佛山地铁|…}}
    stl_re = re.compile(r"\{\{stl\|(?:" + "|".join(map(re.escape, systems)) + r")\|([^}|]+)")
    rows = []
    for ref, text in split_sections(wt_path.read_text(encoding="utf-8"), cfg.get("section_ref_map", {})):
        # 駅一覧が路線ごとのテンプレートにある場合（{{广州地铁1号线车站列表}} など）は中身を読む
        m = re.search(r"\{\{([^{}|]*?车站列表)\s*(\||\}\})", text)
        if m and "{|" not in text:
            name = m.group(1).strip()
            p = tpl_dir / f"{name}.wikitext"
            if not offline:
                tpl_dir.mkdir(parents=True, exist_ok=True)
                p.write_text(fetch_raw("Template:" + name), encoding="utf-8")
            text = p.read_text(encoding="utf-8")
        rows.extend(parse_rows(ref, text, stl_re))

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
