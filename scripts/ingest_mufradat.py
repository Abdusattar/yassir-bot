"""Загрузка пословного перевода Корана (суры 2-10, Аль-Бакара по Юнус -
"семь длинных сур", решение пользователя 18.08.2026) для тренажёра
муфрадата. Источник - официальный API Quran Academy (Digital Quran),
проверено на совпадение с ручной выборкой 17.08.2026 (см.
project_mufradat_data_source_licensing в памяти). LANGUAGES (26.08.2026) -
по одному прогону на каждый язык, коды - реально поддерживаемые API
(проверено эмпирически по /languages: ru/en/uz/tr есть, ky/kk - нет).

save_mufradat_word (core/sampler.py) делает UPDATE на месте для уже
загруженной строки (surah, ayah, position, language) - id и progress_key НЕ
меняются, поэтому повторный прогон идемпотентен и БЕЗОПАСЕН для прогресса
студентов (раньше был INSERT OR REPLACE без id в списке колонок - каждый
повторный прогон раздавал новые id и рвал прогресс всех студентов молча,
починено 26.08.2026 при добавлении языков - см. core/sampler.py).

Арабский текст берём НЕ из API (include_arabic_text=true падает с 500 на их
стороне), а из quran_transcript - того же источника, что использует
core/quran_ref.py. Сопоставление по позиции слова внутри аята: если
количество слов у API и quran_transcript на каком-то аяте расходится - аят
пропускаем и логируем, не гадаем (см. feedback_never_invent_quran_translations).

На узбекском (uz) у API есть аяты, падающие с HTTP 500 целиком (поймано
26.08.2026 на 2:4, проверено точечными запросами - не проблема размера
батча, конкретный аят реально не отдаётся на этом языке). На русском такого
не было. fetch_batch поэтому при 500/ошибке сети на батче не валит весь
прогон, а разбивает батч на отдельные аяты и пропускает+логирует только те,
что падают персонально - остальные аяты батча всё равно грузятся.

Требует quran_transcript и requests (оба в requirements.txt, 17.08.2026,
раньше quran_transcript ставился только локально - см. core/quran_ref.py,
там индекс собран заранее офлайн). Запускать вручную из корня репозитория
(в т.ч. на сервере после git pull):
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
LANGUAGES = ["ru", "uz"]
BATCH_SIZE = 20
API_URL = "https://digital-quran.quranacademy.org/words"


def _fetch(language, start_ayah, end_ayah, surah_number):
    resp = requests.get(
        API_URL,
        params={
            "surah_number": surah_number,
            "start_ayah_number": start_ayah,
            "end_ayah_number": end_ayah,
            "language": language,
        },
        headers={
            "Access-Token": QURAN_ACADEMY_ACCESS_TOKEN,
            "Language": language,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["data"]


def fetch_batch(language, surah_number, start_ayah, end_ayah):
    """Батч целиком, с откатом на поаятный запрос при сбое (см. модульный
    docstring про 500 на отдельных аятах узбекского). Возвращает (ayat,
    failed_ayah_numbers) - failed НЕ прерывает прогон, просто список номеров
    для отчёта/пропуска."""
    try:
        return _fetch(language, start_ayah, end_ayah, surah_number), []
    except requests.RequestException:
        pass

    ayat, failed = [], []
    for n in range(start_ayah, end_ayah + 1):
        try:
            ayat.extend(_fetch(language, n, n, surah_number))
        except requests.RequestException:
            failed.append(n)
        time.sleep(0.3)
    return ayat, failed


def ingest_surah(language, surah_number):
    total_ayat = qt.Aya(surah_number, 1).get().num_ayat_in_sura
    saved_words = 0
    skipped_ayat = []
    failed_ayat = []

    start = 1
    while start <= total_ayat:
        end = min(start + BATCH_SIZE - 1, total_ayat)
        ayat, failed = fetch_batch(language, surah_number, start, end)
        failed_ayat.extend(failed)

        for ayah in ayat:
            n = ayah["number"]
            api_words = ayah["words"]
            uthmani_words = qt.Aya(surah_number, n).get().uthmani_words

            if len(api_words) != len(uthmani_words):
                skipped_ayat.append((n, len(api_words), len(uthmani_words)))
                continue

            for w, arabic in zip(api_words, uthmani_words):
                save_mufradat_word(surah_number, n, w["position"], arabic, w["translation"], language)
                saved_words += 1

        print(f"  [{language}] сура {surah_number}, аяты {start}-{end}: готово"
              + (f" (не отдались с API: {failed})" if failed else ""))
        start = end + 1
        time.sleep(1)  # вежливость к их лимиту 60 запросов/мин

    return saved_words, skipped_ayat, failed_ayat


def main():
    if not QURAN_ACADEMY_ACCESS_TOKEN:
        print("QURAN_ACADEMY_ACCESS_TOKEN не задан (проверь .env)")
        return

    for language in LANGUAGES:
        print(f"=== Язык: {language} ===")
        total_saved = 0
        all_skipped = []
        all_failed = []
        for surah_number in SURAHS:
            saved, skipped, failed = ingest_surah(language, surah_number)
            total_saved += saved
            all_skipped.extend((surah_number, n, api_c, qt_c) for n, api_c, qt_c in skipped)
            all_failed.extend((surah_number, n) for n in failed)

        print()
        print(f"[{language}] Сохранено слов (все суры {SURAHS[0]}-{SURAHS[-1]}): {total_saved}")
        print(f"[{language}] Пропущено аятов (расхождение в счёте слов): {len(all_skipped)}")
        for surah_number, n, api_c, qt_c in all_skipped:
            print(f"  сура {surah_number}, аят {n}: api={api_c} qt={qt_c}")
        print(f"[{language}] Не отдались с API вообще (HTTP-ошибка): {len(all_failed)}")
        for surah_number, n in all_failed:
            print(f"  сура {surah_number}, аят {n}")
        print()


if __name__ == "__main__":
    main()
