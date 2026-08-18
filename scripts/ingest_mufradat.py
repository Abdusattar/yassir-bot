"""Разовая загрузка пословного перевода Корана (суры 2-10, Аль-Бакара по
Юнус - "семь длинных сур", решение пользователя 18.08.2026) для тренажёра
муфрадата. Источник - официальный API Quran Academy (Digital Quran),
проверено на совпадение с ручной выборкой 17.08.2026 (см.
project_mufradat_data_source_licensing в памяти).

save_mufradat_word делает INSERT OR REPLACE с UNIQUE(surah_number,
ayah_number, position) - повторный прогон идемпотентен, поэтому диапазон
сур всегда 2-10 целиком (не только новые), даже если сура 2 уже была
загружена раньше.

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

SURAHS = list(range(2, 11))  # Аль-Бакара по Юнус
BATCH_SIZE = 20
API_URL = "https://digital-quran.quranacademy.org/words"


def fetch_batch(surah_number, start_ayah, end_ayah):
    resp = requests.get(
        API_URL,
        params={
            "surah_number": surah_number,
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


def ingest_surah(surah_number):
    total_ayat = qt.Aya(surah_number, 1).get().num_ayat_in_sura
    saved_words = 0
    skipped_ayat = []

    start = 1
    while start <= total_ayat:
        end = min(start + BATCH_SIZE - 1, total_ayat)
        ayat = fetch_batch(surah_number, start, end)

        for ayah in ayat:
            n = ayah["number"]
            api_words = ayah["words"]
            uthmani_words = qt.Aya(surah_number, n).get().uthmani_words

            if len(api_words) != len(uthmani_words):
                skipped_ayat.append((n, len(api_words), len(uthmani_words)))
                continue

            for w, arabic in zip(api_words, uthmani_words):
                save_mufradat_word(surah_number, n, w["position"], arabic, w["translation"])
                saved_words += 1

        print(f"  сура {surah_number}, аяты {start}-{end}: готово")
        start = end + 1
        time.sleep(1)  # вежливость к их лимиту 60 запросов/мин

    return saved_words, skipped_ayat


def main():
    if not QURAN_ACADEMY_ACCESS_TOKEN:
        print("QURAN_ACADEMY_ACCESS_TOKEN не задан (проверь .env)")
        return

    total_saved = 0
    all_skipped = []
    for surah_number in SURAHS:
        saved, skipped = ingest_surah(surah_number)
        total_saved += saved
        all_skipped.extend((surah_number, n, api_c, qt_c) for n, api_c, qt_c in skipped)

    print()
    print(f"Сохранено слов (все суры {SURAHS[0]}-{SURAHS[-1]}): {total_saved}")
    print(f"Пропущено аятов (расхождение в счёте слов): {len(all_skipped)}")
    for surah_number, n, api_c, qt_c in all_skipped:
        print(f"  сура {surah_number}, аят {n}: api={api_c} qt={qt_c}")


if __name__ == "__main__":
    main()
