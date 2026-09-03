#!/usr/bin/env python3
"""Сверка НАШЕЙ построчной раскладки мусхафа с печатной мединской.

Эталон — KFGQPC V4 layout (1441H print) на QUL
(`qul.tarteel.ai/resources/mushaf-layout/19?page=N`): ровно то издание,
под которое нарисован наш шрифт. Это и есть «мединский мусхаф», по
которому студенты учат с бумаги — построчная разбивка обязана совпадать,
иначе заучивание по строкам в приложении и по книге расходится (причина,
названная пользователем 02.09.2026).

**Ловушка, без которой сверка врёт**: у QUL знак конца аята размечен тем
же тегом, что слова, но с классом `char-end` вместо `char-word`, и
получает СВОЮ позицию (N+1 внутри аята). Считать его словом нельзя -
иначе расходится счёт в каждом аяте. Здесь он отфильтрован по классу.

Использование:
    python scripts/audit_mushaf_layout.py                # все 604
    python scripts/audit_mushaf_layout.py --pages 1-10   # выборка
    python scripts/audit_mushaf_layout.py --out отчёт.json

Кэш скачанных страниц QUL - sources/qul_layout_cache/, повторный запуск
сети не трогает.
"""
import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "..", "mushaf_data")
CACHE_DIR = os.path.join(SCRIPT_DIR, "..", "sources", "qul_layout_cache")

QUL_URL = "https://qul.tarteel.ai/resources/mushaf-layout/19?page={page}"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; yassir-bot/1.0)"}
_RETRIES = 3

# Слово QUL: тег с классом char-word (char-end - это знак конца аята,
# НЕ слово, см. докстрочку модуля).
_WORD_RE = re.compile(
    r'<span class="char\s+(char-word|char-end)\s*"[^>]*?data-location="([^"]*)"',
    re.S,
)
_LINE_RE = re.compile(r'data-line="(\d+)"')


def fetch_qul_page(page):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"page{page}.html")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return f.read()
    last_err = None
    for attempt in range(_RETRIES):
        try:
            req = urllib.request.Request(QUL_URL.format(page=page), headers=_HEADERS)
            with urllib.request.urlopen(req, timeout=30) as r:
                html = r.read().decode("utf-8", "replace")
            with open(path, "w", encoding="utf-8") as f:
                f.write(html)
            return html
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            time.sleep(2 * (attempt + 1))
    raise last_err


def qul_lines(page):
    """[[«сура:аят:позиция», ...], ...] по строкам печатной страницы."""
    html = fetch_qul_page(page)
    line_starts = [(m.start(), int(m.group(1))) for m in _LINE_RE.finditer(html)]
    out = {}
    for m in _WORD_RE.finditer(html):
        if m.group(1) != "char-word":
            continue
        pos = m.start()
        cur = None
        for lp, ln in line_starts:
            if lp <= pos:
                cur = ln
            else:
                break
        out.setdefault(cur, []).append(m.group(2))
    return [out[k] for k in sorted(out)]


def our_lines(page):
    path = os.path.join(DATA_DIR, f"page{page}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return [
        [f"{t['surah']}:{t['ayah']}:{t['position']}"
         for t in (l.get("tokens") or []) if t.get("type") == "word"]
        for l in d["lines"] if l.get("type") == "text"
    ]


def compare(page):
    """Сколько слов стоит не на своей строке относительно печати."""
    q, o = qul_lines(page), our_lines(page)
    if o is None:
        return {"page": page, "error": "нет наших данных"}
    qmap = {w: i for i, line in enumerate(q) for w in line}
    omap = {w: i for i, line in enumerate(o) for w in line}
    wrong = [w for w in qmap if omap.get(w) != qmap[w]]
    return {
        "page": page,
        "qul_lines": len(q), "our_lines": len(o),
        "words": len(qmap), "wrong": len(wrong),
        "missing": [w for w in qmap if w not in omap],
        "extra": [w for w in omap if w not in qmap],
    }


def parse_pages(spec):
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", default="1-604")
    ap.add_argument("--out", default=os.path.join(SCRIPT_DIR, "..", "sources", "layout_audit.json"))
    args = ap.parse_args()

    results, bad = [], []
    for page in parse_pages(args.pages):
        try:
            r = compare(page)
        except Exception as e:
            r = {"page": page, "error": f"{type(e).__name__}: {e}"}
        results.append(r)
        if r.get("error") or r.get("wrong"):
            bad.append(r)
            mark = r.get("error") or f"{r['wrong']}/{r['words']} слов не на своей строке"
            print(f"стр {page}: {mark}", flush=True)
        if page % 25 == 0:
            print(f"...обработано до стр. {page}, расхождений пока: {len(bad)}", flush=True)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    ok = len(results) - len(bad)
    print(f"\nИТОГО: страниц проверено {len(results)}, совпадает {ok}, расходится {len(bad)}")
    if bad:
        print("Расходящиеся страницы:", [r["page"] for r in bad])


if __name__ == "__main__":
    main()
