"""Смысловой перевод аятов на кыргызском и узбекском (quranenc.com, 30.08.2026).

Русский смысл берётся с api.quran.com (Кулиев, resource_id=45, см.
scripts/add_ayah_meaning.py) - но кыргызского там нет вообще. Проверено
30.08.2026 у самих источников: в каталоге api.quran.com 126 переводов, в
alquran.cloud 330 изданий - кыргызского нет ни там, ни там.

Есть на quranenc.com - это "Noble Quran Encyclopedia" Комплекса имени
короля Фахда (той же организации принадлежит шрифт QPC V4, на котором
построена наша построчная вёрстка, см. wiki/mushaf_yassirapp.md):
    ky  kyrgyz_hakimov  Шамсуддин Хакимов, редакция Rowwad Translation Center
    uz  uzbek_rwwad     Rowwad Translation Center
Узбекский взят у Rowwad, а не более известный Мухаммад Содик Мухаммад
Юсуф с api.quran.com - решение пользователя 30.08.2026: один источник и
одна редакция на оба языка (один конвейер, один разговор о правах, один
стиль, сноски отдельным полем, а не тегами внутри текста).

Нумерация аятов сверена с эталонной на сурах 2 (286), 18 (110) и 114 (6) -
совпадает, аяты идут подряд без пропусков.

Запрос идёт по СУРАМ - 114 вызовов на язык, не 6236 по аятам.

Права: разрешение на постоянное размещение русского перевода
подтверждено пользователем лично (см. scripts/add_ayah_meaning.py). Для
этих двух переводов такой же вопрос стоит отдельно - скрипт только
складывает файл, публикация решается человеком.

Запускать вручную:
    python scripts/fetch_meaning_quranenc.py ky
    python scripts/fetch_meaning_quranenc.py uz
"""
import json
import os
import re
import sys
import time

import requests

OUT_DIR = "mushaf_data"
LAST_SURAH = 114

# Ключ перевода на quranenc.com для каждого нашего языка.
TRANSLATION_KEYS = {
    "ky": "kyrgyz_hakimov",
    "uz": "uzbek_rwwad",
}

# Ссылки на сноски вида "[1]" идут ВНУТРИ текста перевода, а сами сноски -
# отдельным полем "footnotes". Сносок мы не показываем (вкладка "Смысл" -
# сплошной текст аята, не тафсир), поэтому маркеры убираем: иначе студент
# видит "Бул китепте[1] эч күмөн жок" и ищет, к чему относится цифра.
_FOOTNOTE_REF_RE = re.compile(r"\[\d+\]")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def clean(text):
    text = _FOOTNOTE_REF_RE.sub("", text)
    # После удаления маркера остаётся двойной пробел или пробел перед точкой.
    text = re.sub(r"\s+", " ", text)
    return text.replace(" .", ".").replace(" ,", ",").strip()


def fetch_surah(key, surah, retries=3):
    """{verse_key: текст} для одной суры, один запрос."""
    url = "https://quranenc.com/api/v1/translation/sura/%s/%d" % (key, surah)
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            rows = r.json()["result"]
            return {
                "%s:%s" % (row["sura"], row["aya"]): clean(row["translation"])
                for row in rows
                if (row.get("translation") or "").strip()
            }
        except Exception:
            if attempt < retries - 1:
                time.sleep(2)
                continue
            raise


def main():
    language = sys.argv[1] if len(sys.argv) > 1 else None
    if language not in TRANSLATION_KEYS:
        raise SystemExit("укажи язык: %s" % "/".join(TRANSLATION_KEYS))
    key = TRANSLATION_KEYS[language]

    meanings = {}
    for surah in range(1, LAST_SURAH + 1):
        got = fetch_surah(key, surah)
        if not got:
            raise SystemExit("сура %d вернулась пустой - прерываю, файл не пишу" % surah)
        meanings.update(got)
        if surah % 20 == 0 or surah == LAST_SURAH:
            print("  сура %d/%d, аятов всего: %d" % (surah, LAST_SURAH, len(meanings)))

    # 6236 - канонические аяты Корана; 6234 у нас в страницах (page*.json
    # не содержит "Бисмиллях" отдельными аятами там, где она вне нумерации).
    # Расхождение в пару аятов ожидаемо, а вот недобор в сотни означал бы
    # оборванную загрузку - такой файл писать нельзя.
    if len(meanings) < 6000:
        raise SystemExit("получено только %d аятов - похоже на обрыв" % len(meanings))

    dst = os.path.join(OUT_DIR, "meaning_%s.json" % language)
    with open(dst, "w", encoding="utf-8") as f:
        json.dump(meanings, f, ensure_ascii=False)
    print()
    print("записано: %s (%d аятов, источник %s)" % (dst, len(meanings), key))


if __name__ == "__main__":
    main()
