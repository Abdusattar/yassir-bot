"""Разовая загрузка пословного перевода Корана (сура Бакара) для тренажёра
муфрадата. Источник - официальный API Quran Academy (Digital Quran),
проверено на совпадение с ручной выборкой 17.08.2026 (см.
project_mufradat_data_source_licensing в памяти).

Арабский текст берём НЕ из API (include_arabic_text=true падает с 500 на их
стороне), а из quran_transcript - того же источника, что использует
core/quran_ref.py. Сопоставление по позиции слова внутри аята: если
количество слов у API и quran_transcript на каком-то аяте расходится - аят
пропускаем и логируем, не гадаем (см. feedback_never_invent_quran_translations).

Требует quran_transcript и requests (оба в requirements.txt, 17.08.2026,
раньше quran_transcript ставился только локально - см. core/quran_ref.py,
там индекс собран заранее офлайн). Разовый скрипт, не рантайм бота -
запускать вручную из корня репозитория (в т.ч. на сервере после git pull,
там таблиц mufradat_* ещё нет):
    python scripts/ingest_mufradat.py
"""
import sys
import time

import requests
import quran_transcript as qt

sys.path.insert(0, ".")
from config import QURAN_ACADEMY_ACCESS_TOKEN
from core.sampler import save_mufradat_word

SURAH_NUMBER = 2  # Аль-Бакара
BATCH_SIZE = 20
API_URL = "https://digital-quran.quranacademy.org/words"


def fetch_batch(start_ayah, end_ayah):
    resp = requests.get(
        API_URL,
        params={
            "surah_number": SURAH_NUMBER,
            "start_ayah_number": start_ayah,
            "end_ayah_number": end_ayah,
            "language": "ru",
        },
        headers={
            "Access-Token": QURAN_ACADEMY_ACCESS_TOKEN,
            "Language": "ru",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def main():
    if not QURAN_ACADEMY_ACCESS_TOKEN:
        print("QURAN_ACADEMY_ACCESS_TOKEN не задан (проверь .env)")
        return

    total_ayat = qt.Aya(SURAH_NUMBER, 1).get().num_ayat_in_sura
    saved_words = 0
    skipped_ayat = []

    start = 1
    while start <= total_ayat:
        end = min(start + BATCH_SIZE - 1, total_ayat)
        ayat = fetch_batch(start, end)

        for ayah in ayat:
            n = ayah["number"]
            api_words = ayah["words"]
            uthmani_words = qt.Aya(SURAH_NUMBER, n).get().uthmani_words

            if len(api_words) != len(uthmani_words):
                skipped_ayat.append((n, len(api_words), len(uthmani_words)))
                continue

            for w, arabic in zip(api_words, uthmani_words):
                save_mufradat_word(SURAH_NUMBER, n, w["position"], arabic, w["translation"])
                saved_words += 1

        print(f"аяты {start}-{end}: готово")
        start = end + 1
        time.sleep(1)  # вежливость к их лимиту 60 запросов/мин

    print()
    print(f"Сохранено слов: {saved_words}")
    print(f"Пропущено аятов (расхождение в счёте слов): {len(skipped_ayat)}")
    for n, api_c, qt_c in skipped_ayat:
        print(f"  аят {n}: api={api_c} qt={qt_c}")


if __name__ == "__main__":
    main()
