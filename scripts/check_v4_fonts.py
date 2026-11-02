"""Проверка шрифтов мусхафа V4 на CDN (02.11.2026).

Зачем: 02.11 у tarteel пропал p328.woff2 (404), и лист 328 рисовался шрифтом
листа 327 - чужими словами. Скрипт ловит оба вида поломки:
  - файла нет (не 200) на основном CDN и на зеркале quran.foundation;
  - файл есть, но в нём нет кодов слов своего листа (не тот лист).
Сверяет обе раскладки: мединскую (mushaf_data/page*.json) и Дар аль-Маариф
(mushaf_data/dm/page*.json, у слов с fp - шрифт мединского листа fp).

    python scripts/check_v4_fonts.py            # все 604
    python scripts/check_v4_fonts.py 327 328    # выборочно
"""
import io
import json
import pathlib
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from fontTools.ttLib import TTFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "mushaf_data"
MAIN = "https://static-cdn.tarteel.ai/qul/fonts/quran_fonts/v4-tajweed/woff2/p{}.woff2"
MIRROR = "https://verses.quran.foundation/fonts/quran/hafs/v4/colrv1/woff2/p{}.woff2"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception as e:  # сеть
        return str(e), b""


def needed_codes():
    """{номер шрифта: множество кодов} по обеим раскладкам."""
    need = {}
    for path in sorted(DATA.glob("page*.json")) + sorted((DATA / "dm").glob("page*.json")):
        stem = path.stem
        if "_" in stem:          # переводы - те же коды
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        page = int(stem[4:])
        for line in d.get("lines", []):
            for t in line.get("tokens", []):
                code = t.get("code_v4")
                if not code:
                    continue
                fp = t.get("fp") or (d.get("font_page") if path.parent.name == "dm" else None) or page
                need.setdefault(int(fp), set()).update(ord(ch) for ch in code)
    return need


def check(page, codes):
    out = []
    for name, tpl in (("main", MAIN), ("mirror", MIRROR)):
        status, body = fetch(tpl.format(page))
        if status != 200:
            out.append(f"{name}: HTTP {status}")
            continue
        try:
            cmap = TTFont(io.BytesIO(body)).getBestCmap()
        except Exception as e:
            out.append(f"{name}: не читается ({e})")
            continue
        miss = [c for c in codes if c not in cmap]
        if miss:
            out.append(f"{name}: нет {len(miss)} из {len(codes)} кодов")
    return page, out


def main():
    need = needed_codes()
    pages = [int(a) for a in sys.argv[1:]] or sorted(need)
    bad = 0
    with ThreadPoolExecutor(16) as ex:
        for page, problems in ex.map(lambda p: check(p, need.get(p, set())), pages):
            if problems:
                bad += 1
                print(f"p{page}: " + "; ".join(problems))
    print(f"проверено {len(pages)} шрифтов, с проблемами: {bad}")


if __name__ == "__main__":
    main()
