#!/usr/bin/env python3
"""Раскладка «Дар аль-Маариф (египетский)» - второй вариант мусхафа (23.09.2026).

Таджвидный мусхаф Дар аль-Маарифа (Дамаск; у студентов - издание
«Даруль-Мирас», Москва) идёт по раскладке старого мединского издания 1405H:
604 страницы по 15 строк, почерк Усмана Тахи. На QUL она лежит как
`mushaf-layout/15` (KFGQPC V1). Сверено с печатной книгой (PDF archive.org
«quran-with-colour-coded-tajweed») на стр. 3, 121, 300, 586, 600 - строка в
строку, включая страницы, где границы листа расходятся с нашим мединским.

Цветного шрифта 1405 нет (V1 на QUL - только чёрный, слово = один глиф,
буквы не раскрасить), поэтому слова рисуются нашим QPC V4 Tajweed: каждый
токен берётся из нашей раскладки ВМЕСТЕ с его глифом, а глиф живёт в шрифте
своей мединской страницы - это поле `fp` у токена (решение пользователя:
«их раскладка, наши цветные буквы»).

Выход: mushaf_data/dm/page{N}.json (+ _ky/_uz, где у исходных слов есть
перевод). Формат тот же, что у page{N}.json, плюс `fp` у токена, если его
страница шрифта отличается от `font_page` листа.

    python scripts/build_dm_layout.py            # собрать и проверить
    python scripts/build_dm_layout.py --check    # только проверки

Кэш страниц QUL - sources/qul_layout15_cache/ (сеть только при пустом кэше).
"""
import argparse
import collections
import json
import os
import re
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import audit_mushaf_layout as A  # noqa: E402

A.QUL_URL = "https://qul.tarteel.ai/resources/mushaf-layout/15?page={page}"
A.CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "sources", "qul_layout15_cache")

DATA_DIR = os.path.join(SCRIPT_DIR, "..", "mushaf_data")
OUT_DIR = os.path.join(DATA_DIR, "dm")
FONT_URL = "https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/woff2/p{}.woff2"
LANGS = ("ky", "uz")
V4_FONTS = os.path.join(SCRIPT_DIR, "..", "sources", "v4_fonts")   # p{N}.ttf, как на CDN

# Ужимка длинных строк (23.09.2026, просьба пользователя «шрифт не должен
# пострадать»). Наши глифы V4 нарисованы под строки 1441H, и на части строк
# 1405H они выходят длиннее: без поправки кегль всего листа равнялся бы по
# самой длинной строке и падал в среднем на 10%, на худших листах - на
# 25-30%. Поэтому строка длиннее «целевой ширины» листа получает свой
# кегль `fs` (доля от кегля листа), но не меньше 1 - SQUEEZE_MAX; целевая
# ширина - самая длинная строка, ужатая на SQUEEZE_MAX, и не уже медианной.
# Замер по всем 604: кегль листа в среднем 98% мединского, строк с ужимкой
# около четверти, обычно на 4%.
SQUEEZE_MAX = 0.08

_LINE_RE = re.compile(r'<div class="line-container" data-line="(\d+)">\s*<div class="line([^"]*)"')
_CHAR_RE = re.compile(r'<span class="char\s+(char-word|char-end)\s*"[^>]*?data-location="(\d+):(\d+):(\d+)"', re.S)
_SURAH_RE = re.compile(r"surah(\d{3})")


def qul_rows(page):
    """[(номер, вид, данные)] - вид: header (сура), bismillah, text ([(kind, s, a, p)])."""
    html = A.fetch_qul_page(page)
    starts = [(m.start(), int(m.group(1)), m.group(2)) for m in _LINE_RE.finditer(html)]
    rows = []
    for i, (pos, num, cls) in enumerate(starts):
        chunk = html[pos:starts[i + 1][0] if i + 1 < len(starts) else len(html)]
        if "line--surah-name" in cls:
            rows.append((num, "header", int(_SURAH_RE.search(chunk).group(1))))
        elif "line--bismillah" in cls:
            rows.append((num, "bismillah", None))
        else:
            rows.append((num, "text", [(m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4)))
                                       for m in _CHAR_RE.finditer(chunk)]))
    return rows


