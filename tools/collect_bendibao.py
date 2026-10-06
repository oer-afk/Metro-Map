"""本地宝（bendibao.com）の地下鉄の「首尾班车经过各车站时间」から、各駅の始発・終電の通過時刻を集める。

使い方:  python tools/collect_bendibao.py [shenzhen|guangzhou|shanghai …]   （省略時は 3 都市）

  本地宝は、各都市の地下鉄の公式の時刻（各駅の始発・終電）を路線ごとに転載している第三者のサイト。
  公式の情報源（上海・広州の事業者サイト）に届かないため、その代わりに使う。
  深圳は公式の時刻（Wikipedia のモジュール）と比べて、転載の確かさを確かめる（build_times.py）。
  各都市の /ditie/ にある路線ごとのページ（shike_<番号>.shtml）を、2 秒おきに 1 ページずつ取得する。
  サイトが人間かどうかの確認（パズルの CAPTCHA）を出したら、その時点で取得をやめる（回避はしない）。
  2026-10-06 の取得では、深圳の全ページを取ったあと、広州の 3 ページ目で CAPTCHA が出たため、深圳だけを保存した。
保存先: raw/<id>/bendibao_timetable.json  ページの HTML は保存せず、表の値だけを残す
  {"<ページ番号>": {"title": 路線名, "url": …, "panels": {"workday": [表, …], "weekend": …}}}
  表: {"cols": [["首班车", "往碧头"], …], "rows": [["红岭南", "06:00", "—", …], …]}
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
HEADERS = {"User-Agent": "Mozilla/5.0 (metro-map-learning; personal study)"}
HOSTS = {"shenzhen": "m.bendibao.com", "guangzhou": "m.gz.bendibao.com", "shanghai": "m.sh.bendibao.com"}
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")


def get(url: str) -> str:
    for i in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.encoding = r.apparent_encoding
            if r.status_code == 200:
                return r.text
        except Exception:  # noqa: BLE001
            pass
        time.sleep(5 * (i + 1))
    return ""


def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_table(t: str) -> dict:
    trs = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.S)
    cells = [re.findall(r"<td([^>]*)>(.*?)</td>", tr, re.S) for tr in trs]
    if len(cells) < 3:
        return {}
    groups = []  # 1 行目: 方向 | 首班车(colspan 2) | 末班车(colspan 2)
    for attr, c in cells[0][1:]:
        m = re.search(r'colspan="?(\d+)', attr)
        groups += [text(c)] * (int(m.group(1)) if m else 1)
    dirs = [text(c) for _, c in cells[1][1:]]
    cols = [[g, d] for g, d in zip(groups, dirs)]
    rows = [[text(c) for _, c in r] for r in cells[2:] if r]
    return {"cols": cols, "rows": rows}


def parse_page(page: str) -> dict:
    title = text(re.search(r"<h1>(.*?)</h1>", page, re.S).group(1)) if "<h1>" in page else ""
    panels = {}
    for m in re.finditer(r'<div class="ditie-time-panel" data-tab="(\w+)"[^>]*>(.*?)(?=<div class="ditie-time-panel"|<div class="line-list"|$)', page, re.S):
        tabs = [parse_table(t) for t in re.findall(r"<table[^>]*>(.*?)</table>", m.group(2), re.S)]
        notes = [text(p) for p in re.findall(r'<p class="time">(.*?)</p>', m.group(2), re.S)]
        panels[m.group(1)] = {"notes": notes, "tables": [t for t in tabs if t]}
    return {"title": re.sub(r"运营时间$", "", title), "panels": panels}


def main() -> None:
    cities = [a for a in sys.argv[1:] if a in HOSTS] or list(HOSTS)
    for nid in cities:
        host = HOSTS[nid]
        index = get(f"https://{host}/ditie/")
        ids = sorted(set(re.findall(r'href="/ditie/shike_(\d+)\.shtml"', index)), key=int)
        out = {"_source": f"https://{host}/ditie/ （本地宝。公式時刻の転載）", "_fetched": date.today().isoformat()}
        for pid in ids:
            url = f"https://{host}/ditie/shike_{pid}.shtml"
            page = get(url)
            if "拼图验证" in page or "captcha" in page.lower():
                print(f"{nid} {pid}: CAPTCHA が出たので取得をやめる（{nid} は保存しない）", flush=True)
                return
            if page:
                rec = parse_page(page)
                rec["url"] = url
                out[pid] = rec
                n = sum(len(t["rows"]) for p in rec["panels"].values() for t in p["tables"])
                print(f"{nid} {pid} {rec['title']}: {n} rows", flush=True)
            time.sleep(2)
        p = ROOT / "raw" / nid / "bendibao_timetable.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"-> {p}  ({len(out) - 2} pages)", flush=True)


if __name__ == "__main__":
    main()
