"""Языковые версии страниц мусхафа: page{N}_{lang}.json (30.08.2026).

Страница чтения берёт пословные переводы и смысловой перевод аята прямо
из page*.json - они вшиваются туда на этапе экспорта
(scripts/export_mushaf_page.py, scripts/add_ayah_meaning.py), поэтому в
основных 604 файлах лежит только русский. Для кыргызского и узбекского
кладём рядом отдельный файл на страницу, а фронтенд (mushaf_data/index.html,
loadPage) запрашивает page{N}_{lang}.json и молча откатывается на русский,
если файла нет.

Полный export_mushaf_page.py тут не годится: он ходит в api.quran.com за
таджвид-разметкой на каждую страницу (часы работы и лишний риск для уже
выверенных данных). Раскладка, арабский текст, таджвид и границы страниц от
языка не зависят - меняются ТОЛЬКО поля translation (пословный перевод) и
meaning (смысл аята). Поэтому берём готовый page{N}.json и подменяем их.

ПОСЛОВНЫЙ перевод есть пока только на джуз 1, СМЫСЛОВОЙ - на весь Коран
(scripts/fetch_meaning_quranenc.py). Поэтому файл создаётся на КАЖДУЮ из
604 страниц, а слова без перевода на целевом языке остаются с русским
текстом (решение пользователя 30.08.2026). Раньше правило было обратным -
пустая строка, то есть слово просто не тапалось; при полном охвате
смыслового перевода это означало бы, что кыргызский студент на странице 30
теряет подсказки по словам, которые у него сейчас есть. Тот же выбор, что
уже сделан в "Мои слова" (core/mushaf_words.py:list_starred_words): перевод
на другом языке полезнее пустоты.

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


def load_meanings(language):
    """{"2:2": текст} - смысловой перевод, весь Коран (см.
    scripts/fetch_meaning_quranenc.py). Нет файла - работаем без смыслов,
    страницы всё равно нужны ради пословных переводов."""
    src = os.path.join(OUT_DIR, "meaning_%s.json" % language)
    if not os.path.exists(src):
        print("нет %s - смысловой перевод останется русским" % src)
        return {}
    with open(src, encoding="utf-8") as f:
        return json.load(f)


def localize_page(data, translations, meanings):
    """Подменяет пословные переводы и смыслы аятов. Возвращает
    (слов на целевом языке, аятов со смыслом на целевом языке)."""
    word_hits = 0
    meaning_hits = 0

    def patch(token):
        nonlocal word_hits
        if token.get("type") != "word":
            return
        key = (token.get("surah"), token.get("ayah"), token.get("position"))
        if None in key:
            return
        t = translations.get(key)
        # Нет перевода на этот язык - оставляем русский как есть (см.
        # модульный docstring), НЕ затираем пустой строкой.
        if t is not None:
            token["translation"] = t
            word_hits += 1

    for ayah in data.get("ayahs", []):
        for token in ayah.get("tokens", []):
            # в ayahs[] у токенов нет surah/ayah - берём с уровня аята
            if token.get("type") == "word":
                token.setdefault("surah", ayah["surah"])
                token.setdefault("ayah", ayah["ayah"])
            patch(token)
        meaning = meanings.get("%s:%s" % (ayah["surah"], ayah["ayah"]))
        if meaning:
            ayah["meaning"] = meaning
            meaning_hits += 1
    for line in data.get("lines", []):
        for token in line.get("tokens", []):
            patch(token)
    return word_hits, meaning_hits


def main():
    language = sys.argv[1] if len(sys.argv) > 1 else None
    if not language:
        raise SystemExit("укажи язык: python scripts/export_mushaf_lang.py ky")

    translations = load_translations(language)
    meanings = load_meanings(language)
    if not translations and not meanings:
        raise SystemExit("для языка %s нет ни пословных переводов, ни смыслов" % language)
    print("пословных переводов: %d, смыслов аятов: %d" % (len(translations), len(meanings)))

    written = skipped = 0
    total_words = total_meanings = 0
    for page in range(FIRST_PAGE, LAST_PAGE + 1):
        src = os.path.join(OUT_DIR, "page%d.json" % page)
        if not os.path.exists(src):
            continue
        with open(src, encoding="utf-8") as f:
            data = json.load(f)
        word_hits, meaning_hits = localize_page(data, translations, meanings)
        dst = os.path.join(OUT_DIR, "page%d_%s.json" % (page, language))
        if not word_hits and not meaning_hits:
            # Ничего не локализовано - файл не создаём, пусть фронтенд
            # откатывается на русскую страницу целиком.
            if os.path.exists(dst):
                os.remove(dst)
            skipped += 1
            continue
        with open(dst, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        written += 1
        total_words += word_hits
        total_meanings += meaning_hits
        if page % 100 == 0:
            print("  ...страница %d" % page)

    print()
    print("создано файлов: %d, пропущено страниц: %d" % (written, skipped))
    print("локализовано слов: %d, аятов со смыслом: %d" % (total_words, total_meanings))


if __name__ == "__main__":
    main()
