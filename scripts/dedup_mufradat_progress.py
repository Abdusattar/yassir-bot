"""Слияние дублей прогресса в mufradat_progress по progress_key (core/sampler.py).

Контекст: до 26.08.2026 прогресс студента хранился по mufradat_words.id
(конкретная строка-позиция) - если одно и то же арабское слово с одним и тем
же переводом встречалось на нескольких страницах, у него было НЕСКОЛЬКО
независимых прогресс-записей, и "выученность" на одной странице не была
видна на другой (найдено пользователем 26.08.2026, измерено на проде:
2990 из 16040 пар с 2+ повторами, 61% активных студентов затронуты).

С 26.08.2026 (core/sampler.py, core/mufradat.py) НОВЫЙ прогресс уже пишется
по progress_key. Этот скрипт - разовая миграция СУЩЕСТВУЮЩЕГО прогресса
(накопленного до перехода): группирует старые записи по (user_id,
progress_key) и сливает их в одну.

Политика слияния (решение пользователя 26.08.2026):
  - correct_count, wrong_count - SUM (оба честно накопительные)
  - last_correct_date - MAX
  - correct_streak - от строки(строк) с МАКСИМАЛЬНОЙ last_correct_date;
    при совпадении дат - MAX streak среди них (решение пользователя:
    "строже по дате"); если у всех NULL - 0 (streak>0 без даты невозможен,
    т.к. record_answer выставляет дату ровно на том же ответе, что двигает
    streak - core/mufradat.py:record_answer)

ИДЕМПОТЕНТНО по конструкции - каждый прогон группирует ТЕКУЩЕЕ состояние
таблицы заново (не накапливает поверх предыдущего слияния), поэтому
повторный запуск на уже слитых данных - no-op (группы размера 1 сливаются
сами в себя). Явной защиты от повторного запуска поэтому не требуется, но
это НЕ повод запускать без надобности - каждый прогон читает и
перезаписывает всю таблицу.

Осиротевшие строки (word_id, которого больше нет в mufradat_words -
исторический баг ДО 26.08.2026, см. project_mufradat_orphan_progress_18aug
в памяти, 1146 строк на 27.08.2026) - пропускаются НЕТРОНУТЫМИ: без записи
в mufradat_words не определить progress_key, мержить или удалять их не
входит в эту миграцию.

mufradat_daily_answered_words - тот же word_id->progress_key ремап,
дедуп естественный через PRIMARY KEY (user_id, date, word_id).

ОБЯЗАТЕЛЕН бэкап hadiths.db перед запуском (см. wiki/feedback_no_manual_db
в памяти - находим причину в коде, не правим прод руками, но эта миграция
- код, не ручная правка, бэкап всё равно обязателен для необратимой операции).

Запускать вручную:
    python scripts/dedup_mufradat_progress.py
"""
import sqlite3
import sys
from collections import defaultdict

sys.path.insert(0, ".")
from core.sampler import HADITHS_DB, ensure_mufradat_schema


def load_word_to_progress_key(conn):
    return dict(conn.execute("SELECT id, progress_key FROM mufradat_words").fetchall())


def merge_progress(conn, word_to_pk):
    rows = conn.execute(
        "SELECT user_id, word_id, correct_streak, wrong_count, days_correct, "
        "last_correct_date, correct_count FROM mufradat_progress"
    ).fetchall()

    groups = defaultdict(list)
    orphans = 0
    for user_id, word_id, streak, wrong, days_correct, last_date, correct in rows:
        pk = word_to_pk.get(word_id)
        if pk is None:
            orphans += 1
            continue
        groups[(user_id, pk)].append({
            "streak": streak, "wrong": wrong, "days_correct": days_correct,
            "last_date": last_date, "correct": correct,
        })

    merged = []
    for (user_id, pk), members in groups.items():
        correct_count = sum(m["correct"] for m in members)
        wrong_count = sum(m["wrong"] for m in members)
        days_correct = max(m["days_correct"] for m in members)
        dated = [m for m in members if m["last_date"]]
        if dated:
            max_date = max(m["last_date"] for m in dated)
            streak = max(m["streak"] for m in dated if m["last_date"] == max_date)
        else:
            max_date = None
            streak = 0
        merged.append((user_id, pk, streak, wrong_count, days_correct, max_date, correct_count))

    return merged, len(rows), orphans, sum(1 for g in groups.values() if len(g) > 1)


def merge_daily_answered(conn, word_to_pk):
    rows = conn.execute("SELECT DISTINCT user_id, date, word_id FROM mufradat_daily_answered_words").fetchall()
    remapped = set()
    orphans = 0
    for user_id, date, word_id in rows:
        pk = word_to_pk.get(word_id)
        if pk is None:
            orphans += 1
            continue
        remapped.add((user_id, date, pk))
    return remapped, len(rows), orphans


def main():
    with sqlite3.connect(HADITHS_DB) as conn:
        ensure_mufradat_schema(conn)
        word_to_pk = load_word_to_progress_key(conn)

        merged, before_count, orphans, collapsed_groups = merge_progress(conn, word_to_pk)
        print(f"mufradat_progress: было строк {before_count}, осиротевших (пропущены) {orphans}, "
              f"групп с 2+ дублями {collapsed_groups}, станет строк {len(merged)}")

        daily_remapped, daily_before, daily_orphans = merge_daily_answered(conn, word_to_pk)
        print(f"mufradat_daily_answered_words: было {daily_before}, осиротевших (пропущены) {daily_orphans}, "
              f"станет {len(daily_remapped)}")

        # Осиротевшие строки НЕ трогаем - удаляем только строки с валидным
        # progress_key (те, что реально участвовали в группировке), заменяем
        # их слитым набором. Осиротевшие остаются как были.
        conn.execute(
            "DELETE FROM mufradat_progress WHERE word_id IN (SELECT id FROM mufradat_words)"
        )
        conn.executemany(
            "INSERT INTO mufradat_progress "
            "(user_id, word_id, correct_streak, wrong_count, days_correct, last_correct_date, correct_count) "
            "VALUES (?,?,?,?,?,?,?)",
            merged
        )

        conn.execute(
            "DELETE FROM mufradat_daily_answered_words WHERE word_id IN (SELECT id FROM mufradat_words)"
        )
        conn.executemany(
            "INSERT OR IGNORE INTO mufradat_daily_answered_words (user_id, date, word_id) VALUES (?,?,?)",
            list(daily_remapped)
        )

    print("Готово.")


if __name__ == "__main__":
    main()
