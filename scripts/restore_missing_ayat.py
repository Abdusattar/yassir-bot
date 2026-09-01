#!/usr/bin/env python3
"""Возвращает в страницы мусхафа аяты, потерянные экспортёром.

Как они пропали: в export_page() при расхождении в счёте слов между
quran_transcript и таджвид-разметкой api.quran.com аят пропускался ЦЕЛИКОМ
(осознанное решение — лучше дыра, чем выдуманный текст) и лишь логировался.
Лог никто не разобрал, и на прод уехали страницы БЕЗ аятов 2:181 и 13:37:
после 2:180 сразу шёл 2:182. Обнаружено 01.09.2026 при сверке построчной
разметки с печатной раскладкой KFGQPC V4.

Причина расхождения одна на оба случая: api.quran.com пишет 'بَعْدَمَا'
слитно, а quran_transcript (и шрифт V4, и печатная раскладка) считает это
двумя словами — 'بَعْدَ' + 'مَا'. Починено в самом экспортёре
(_split_glued_chunk): точка реза берётся из длины первого слова и
проверяется посимвольно, не угадывается.

Этот скрипт — разовая доводка УЖЕ выгруженных страниц, чтобы не гонять
заново весь дорогой экспорт 604 страниц. Ничего не выдумывает: арабский и
таджвид из api.quran.com, позиции слов из quran_transcript, переводы из
mufradat_words, глифы из того же qpc-v4, построчная раскладка из QUL.

Идемпотентен: если дыр нет, ничего не делает.

После него нужно один раз прогнать смысловой перевод на затронутых
страницах:
    python scripts/add_ayah_meaning.py

Запуск:
    python scripts/restore_missing_ayat.py            # починить
    python scripts/restore_missing_ayat.py --check    # только показать дыры
"""

import argparse
import importlib.util
import io
import json
import os
import sqlite3
import sys

sys.path.insert(0, ".")
HERE = os.path.dirname(os.path.abspath(__file__))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


EXP = load("exp", os.path.join(HERE, "export_mushaf_page.py"))
FIX = load("fixlines", os.path.join(HERE, "fix_mushaf_lines.py"))


def page_path(directory, page):
    return os.path.join(directory, "page%d.json" % page)


def ayat_of(data):
    return [(a["surah"], a["ayah"]) for a in data["ayahs"]]


def qul_ayat(layout):
    """Аяты, которые печатная раскладка кладёт на эту страницу, по порядку."""
    out = []
    for _, locs in layout:
        for loc in locs:
            s, a, _ = loc.split(":")
            key = (int(s), int(a))
            if key not in out:
                out.append(key)
    return out


def find_holes(directory, cache):
    """Аяты, которых нет НИ НА ОДНОЙ нашей странице.

    Сравнивать надо сквозным списком, а не постранично: постранично в глаза
    лезут расхождения ГРАНИЦ страниц (у нас аят на 121-й, в печати на 120-й —
    таких 56 аятов на 25 страницах). Это отдельная история, аят при этом
    никуда не пропал. Настоящая дыра — когда аята нет во всём мусхафе."""
    ours = {}
    for page in range(1, 605):
        path = page_path(directory, page)
        if not os.path.exists(path):
            continue
        data = json.loads(io.open(path, encoding="utf-8").read())
        for key in ayat_of(data):
            ours.setdefault(key, page)

    holes = []
    for page in range(1, 605):
        if not os.path.exists(page_path(directory, page)):
            continue
        layout = FIX.qul_layout(FIX.fetch_qul(page, cache))
        for key in qul_ayat(layout):
            if key not in ours:
                holes.append((page, key[0], key[1]))
    return holes


def build_ayah(conn, surah, ayah):
    """Собирает запись аята ровно в той же форме, что и export_page()."""
    words = EXP.get_ayah_words(conn, surah, ayah)
    raw = EXP.fetch_tajweed_ayah(surah, ayah)
    missing = []
    tokens = EXP.parse_ayah_tokens(raw, words, surah, ayah, missing)
    n_words = len([t for t in tokens if t["type"] == "word"])
    if n_words != len(words):
        raise ValueError(
            "%d:%d — собрано %d слов, а в quran_transcript %d"
            % (surah, ayah, n_words, len(words))
        )
    if missing:
        raise ValueError("%d:%d — нет глиф-кодов v4: %s" % (surah, ayah, missing))
    return {"surah": surah, "ayah": ayah, "tokens": tokens}, n_words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="mushaf_data")
    ap.add_argument("--cache", default="qul_cache")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    holes = find_holes(args.dir, args.cache)
    print("дыр в мусхафе: %d" % len(holes))
    for page, s, a in holes:
        print("   стр.%d — нет аята %d:%d" % (page, s, a))
    if args.check or not holes:
        return 0

    conn = sqlite3.connect(str(EXP.HADITHS_DB))
    conn.row_factory = sqlite3.Row
    touched = set()
    failed = 0

    for page, surah, ayah in holes:
        path = page_path(args.dir, page)
        data = json.loads(io.open(path, encoding="utf-8").read())
        try:
            entry, n_words = build_ayah(conn, surah, ayah)
        except Exception as e:
            print("   стр.%d %d:%d ОШИБКА: %s" % (page, surah, ayah, e))
            failed += 1
            continue

        # Вставляем аят на его место в порядке чтения.
        idx = len(data["ayahs"])
        for i, a in enumerate(data["ayahs"]):
            if (a["surah"], a["ayah"]) > (surah, ayah):
                idx = i
                break
        data["ayahs"].insert(idx, entry)

        # Пересобираем строки по печатной раскладке — теперь все слова на месте.
        layout = FIX.qul_layout(FIX.fetch_qul(page, args.cache))
        try:
            data["lines"] = FIX.rebuild(data, layout)
        except Exception as e:
            print("   стр.%d: строки не пересобрались: %s" % (page, e))
            failed += 1
            continue

        io.open(path, "w", encoding="utf-8").write(
            json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        )
        n_lines = len([l for l in data["lines"] if l["type"] == "text"])
        print(
            "   стр.%d: аят %d:%d возвращён (%d слов), строк текста %d"
            % (page, surah, ayah, n_words, n_lines)
        )
        touched.add(page)

    if touched:
        print(
            "\nтеперь прогони смысловой перевод на этих страницах:\n"
            "    python scripts/add_ayah_meaning.py"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
