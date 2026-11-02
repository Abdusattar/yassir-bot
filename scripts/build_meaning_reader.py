"""Смысловой перевод по сурам - для отдельного чтения и панели аята (02.11.2026).

Один формат на все переводы: mushaf_data/meaning/<перевод>/<сура>.json =
{"s": 21, "t": ["аят 1", "аят 2", ...]}. Читатель смысла и панель удержания
берут текст отсюда - одним загрузчиком, сура весит десятки КБ, а не весь Коран.

Переводы (только реальные источники, права подтверждены пользователем):
  ru_kuliev  - Кулиев, api.quran.com id 45 (права 28.08.2026)
  ru_abuadel - Абу Адель, api.quran.com id 79 (права 02.11.2026)
  ky, uz, zh - из уже лежащих mushaf_data/meaning_{lang}.json (quranenc.com)

Проверки: в каждом переводе 6236 непустых аятов; скачанный Кулиев сверяется
с полем meaning в page*.json - иначе в приложении жили бы два разных Кулиева.

    python scripts/build_meaning_reader.py           # всё
    python scripts/build_meaning_reader.py ru_abuadel
"""
import html
import json
import pathlib
import re
import sys
import time
from html.parser import HTMLParser

import requests

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "mushaf_data"
OUT = DATA / "meaning"
API = {"ru_kuliev": 45, "ru_abuadel": 79}
LOCAL = ("ky", "uz", "zh")
TOTAL = 6236

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


class _Text(HTMLParser):
    """Текст без тегов; сноски <sup>...</sup> выбрасываются целиком."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.sup = [], 0

    def handle_starttag(self, tag, attrs):
        if tag == "sup":
            self.sup += 1

    def handle_endtag(self, tag):
        if tag == "sup" and self.sup:
            self.sup -= 1

    def handle_data(self, data):
        if not self.sup:
            self.out.append(data)


def clean(s):
    p = _Text()
    p.feed(s or "")
    p.close()
    return re.sub(r"\s+", " ", html.unescape("".join(p.out))).strip()


def fetch_surah(rid, surah):
    for attempt in range(4):
        try:
            r = requests.get(f"https://api.quran.com/api/v4/quran/translations/{rid}",
                             params={"chapter_number": surah}, timeout=30)
            r.raise_for_status()
            return [clean(x["text"]) for x in r.json()["translations"]]
        except Exception:
            if attempt == 3:
                raise
            time.sleep(2 + attempt * 2)


def by_surah_api(rid):
    out = {}
    for s in range(1, 115):
        out[s] = fetch_surah(rid, s)
        time.sleep(0.15)
    return out


def by_surah_local(lang):
    d = json.loads((DATA / f"meaning_{lang}.json").read_text(encoding="utf-8"))
    out = {}
    for key, text in d.items():
        s, a = map(int, key.split(":"))
        if isinstance(text, dict):            # на случай формата {text, footnotes}
            text = text.get("text", "")
        out.setdefault(s, {})[a] = clean(text)
    return {s: [m[a] for a in sorted(m)] for s, m in out.items()}


def check(name, surahs):
    n = sum(len(v) for v in surahs.values())
    empty = [f"{s}:{i + 1}" for s, v in surahs.items() for i, t in enumerate(v) if not t]
    if len(surahs) != 114 or n != TOTAL or empty:
        raise SystemExit(f"{name}: сур {len(surahs)}, аятов {n}, пустых {len(empty)} {empty[:5]}")


def compare_kuliev(surahs):
    """Кулиев из API против поля meaning в листах мусхафа."""
    diff = total = 0
    for p in DATA.glob("page*.json"):
        if "_" in p.stem:
            continue
        for a in json.loads(p.read_text(encoding="utf-8"))["ayahs"]:
            if not a.get("meaning"):
                continue
            total += 1
            if clean(a["meaning"]) != surahs[a["surah"]][a["ayah"] - 1]:
                diff += 1
                if diff <= 3:
                    print(f"  расхождение {a['surah']}:{a['ayah']}")
    print(f"  Кулиев: сверено с листами {total}, расхождений {diff}")
    if diff:
        raise SystemExit("Кулиев из API не совпал с листами - разобраться до выкладки")


def write(name, surahs):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    for s, texts in surahs.items():
        (d / f"{s}.json").write_text(json.dumps({"s": s, "t": texts}, ensure_ascii=False,
                                                separators=(",", ":")), encoding="utf-8")


def main():
    names = sys.argv[1:] or list(API) + list(LOCAL)
    for name in names:
        print(name)
        surahs = by_surah_api(API[name]) if name in API else by_surah_local(name)
        check(name, surahs)
        if name == "ru_kuliev":
            compare_kuliev(surahs)
        write(name, surahs)
        print(f"  записано 114 сур, {TOTAL} аятов")


if __name__ == "__main__":
    main()
