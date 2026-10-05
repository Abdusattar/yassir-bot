"""Вернуть «выучено» словам, сброшенным багом 28.08–05.10.2026.

Баг: remove_starred_by_progress_key (core/mushaf_words.py) обнуляла correct_streak у
ЛЮБОГО слова на пороге MASTERY_STREAK, а не только у слов из «Моих слов». Исправлено
05.10.2026 (жалоба Толкун). Решение пользователя: вернуть по строгому правилу.

Правило (только то, что точно было выучено и сброшено багом):
  - correct_count >= MASTERY_STREAK и wrong_count == 0 (ни одной ошибки за всё время);
  - сейчас correct_streak < MASTERY_STREAK;
  - слова нет в «Моих словах» этого человека (у них сброс по задумке);
  - last_correct_date >= 2026-08-28 (окно бага).
Таким словам ставится correct_streak = MASTERY_STREAK; last_correct_date не трогаем
(отдых 60 дней считается от последнего верного ответа, как и было бы без бага).

    sudo -u stursunkul python3 scripts/restore_mastery_after_reset_bug.py           # показать
    sudo -u stursunkul python3 scripts/restore_mastery_after_reset_bug.py --apply   # применить

Запускать на сервере из корня репозитория, ПОСЛЕ выкладки исправления.
"""
import argparse
import pathlib
import sqlite3
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import mufradat  # noqa: E402
from core.sampler import HADITHS_DB  # noqa: E402

BUG_FROM = "2026-08-28"


def candidates(conn):
    return conn.execute("""
        SELECT p.user_id, p.word_id
        FROM mufradat_progress p
        WHERE p.correct_count >= ? AND p.wrong_count = 0 AND p.correct_streak < ?
          AND p.last_correct_date >= ?
          AND NOT EXISTS (SELECT 1 FROM mushaf_starred_words s
                          WHERE s.user_id = p.user_id AND s.progress_key = p.word_id)
    """, (mufradat.MASTERY_STREAK, mufradat.MASTERY_STREAK, BUG_FROM)).fetchall()


def scores(users):
    out = {}
    for u in users:
        s = mufradat.compute_overall_score(u)
        out[u] = (s["score10"], s["mastered"]) if s else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    with sqlite3.connect(str(HADITHS_DB)) as conn:
        rows = candidates(conn)
    per_user = {}
    for uid, _ in rows:
        per_user[uid] = per_user.get(uid, 0) + 1
    print("слов к возврату: %d, людей: %d" % (len(rows), len(per_user)))
    top = sorted(per_user.items(), key=lambda x: -x[1])[:10]
    before = scores([u for u, _ in top])
    if not a.apply:
        for u, n in top:
            print("  %s  слов %d  сейчас вес/выучено %s" % (u, n, before[u]))
        print("НЕ применено: это просмотр. Для применения --apply")
        return
    with sqlite3.connect(str(HADITHS_DB)) as conn:
        conn.executemany(
            "UPDATE mufradat_progress SET correct_streak=? WHERE user_id=? AND word_id=? AND correct_streak<?",
            [(mufradat.MASTERY_STREAK, u, w, mufradat.MASTERY_STREAK) for u, w in rows])
    after = scores([u for u, _ in top])
    for u, n in top:
        print("  %s  слов %d  вес/выучено %s -> %s" % (u, n, before[u], after[u]))
    print("применено")


if __name__ == "__main__":
    main()
