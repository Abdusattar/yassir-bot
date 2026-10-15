"""Разметка страниц тренажёра слов из мусхафа приложения (15.10.2026).

Таблица PAGES в core/quran_pages.py строится отсюда, а не из стороннего
датасета: mushaf_data/pageN.json - это ровно те страницы, что студент видит
на экране (KFGQPC V4, издание 1441 г.х., сверено с QUL скриптом
scripts/audit_mushaf_layout.py). Прежняя таблица (zonetecde/mushaf-layout,
стр. 2-221) была другим изданием: на стр. 120-123 и 144-145 граница
сдвинута на один аят, а стр. 221 обрезана по Юнус (без Худ 1-5).
С Фатихи (стр. 1) - тоже с 15.10.2026.

Проверки перед записью - любая не прошла, файл не трогаем:
  - все 6236 аятов на месте, каждый ровно на одной странице;
  - последний аят каждой из 114 сур = известное число её аятов;
  - аяты внутри страницы идут подряд, без дыр.

    python scripts/build_quran_pages.py           # только проверить
    python scripts/build_quran_pages.py --write   # переписать PAGES
"""
import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TARGET = ROOT / "core" / "quran_pages.py"
FIRST_PAGE, LAST_PAGE = 1, 604   # с Фатихой (решение пользователя 15.10.2026)

# Число аятов в каждой суре (1..114) - общеизвестное, сверка по нему.
AYAT = [7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99, 128, 111,
        110, 98, 135, 112, 78, 118, 64, 77, 227, 93, 88, 69, 60, 34, 30, 73, 54, 45, 83,
        182, 88, 75, 85, 54, 53, 89, 59, 37, 35, 38, 29, 18, 45, 60, 49, 62, 55, 78, 96,
        29, 22, 24, 13, 14, 11, 11, 18, 12, 12, 30, 52, 52, 44, 28, 28, 20, 56, 40, 31,
        50, 40, 46, 42, 29, 19, 36, 25, 22, 17, 19, 26, 30, 20, 15, 21, 11, 8, 8, 19, 5,
        8, 8, 11, 11, 8, 3, 9, 5, 4, 7, 3, 6, 3, 5, 4, 5, 6]


def read_pages():
    pages, seen, errors = {}, {}, []
    for p in range(1, 605):
        d = json.loads((ROOT / "mushaf_data" / f"page{p}.json").read_text(encoding="utf-8"))
        by_surah = {}
        for a in d["ayahs"]:
            s, n = int(a["surah"]), int(a["ayah"])
            if (s, n) in seen and seen[(s, n)] != p:
                errors.append(f"аят {s}:{n} на стр. {seen[(s, n)]} и {p}")
            seen.setdefault((s, n), p)
            by_surah.setdefault(s, []).append(n)
        for s, ns in by_surah.items():
            if sorted(set(ns)) != list(range(min(ns), max(ns) + 1)):
                errors.append(f"стр. {p}: дыра в суре {s}")
        pages[p] = {s: (min(ns), max(ns)) for s, ns in sorted(by_surah.items())}
    missing = [f"{s}:{n}" for s in range(1, 115) for n in range(1, AYAT[s - 1] + 1)
               if (s, n) not in seen]
    if missing:
        errors.append(f"нет аятов: {missing[:10]}")
    extra = [f"{s}:{n}" for (s, n) in seen if n > AYAT[s - 1]]
    if extra:
        errors.append(f"лишние аяты: {extra[:10]}")
    return pages, errors


def render(pages):
    lines = ["PAGES = {"]
    for p in range(FIRST_PAGE, LAST_PAGE + 1):
        body = ", ".join(f"{s}: ({a}, {b})" for s, (a, b) in pages[p].items())
        lines.append(f"    {p}: {{{body}}},")
    lines.append("}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    pages, errors = read_pages()
    if errors:
        print("ОШИБКИ:", *errors, sep="\n  ")
        sys.exit(1)
    multi = sum(1 for p in range(FIRST_PAGE, LAST_PAGE + 1) if len(pages[p]) > 1)
    print(f"ok: 6236 аятов, 114 сур, страниц {FIRST_PAGE}-{LAST_PAGE}, с переходом сур: {multi}")
    if args.write:
        src = TARGET.read_text(encoding="utf-8")
        new, n = re.subn(r"^PAGES = \{\n.*?^\}", lambda _: render(pages), src, flags=re.S | re.M)
        if n != 1:
            print("PAGES в core/quran_pages.py не найден")
            sys.exit(1)
        TARGET.write_text(new, encoding="utf-8")
        print("записано:", TARGET)


if __name__ == "__main__":
    main()
