#!/usr/bin/env python3
"""Возвращает аяты на ТУ страницу, где они стоят в печатном мусхафе.

Почему это не косметика. Шрифт V4 у каждой страницы СВОЙ, и глифы в нём
нумеруются заново с U+FC41. Поле code_v4 у слова — это PUA-код внутри
шрифта ЕГО печатной страницы. Если слово лежит у нас на соседней странице,
оно рисуется чужим шрифтом, и на экране вместо аята Корана получается
нечитаемый набор букв (проверено рендером 01.09.2026: первая строка нашей
стр. 121 — мусор вместо 5:77).

Масштаб на 01.09.2026: 25 страниц, 56 аятов, 305 слов.

Признак, по которому это ловится без всякого внешнего источника: коды
глифов страницы обязаны идти неубывающим рядом, начиная ровно с U+FC41.
Проверка стоит в конце скрипта и гоняется по всем 604 страницам.

Чинится переносом ЦЕЛЫХ аятов: печатная раскладка KFGQPC V4 не рвёт ни
одного аята границей страницы (проверено — 0 из 6236), поэтому модель
«аят целиком на одной странице», на которой стоят наши данные, верна.
Меняется только то, на какой странице аят лежит; сами токены, глифы,
переводы и смыслы переносятся как есть.

После переноса строки на затронутых страницах пересобираются по той же
печатной раскладке (scripts/fix_mushaf_lines.py).

Запуск:
    python scripts/fix_page_boundaries.py --check   # только показать
    python scripts/fix_page_boundaries.py           # починить
"""

import argparse
import importlib.util
import io
import json
import os
import sys

sys.path.insert(0, ".")
HERE = os.path.dirname(os.path.abspath(__file__))
BASE_CODE = 0xFC41


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


FIX = load("fixlines", os.path.join(HERE, "fix_mushaf_lines.py"))


def page_path(directory, page):
    return os.path.join(directory, "page%d.json" % page)


def read_page(directory, page):
    path = page_path(directory, page)
    if not os.path.exists(path):
        return None
    return json.loads(io.open(path, encoding="utf-8").read())


def collect(directory):
    """(сура, аят) -> запись аята, и на какой странице она лежит сейчас."""
    entries, where = {}, {}
    for page in range(1, 605):
        data = read_page(directory, page)
        if not data:
            continue
        for a in data["ayahs"]:
            key = (a["surah"], a["ayah"])
            if key in entries:
                raise ValueError(
                    "%d:%d встречается на двух страницах (%d и %d) — "
                    "модель «аят целиком на одной странице» нарушена"
                    % (key[0], key[1], where[key], page)
                )
            entries[key] = a
            where[key] = page
    return entries, where


def print_pages(cache):
    """(сура, аят) -> страница печатного мусхафа."""
    out = {}
    for page in range(1, 605):
        for item in FIX.qul_layout(FIX.fetch_qul(page, cache)):
            for loc in item["locs"]:
                s, a, _ = loc.split(":")
                out.setdefault((int(s), int(a)), page)
    return out


def codes_ok(data):
    """Коды глифов страницы: неубывающий ряд, начинающийся с U+FC41."""
    codes = [
        ord(t["code_v4"][0])
        for a in data["ayahs"]
        for t in a["tokens"]
        if t.get("code_v4")
    ]
    if not codes:
        return True
    if codes[0] != BASE_CODE:
        return False
    return all(codes[i + 1] >= codes[i] for i in range(len(codes) - 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="mushaf_data")
    ap.add_argument("--cache", default="qul_cache")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    entries, where = collect(args.dir)
    print("аятов в наших данных: %d" % len(entries))
    target = print_pages(args.cache)
    print("аятов в печатной раскладке: %d" % len(target))

    missing = [k for k in target if k not in entries]
    if missing:
        raise SystemExit(
            "сначала верни пропавшие аяты (scripts/restore_missing_ayat.py): %s"
            % sorted(missing)[:5]
        )

    moved = {k: (where[k], target[k]) for k in entries if target.get(k, where[k]) != where[k]}
    pages_touched = sorted({p for pair in moved.values() for p in pair})
    print("аятов не на своей странице: %d, затронуто страниц: %d"
          % (len(moved), len(pages_touched)))
    for k in sorted(moved)[:10]:
        print("   %d:%d  наша стр.%d -> печатная стр.%d" % (k[0], k[1], *moved[k]))
    if args.check:
        return 0
    if not moved:
        return 0

    # Пересобираем КАЖДУЮ затронутую страницу целиком из печатной раскладки.
    by_page = {}
    for key, page in target.items():
        by_page.setdefault(page, []).append(key)
    for page in by_page:
        by_page[page].sort()

    # Двухфазно: сначала собираем ВСЕ затронутые страницы в памяти и
    # проверяем каждую, и только если всё сошлось — пишем на диск. Иначе
    # при падении на одной странице аят исчезает: с исходной страницы уже
    # снят, на целевую ещё не положен (так потерялись 84:25 и 89:23 при
    # первом заходе 01.09.2026).
    built = {}
    failed = 0
    import quran_transcript as qt

    for page in pages_touched:
        data = read_page(args.dir, page)
        if data is None:
            continue
        data["ayahs"] = [entries[k] for k in by_page.get(page, [])]
        layout = FIX.qul_layout(FIX.fetch_qul(page, args.cache))
        try:
            data["lines"] = FIX.rebuild(data, layout)
        except Exception as e:
            print("   стр.%d: строки не пересобрались: %s" % (page, e))
            failed += 1
            continue
        if not codes_ok(data):
            print("   стр.%d: ряд глиф-кодов всё ещё рваный" % page)
            failed += 1
            continue
        # Названия сур страницы пересчитываем по её новому составу.
        surahs = []
        for a in data["ayahs"]:
            if a["surah"] not in surahs:
                surahs.append(a["surah"])
        data["surah_names"] = [qt.Aya(s, 1).get().sura_name for s in surahs]
        built[page] = data

    if failed:
        print("НЕ ПИШУ НИЧЕГО: не собралось страниц — %d" % failed)
        return 1

    # Сквозная проверка ДО записи: ни один аят не потерян и не задвоен.
    after = dict(where)
    for page, data in built.items():
        for key in list(after):
            if after[key] == page:
                del after[key]
    for page, data in built.items():
        for a in data["ayahs"]:
            key = (a["surah"], a["ayah"])
            if key in after:
                print("АЯТ %d:%d оказался бы на двух страницах" % key)
                return 1
            after[key] = page
    if len(after) != 6236:
        print("после переноса аятов было бы %d вместо 6236 — НЕ ПИШУ" % len(after))
        return 1

    for page, data in built.items():
        io.open(page_path(args.dir, page), "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        )
    print("записано страниц: %d" % len(built))

    # Финальная проверка по всем 604.
    bad, seen = [], set()
    for page in range(1, 605):
        data = read_page(args.dir, page)
        if not data:
            continue
        if not codes_ok(data):
            bad.append(page)
        for a in data["ayahs"]:
            seen.add((a["surah"], a["ayah"]))
    print()
    print("страниц с рваным рядом глиф-кодов: %d %s" % (len(bad), bad[:10]))
    print("аятов на страницах: %d (в Коране 6236)" % len(seen))
    return 1 if (bad or len(seen) != 6236) else 0


if __name__ == "__main__":
    sys.exit(main())
