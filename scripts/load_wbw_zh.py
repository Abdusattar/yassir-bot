"""Пословный китайский перевод сур 1-3 в mufradat_words (20.10.2026).

Готового пословного перевода на китайский нет ни у одного источника
(quran.com под словами даёт английский, QuranEnc - только смысл аята), и
пользователь решил: перевод делает Claude - то же осознанное исключение из
правила «не выдумывать переводы Корана», что у кыргызского
(scripts/generate_kyrgyz_translation.py), только без Gemini. Путунхуа,
упрощённые иероглифы; термины сверены со смысловым переводом Rowwad
(quranenc chinese_suliman, mushaf_data/meaning_zh.json), чтобы подпись под
словом не спорила со смыслом аята: Аллах 安拉, Господь 养主, неверующие
不归信者.

Данные - i18n/wbw_zh.json: {"2:4": ["和那些人", ...]} - по подписи на
каждое слово русской разбивки (те же позиции, тот же «*» у склеенных слов -
core/mufradat.py:_merge_glued_translations). Арабский текст берём из уже
загруженных ru-строк, сегментацию не гадаем заново. Число слов в аяте
сверяется с ru: расхождение - отказ без записи.

Идемпотентно (save_mufradat_word обновляет на месте, progress_key не
трогает). Тренажёр подхватывает правку сам за ~5 минут.

    python scripts/load_wbw_zh.py            # записать
    python scripts/load_wbw_zh.py --check    # только сверить
"""
import json
import os
import sqlite3
import sys

sys.path.insert(0, ".")
from core.sampler import HADITHS_DB, save_mufradat_word

SRC = os.path.join("i18n", "wbw_zh.json")
LANGUAGE = "zh"


def main():
    check_only = "--check" in sys.argv
    with open(SRC, encoding="utf-8") as f:
        data = json.load(f)
    with sqlite3.connect(HADITHS_DB) as conn:
        rows = conn.execute(
            "SELECT surah_number, ayah_number, position, arabic_text, translation "
            "FROM mufradat_words WHERE language='ru' AND surah_number<=3 "
            "ORDER BY surah_number, ayah_number, position").fetchall()
    ru = {}
    for s, a, p, ar, tr in rows:
        ru.setdefault("%d:%d" % (s, a), []).append((p, ar, tr))

    problems = []
    for key, glosses in data.items():
        words = ru.get(key)
        if words is None:
            problems.append("%s: нет ru-строк" % key)
            continue
        if len(words) != len(glosses):
            problems.append("%s: слов %d, в ru %d" % (key, len(glosses), len(words)))
            continue
        for (p, ar, tr), g in zip(words, glosses):
            if (tr.strip() == "*") != (g.strip() == "*"):
                problems.append("%s:%d: «*» не на том месте" % (key, p))
    if problems:
        raise SystemExit("не сходится с ru, ничего не записано:\n" + "\n".join(problems[:30]))
    total = sum(len(v) for v in data.values())
    print("аятов %d, слов %d - сходится с ru" % (len(data), total))
    if check_only:
        return

    for key, glosses in data.items():
        s, a = map(int, key.split(":"))
        for (p, ar, _), g in zip(ru[key], glosses):
            save_mufradat_word(s, a, p, ar, g.strip(), language=LANGUAGE)
    print("записано в %s" % HADITHS_DB)


if __name__ == "__main__":
    main()
