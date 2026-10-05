"""駅名の表記変換と読み付与（普通話）。

- to_name_ja(): 簡体字 → 繁体字 → 日本新字体（OpenCC s2t → t2jp）＋ 上書き辞書
- reading_cmn(): 声調付きピンイン（分かち書き）とカタカナ

上書き辞書（overrides/ 配下, UTF-8 JSON）:
  chars_ja.json        字単位の補正 {"t2jpの結果の字": "採る字"}（例: 竜→龍）
  names_ja.json        駅名単位の日本漢字表記 {"原表記": "日本漢字"}
  pinyin_words.json    語（字列）単位のピンイン {"莘庄": "xīn zhuāng"}（多音字・地名の例外）
カタカナは音節の対応表（PINYIN→KANA）から機械的に作る。付録 A の表記を正として規則を合わせてある。

将来、文章を貼り付けて変換する別ページ（段階 4）でも使えるよう、駅データに依存しない形にしている。
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

import opencc
from pypinyin import Style, lazy_pinyin, load_phrases_dict

ROOT = Path(__file__).resolve().parent.parent
OVR = ROOT / "overrides"

_S2T = opencc.OpenCC("s2t")
_T2JP = opencc.OpenCC("t2jp")


def _load(name: str) -> dict:
    p = OVR / name
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


CHARS_JA = _load("chars_ja.json")
NAMES_JA = _load("names_ja.json")
PINYIN_WORDS = _load("pinyin_words.json")

# pypinyin にも語として教え、前後の字の多音字判定に効かせる
load_phrases_dict({w: [[s] for s in p.split()] for w, p in PINYIN_WORDS.items()})

MIDDOT = "·"  # 原表記・ピンインでの区切り（U+00B7）
MIDDOT_JA = "・"
_DOTS = re.compile(r"[·・･‧•]")


def normalize_orig(name: str) -> str:
    """原表記の正規化（区切り点を U+00B7 に統一、空白除去）。"""
    name = unicodedata.normalize("NFKC", name).strip()
    name = _DOTS.sub(MIDDOT, name)
    return re.sub(r"\s+", "", name)


def to_name_ja(orig: str) -> str:
    if orig in NAMES_JA:
        return NAMES_JA[orig]
    out = _T2JP.convert(_S2T.convert(orig))
    out = "".join(CHARS_JA.get(c, c) for c in out)
    return out.replace(MIDDOT, MIDDOT_JA)


# ---------------------------------------------------------------- 分かち書き
# 末尾の通名（分かち書きする語）。長いものから照合する。
GENERIC_SUFFIXES = [
    "火车站", "航站楼", "博物馆", "公园", "公路", "大道", "大街", "大桥", "路", "街", "寺",
]
DIRECTIONS = set("东南西北中")
NUMERALS = set("一二三四五六七八九十")
DIGITS = {"0": "零", "1": "一", "2": "二", "3": "三", "4": "四", "5": "五",
          "6": "六", "7": "七", "8": "八", "9": "九"}
# 語頭に来て独立した語にする固有名（都市名など）
PREFIX_WORDS = ["上海"]
# 語としてまとまった通名（前の固有名と分かち書き）。この語自体は続け書き。長いものから照合する。
TAIL_WORDS = ["开发区", "保税区", "大学城", "新城", "新村", "大学", "中心"]
# 分かち書きの上書き {"駅名（区切り点ごと）": "語 語 語"}。語の頭に + を付けると前の語とカナで続ける。
SEGMENTS = _load("segments.json")


def segment(name: str) -> list[list[tuple[str, bool]]]:
    """駅名を語に分ける。

    戻り値は区切り点（·）ごとのグループのリスト。各グループは (語, 次の語とカナで続けるか) のリスト。
    例: 海天三路 → [[("海天", False), ("三", True), ("路", False)]]
    """
    return [_segment_part(part) for part in name.split(MIDDOT)]


def _segment_part(s: str) -> list[tuple[str, bool]]:
    if s in SEGMENTS:
        toks = SEGMENTS[s].split()
        out = []
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            out.append((t.lstrip("+"), nxt.startswith("+")))
        return out
    s = "".join(DIGITS.get(c, c) for c in s)

    # 「n号」は語として切り出す（浦东1号2号航站楼 → Pǔdōng Yī Hào Èr Hào Hángzhànlóu）
    m = re.match(r"^(.+?)((?:[一二三四五六七八九十]+号)+)(.*)$", s)
    if m:
        pre, nums, rest = m.groups()
        segs = []
        for n in re.findall(r"[一二三四五六七八九十]+号", nums):
            segs += [(n[:-1], True), ("号", False)]
        return _segment_part(pre) + segs + (_segment_part(rest) if rest else [])

    head: list[tuple[str, bool]] = []
    tail: list[tuple[str, bool]] = []
    for suf in GENERIC_SUFFIXES:
        if s.endswith(suf) and len(s) > len(suf):
            core = s[: -len(suf)]
            tail = [(suf, False)]
            # 方位・数字＋路 は「Dōng Lù」「Sān Lù」と分かち書きし、カナでは続ける（ドンルー）
            if suf in ("路", "公路", "大道") and len(core) >= 3 and (core[-1] in DIRECTIONS or core[-1] in NUMERALS):
                tail = [(core[-1], True)] + tail
                core = core[:-1]
            s = core
            break
    else:
        for tw in TAIL_WORDS:
            if s.endswith(tw) and len(s) > len(tw):
                tail = [(tw, False)]
                s = s[: -len(tw)]
                break
        else:
            # 語末の方位（三林东 → Sānlín Dōng）
            if len(s) >= 3 and s[-1] in DIRECTIONS:
                tail = [(s[-1], False)]
                s = s[:-1]

    for pw in PREFIX_WORDS:
        if s.startswith(pw) and len(s) > len(pw):
            head = [(pw, False)]
            s = s[len(pw):]
            break

    # 残りの固有名部分: 3字以下は続け書き、4字以上は2字ずつ（端数は末尾の語に寄せる）
    if len(s) <= 3:
        core_words = [s] if s else []
    else:
        core_words = []
        i = 0
        while len(s) - i > 3:
            core_words.append(s[i:i + 2])
            i += 2
        core_words.append(s[i:])
        if len(core_words[-1]) == 1:  # 念のため
            core_words[-2] += core_words.pop()
    return head + [(w, False) for w in core_words] + tail


# ---------------------------------------------------------------- ピンイン
@lru_cache(maxsize=None)
def _syllables(word_in_context: str) -> tuple[list[str], list[str]]:
    tone = lazy_pinyin(word_in_context, style=Style.TONE, neutral_tone_with_five=False)
    plain = lazy_pinyin(word_in_context, style=Style.NORMAL, v_to_u=False)
    return tone, plain


def _word_pinyin(full: str) -> list[tuple[str, str]]:
    """名前全体を文脈ごと変換し、字ごとの (声調付き, 声調なし) を返す。"""
    s = "".join(DIGITS.get(c, c) for c in full)
    tone, plain = _syllables(s)
    res = list(zip(tone, plain))
    # 上書き辞書（語単位）を最長一致で当てる
    i = 0
    while i < len(s):
        hit = None
        for w in sorted(PINYIN_WORDS, key=len, reverse=True):
            if s.startswith(w, i):
                hit = w
                break
        if hit:
            sy = PINYIN_WORDS[hit].split()
            for k, t in enumerate(sy):
                res[i + k] = (t, _strip_tone(t))
            i += len(hit)
        else:
            i += 1
    return res


_TONE_STRIP = str.maketrans("āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü", "aaaaeeeeiiiioooouuuuvvvvv")


def _strip_tone(t: str) -> str:
    return t.translate(_TONE_STRIP)


def reading_cmn(name: str) -> dict:
    """普通話の読み。{"roman": 声調付きピンイン, "kana": カタカナ}"""
    groups = segment(name)
    flat = name.replace(MIDDOT, "")
    sy = _word_pinyin(flat)
    pos = 0
    roman_groups, kana_groups = [], []
    for g in groups:
        rwords, kwords = [], []
        kbuf = ""
        for word, join_next in g:
            n = len(word)
            ws = sy[pos:pos + n]
            pos += n
            rwords.append(_roman_word([t for t, _ in ws]))
            kbuf += "".join(syllable_to_kana(p) for _, p in ws)
            if not join_next:
                kwords.append(kbuf)
                kbuf = ""
        if kbuf:
            kwords.append(kbuf)
        roman_groups.append(" ".join(rwords))
        kana_groups.append("・".join(kwords))
    return {"roman": f" {MIDDOT} ".join(roman_groups), "kana": "／".join(kana_groups)}


def _roman_word(syls: list[str]) -> str:
    out = ""
    for i, s in enumerate(syls):
        if i > 0 and s and _strip_tone(s[0]) in "aoe":
            out += "'"
        out += s
    return out[:1].upper() + out[1:]


# ---------------------------------------------------------------- カタカナ
# 声母ごとの「ア・イ・ウ・エ・オ」段
ROWS = {
    "":   ("ア", "イ", "ウ", "エ", "オ"),
    "b":  ("バ", "ビ", "ブ", "ベ", "ボ"),
    "p":  ("パ", "ピ", "プ", "ペ", "ポ"),
    "m":  ("マ", "ミ", "ム", "メ", "モ"),
    "f":  ("ファ", "フィ", "フ", "フェ", "フォ"),
    "d":  ("ダ", "ディ", "ドゥ", "デ", "ド"),
    "t":  ("タ", "ティ", "トゥ", "テ", "ト"),
    "n":  ("ナ", "ニ", "ヌ", "ネ", "ノ"),
    "l":  ("ラ", "リ", "ル", "レ", "ロ"),
    "g":  ("ガ", "ギ", "グ", "ゲ", "ゴ"),
    "k":  ("カ", "キ", "ク", "ケ", "コ"),
    "h":  ("ハ", "ヒ", "フ", "ヘ", "ホ"),
    "j":  ("ジャ", "ジ", "ジュ", "ジェ", "ジョ"),
    "q":  ("チャ", "チ", "チュ", "チェ", "チョ"),
    "x":  ("シャ", "シ", "シュ", "シェ", "ショ"),
    "zh": ("ジャ", "ジ", "ジュ", "ジェ", "ジョ"),
    "ch": ("チャ", "チ", "チュ", "チェ", "チョ"),
    "sh": ("シャ", "シ", "シュ", "シェ", "ショ"),
    "r":  ("ラ", "リ", "ル", "レ", "ロ"),
    "z":  ("ザ", "ズ", "ズ", "ゼ", "ゾ"),
    "c":  ("ツァ", "ツ", "ツ", "ツェ", "ツォ"),
    "s":  ("サ", "ス", "ス", "セ", "ソ"),
}
A, I, U, E, O = range(5)
# 拗音（-iao など）で使う形
PALATAL_A = {"b": "ビャ", "p": "ピャ", "m": "ミャ", "n": "ニャ", "l": "リャ",
             "j": "ジャ", "q": "チャ", "x": "シャ", "d": "ディア", "t": "ティア"}
# 声母なし音節（y・w 表記）
ZERO_INITIAL = {
    "a": "アー", "ai": "アイ", "ao": "アオ", "an": "アン", "ang": "アン", "o": "オー", "ou": "オウ",
    "e": "オー", "ei": "エイ", "en": "エン", "eng": "オン", "er": "アル",
    "yi": "イー", "ya": "ヤー", "yao": "ヤオ", "yan": "イエン", "yang": "ヤン", "ye": "イエ",
    "yin": "イン", "ying": "イン", "yo": "ヨー", "you": "ヨウ", "yong": "ヨン",
    "yu": "ユー", "yue": "ユエ", "yuan": "ユエン", "yun": "ユン",
    "wu": "ウー", "wa": "ワー", "wai": "ワイ", "wan": "ワン", "wang": "ワン",
    "wei": "ウェイ", "wen": "ウェン", "weng": "ウォン", "wo": "ウォー",
}
INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
            "j", "q", "x", "r", "z", "c", "s"]


def syllable_to_kana(syl: str) -> str:
    """声調なしピンイン 1 音節 → カタカナ。ü は v で受け取る（lv, nve）。"""
    syl = syl.lower().replace("ü", "v")
    if not syl:
        return ""
    if not syl.isalpha():
        return syl
    if syl in ZERO_INITIAL:
        return ZERO_INITIAL[syl]
    ini = next((x for x in INITIALS if syl.startswith(x)), "")
    fin = syl[len(ini):]
    row = ROWS.get(ini, ROWS[""])
    jqx = ini in ("j", "q", "x")
    if jqx and fin.startswith("u"):  # j/q/x + u は ü
        fin = "v" + fin[1:]

    # 単母音の開音節は長音
    simple = {
        "a": row[A] + "ー", "ai": row[A] + "イ", "ao": row[A] + "オ", "an": row[A] + "ン", "ang": row[A] + "ン",
        "o": row[O] + "ー", "ou": row[O] + "ウ", "ong": row[O] + "ン",
        "e": row[O] + "ー", "ei": row[E] + "イ", "en": row[E] + "ン", "eng": row[O] + "ン",
        "i": row[I] + "ー", "u": row[U] + "ー",
    }
    if ini == "f" and fin == "eng":
        return "フォン"
    if fin in simple:
        return simple[fin]

    i_ = row[I]
    if fin == "ia":
        return "ジャー" if ini == "j" else i_ + "ア"
    if fin == "iao":
        return PALATAL_A.get(ini, i_ + "ア") + "オ"
    if fin == "ian":
        return i_ + "エン"
    if fin == "iang":
        return i_ + "アン"
    if fin == "ie":
        return i_ + "エ"
    if fin in ("in", "ing"):
        return i_ + "ン"
    if fin == "iong":
        return i_ + "オン"
    if fin == "iu":
        return i_ + "ウ"

    # ü 系（j/q/x, l/n）
    vrow = {"j": "ジュ", "q": "チュ", "x": "シュ", "l": "リュ", "n": "ニュ"}.get(ini, row[U])
    if fin == "v":
        return vrow + "ー"
    if fin == "ve" or fin == "ue" and ini in ("l", "n"):
        return vrow + "エ"
    if fin == "van":
        return vrow + "エン"
    if fin == "vn":
        return vrow + "ン"

    # u 介音（h は ua・uai・uan・uang でホア系にする）
    u_ = "ホ" if ini == "h" and fin in ("ua", "uai", "uan", "uang") else row[U]
    if fin == "ua":
        return u_ + "ア"
    if fin == "uai":
        return u_ + "アイ"
    if fin in ("uan", "uang"):
        return u_ + "アン"
    if fin == "ui":
        return row[U] + "イ"
    if fin == "un":
        return row[U] + "ン"
    if fin == "uo":
        return row[U] + "オ"
    return syl  # 想定外はそのまま（検証レポートで拾う）
