"""Языковые версии страниц мусхафа: page{N}_{lang}.json (30.08.2026).

Страница чтения берёт пословные переводы прямо из page*.json - они
вшиваются туда на этапе экспорта (scripts/export_mushaf_page.py), поэтому
в основных 604 файлах лежит только русский. Для кыргызского и узбекского
кладём рядом отдельный файл на страницу, а фронтенд (mushaf_data/index.html,
loadPage) запрашивает page{N}_{lang}.json и молча откатывается на русский,
если файла нет - переводы готовы пока только на джуз 1.

Полный export_mushaf_page.py тут не годится: он ходит в api.quran.com за
таджвид-разметкой на каждую страницу (часы работы и лишний риск для уже
выверенных данных). Раскладка, арабский текст, таджвид и границы страниц от
языка не зависят - меняется ТОЛЬКО поле translation. Поэтому берём готовый
page{N}.json и подменяем в нём переводы.

Слова без перевода на целевом языке остаются с ПУСТОЙ строкой, а не с
русским текстом: пустой перевод в mushaf_data/index.html означает "слово не
тапается" (та же схема, что у "*"-склеек, см. wiki/mushaf_yassirapp.md) -
это честнее, чем показывать кыргызскому студенту русское слово, выдавая его
за перевод на его язык.

Запускать вручную после пополнения переводов:
    python scripts/export_mushaf_lang.py ky
    python scripts/export_mushaf_lang.py uz
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, ".")
from core.sampler import HADITHS_DB

OUT_DIR = "mushaf_data"
FIRST_PAGE = 1
LAST_PAGE = 604


def load_translations(language):
    """(surah, ayah, position) -> перевод на целевом языке."""
    with sqlite3.connect(HADITHS_DB) as conn:
        rows = conn.execute(
            "SELECT surah_number, ayah_number, position, translation "
            "FROM mufradat_words WHERE language=?",
            (language,)
        ).fetchall()
    return {(s, a, p): t for s, a, p, t in rows}


def localize_page(data, translations):
    """Подменяет переводы в токенах страницы. Возвращает число слов, для
    которых перевод на целевом языке нашёлся."""
    hits = 0

    def patch(token):
        nonlocal hits
        if token.get("type") != "word":
            return
        key = (token.get("surah"), token.get("ayah"), token.get("position"))
        if None in key:
            return
        t = translations.get(key)
        if t is not None:
            token["translation"] = t
            hits += 1
        else:
            # нет перевода на этот язык - слово просто не тапается
            token["translation"] = ""

    for ayah in data.get("ayahs", []):
        for token in ayah.get("tokens", []):
            # в ayahs[] у токенов нет surah/ayah - берём с уровня аята
            if token.get("type") == "word":
                token.setdefault("surah", ayah["surah"])
                token.setdefault("ayah", ayah["ayah"])
            patch(token)
    for line in data.get("lines", []):
        for token in line.get("tokens", []):
            patch(token)
    return hits


def main():
    language = sys.argv[1] if len(sys.argv) > 1 else None
    if not language:
        raise SystemExit("укажи язык: python scripts/export_mushaf_lang.py ky")

    translations = load_translations(language)
    if not translations:
        raise SystemExit(f"нет ни одного слова с language={language}")
    print(f"переводов на {language}: {len(translations)}")

    written = skipped = 0
    for page in range(FIRST_PAGE, LAST_PAGE + 1):
        src = os.path.join(OUT_DIR, f"page{page}.json")
        if not os.path.exists(src):
            continue
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        hits = localize_page(data, translations)
        dst = os.path.join(OUT_DIR, f"page{page}_{language}.json")
        if not hits:
            # Ни одного слова на этом языке - файл не создаём вообще, пусть
            # фронтенд откатывается на русский (иначе студент получил бы
            # страницу, где не тапается ни одно слово).
            if os.path.exists(dst):
                os.remove(dst)
            skipped += 1
            continue
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        written += 1
        print(f"  стр. {page}: {hits} слов -> {dst}")

    print()
    print(f"создано файлов: {written}, пропущено страниц (нет переводов): {skipped}")


if __name__ == "__main__":
    main()