def load_ours(suffix=""):
    """Слова и концы аятов нашей раскладки: токен + страница его шрифта."""
    words, ends, markers = {}, {}, {}
    names, bism = {}, None
    for p in range(1, 605):
        path = os.path.join(DATA_DIR, "page%d%s.json" % (p, suffix))
        if not os.path.exists(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        last = None
        pending = []
        for line in d["lines"]:
            if line["type"] == "header":
                names[line["surah"]] = line["surah_name_ar"]
            elif line["type"] == "bismillah" and line.get("html"):
                bism = line["html"]
            for t in line.get("tokens") or []:
                t = dict(t, fp=p)
                if t["type"] == "word":
                    last = (t["surah"], t["ayah"])
                    key = (t["surah"], t["ayah"], t["position"])
                    words[key] = t
                    if pending:
                        markers[key] = pending
                        pending = []
                elif t["type"] == "ayah_end":
                    ends[last] = t
                elif t["type"] == "marker":
                    pending.append(t)
    return words, ends, markers, names, bism


_fonts = {}


def _advance(fp, text):
    """Ширина глифов слова в шрифте его листа при кегле 1 (доли em)."""
    if fp not in _fonts:
        from fontTools.ttLib import TTFont
        f = TTFont(os.path.join(V4_FONTS, "p%d.ttf" % fp))
        _fonts[fp] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    cmap, hm, upm = _fonts[fp]
    return sum(hm[cmap[ord(ch)]][0] for ch in text if ord(ch) in cmap) / upm


def squeeze_lines(d):
    """Проставить `fs` длинным строкам листа (см. SQUEEZE_MAX)."""
    widths = []
    for line in d["lines"]:
        if line["type"] != "text" or not line.get("tokens"):
            continue
        w = 0.0
        for t in line["tokens"]:
            if t.get("code_v4"):
                w += _advance(t.get("fp", d["font_page"]), t["code_v4"])
            elif t["type"] == "marker":
                w += 0.45   # ۞ запасным шрифтом, .marker { font-size: 0.45em }
        widths.append((line, w))
    if len(widths) < 8:          # стр. 1-2 и короткие - как есть
        return
    ws = sorted(w for _, w in widths)
    target = max(ws[-1] * (1 - SQUEEZE_MAX), ws[len(ws) // 2])
    for line, w in widths:
        if w > target:
            line["fs"] = round(target / w, 3)


def build_page(page, rows, ours):
    words, ends, markers, names, bism = ours
    lines, fps, placed = [], collections.Counter(), set()
    for num, kind, data in rows:
        if kind == "header":
            lines.append({"line": num, "type": "header", "surah": data, "surah_name_ar": names[data]})
        elif kind == "bismillah":
            lines.append({"line": num, "type": "bismillah", "html": bism})
        else:
            toks = []
            for ck, s, a, p in data:
                if ck == "char-word":
                    toks.extend(dict(m) for m in markers.get((s, a, p), []))
                    toks.append(dict(words[(s, a, p)]))
                else:
                    toks.append(dict(ends[(s, a)]))
            for t in toks:
                fps[t["fp"]] += 1
            placed.update((t["surah"], t["ayah"], t["position"]) for t in toks if t["type"] == "word")
            lines.append({"line": num, "type": "text", "tokens": toks})
    # Слово, которого у QUL 15 нет отдельно, идёт сразу за предыдущим: в
    # 1405 «إِلْ يَاسِينَ» (37:130) - один глиф на позиции 3, а позиция 4 у
    # них - знак конца аята; у нас это два слова.
    for line in lines:
        toks = line.get("tokens") or []
        i = 0
        while i < len(toks):
            t = toks[i]
            if t["type"] == "word":
                nxt = (t["surah"], t["ayah"], t["position"] + 1)
                if nxt in words and nxt not in placed and _missing_in_qul(nxt):
                    toks.insert(i + 1, dict(words[nxt]))
                    placed.add(nxt)
                    fps[words[nxt]["fp"]] += 1
            i += 1
    main_fp = fps.most_common(1)[0][0]
    ayahs, cur = [], None
    for line in lines:
        for t in line.get("tokens") or []:
            if t["fp"] == main_fp:
                del t["fp"]
            if t["type"] == "word":
                if not cur or (cur["surah"], cur["ayah"]) != (t["surah"], t["ayah"]):
                    cur = {"surah": t["surah"], "ayah": t["ayah"], "tokens": []}
                    ayahs.append(cur)
                cur["tokens"].append({k: v for k, v in t.items() if k not in ("surah", "ayah")})
            elif cur and t["type"] == "ayah_end":
                cur["tokens"].append(dict(t))
    surahs = []
    for a in ayahs:
        if a["surah"] not in surahs:
            surahs.append(a["surah"])
    out = {"page": page, "layout": "dm", "font_page": main_fp, "font_url": FONT_URL.format(main_fp),
           "surah_names": [names[s] for s in surahs], "ayahs": ayahs, "lines": lines}
    squeeze_lines(out)
    return out


_QUL_WORDS = None


def _missing_in_qul(key):
    global _QUL_WORDS
    if _QUL_WORDS is None:
        _QUL_WORDS = {(s, a, p) for n in range(1, 605) for _, kind, data in qul_rows(n)
                      if kind == "text" for ck, s, a, p in data if ck == "char-word"}
    return key not in _QUL_WORDS


def check(pages):
    """Каждое слово ровно один раз, по порядку; строки - как у QUL 15."""
    seq = []
    problems = []
    for n, d in pages.items():
        rows = qul_rows(n)
        if len(d["lines"]) != len(rows):
            problems.append("стр %d: рядов %d, у QUL %d" % (n, len(d["lines"]), len(rows)))
        if n > 2 and len(d["lines"]) != 15:
            problems.append("стр %d: рядов %d, не 15" % (n, len(d["lines"])))
        for line, (_, kind, data) in zip(d["lines"], rows):
            if line["type"] != kind:
                problems.append("стр %d ряд %d: %s вместо %s" % (n, line["line"], line["type"], kind))
            if kind == "text":
                got = [(t["surah"], t["ayah"], t["position"]) for t in line["tokens"] if t["type"] == "word"]
                want = [(s, a, p) for ck, s, a, p in data if ck == "char-word"]
                seq.extend(got)
                if [w for w in got if not _missing_in_qul(w)] != want:
                    problems.append("стр %d ряд %d: слова не те" % (n, line["line"]))
    ours = []
    for p in range(1, 605):
        d = json.load(open(os.path.join(DATA_DIR, "page%d.json" % p), encoding="utf-8"))
        for line in d["lines"]:
            ours.extend((t["surah"], t["ayah"], t["position"]) for t in line.get("tokens") or []
                        if t["type"] == "word")
    if seq != ours:
        problems.append("поток слов расходится с нашим: %d против %d" % (len(seq), len(ours)))
    return problems, len(seq)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)
    rows = {n: qul_rows(n) for n in range(1, 605)}
    if not a.check:
        ours = load_ours()
        for n in range(1, 605):
            d = build_page(n, rows[n], ours)
            with open(os.path.join(OUT_DIR, "page%d.json" % n), "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
        for lang in LANGS:
            src = ours
            loc = load_ours("_" + lang)
            words = dict(src[0])
            words.update(loc[0])
            ours_l = (words, src[1], src[2], src[3], src[4])
            have = {p for p in range(1, 605) if os.path.exists(os.path.join(DATA_DIR, "page%d_%s.json" % (p, lang)))}
            made = 0
            for n in range(1, 605):
                if not any(fp in have for fp in _page_fps(n, rows[n], src)):
                    continue
                d = build_page(n, rows[n], ours_l)
                with open(os.path.join(OUT_DIR, "page%d_%s.json" % (n, lang)), "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, separators=(",", ":"))
                made += 1
            print("%s: %d страниц" % (lang, made))
    pages = {n: json.load(open(os.path.join(OUT_DIR, "page%d.json" % n), encoding="utf-8")) for n in range(1, 605)}
    problems, total = check(pages)
    print("слов: %d, проблем: %d" % (total, len(problems)))
    for p in problems[:40]:
        print("  ", p)
    sys.exit(1 if problems else 0)


def _page_fps(n, rows, ours):
    words = ours[0]
    return {words[(s, a, p)]["fp"] for _, kind, data in rows if kind == "text"
            for ck, s, a, p in data if ck == "char-word"}


if __name__ == "__main__":
    main()
