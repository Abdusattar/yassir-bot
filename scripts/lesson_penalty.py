"""Ложная отметка онлайн-урока: снять +5 и записать штраф (07.10.2026).

Зачем: объявление 26.09.2026 во все учебные группы обещало за отметку урока,
которого не было, снятие баллов и штраф 20 баллов. Бот сам этого не делает —
без расписания уроков он не знает, был ли урок. Решает человек, скрипт
оформляет решение так, чтобы всё было видно потом: снятая отметка уходит в
score_removals (через remove_scores), штраф ложится отдельной строкой
score_events с category='penalty' и отрицательными баллами (в /rating,
/mystats и недельном отчёте он просто вычитается), студенту уходит личное
сообщение.

Первый случай — Ибрахим (G-9): урок на неделе был один, 29.09, а «Я был»
нажато дважды (29.09 и в ночь на 01.10, промежуток 26 ч — лимит «две в
неделю» пропустил; с 07.10 лимит снова одна).

По умолчанию НИЧЕГО не меняет — показывает, что снимет, что запишет и что
отправит. Применение — с ключом --send. Запускать НА СЕРВЕРЕ под окружением
нужного бота (у мужского и женского свои токены и базы):

    sudo -u stursunkul bash -c "set -a; . .env; set +a; venv/bin/python3 scripts/lesson_penalty.py \
        --user-id 687 --group 'G - 9' --date 2026-09-30 --penalty 20 \
        --why 'второй «Я был» за один урок' --text-file /tmp/dm.txt"
    ... --send                 применить и отправить
    ... --penalty 0            только снять отметку, без штрафа
"""
import argparse
import asyncio
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.db import db, remove_scores, add_bonus, get_date   # noqa: E402

PENALTY_CATEGORY = "penalty"
PENALTY_SUB = "false_lesson"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", type=int, required=True, help="users.id в базе этого бота")
    ap.add_argument("--group", required=True, help="название группы, как в базе (точно)")
    ap.add_argument("--date", required=True, help="учебный день ложной отметки YYYY-MM-DD")
    ap.add_argument("--penalty", type=int, default=20, help="штраф в баллах, 0 - без штрафа")
    ap.add_argument("--why", required=True, help="причина - в score_removals.why и в note штрафа")
    ap.add_argument("--text-file", help="текст личного сообщения студенту (utf-8)")
    ap.add_argument("--send", action="store_true")
    a = ap.parse_args()

    with db() as c:
        u = c.execute("SELECT id, name, phone, dm_ok FROM users WHERE id=?", (a.user_id,)).fetchone()
        g = c.execute("SELECT id, title FROM groups WHERE title=?", (a.group,)).fetchone()
        if not u or not g:
            print("нет пользователя или группы:", a.user_id, a.group)
            return 1
        mark = c.execute(
            "SELECT id, date, created_at, points FROM score_events WHERE student_id=? AND group_id=?"
            " AND category='attendance' AND subcategory='online' AND date=?",
            (u["id"], g["id"], a.date)
        ).fetchone()
        already = c.execute(
            "SELECT points, note FROM score_events WHERE student_id=? AND group_id=?"
            " AND category=? AND subcategory=? AND date=?",
            (u["id"], g["id"], PENALTY_CATEGORY, PENALTY_SUB, get_date())
        ).fetchone()

    print("студент: %s (id %s, tg %s), личка открыта: %s" % (
        u["name"], u["id"], u["phone"], "да" if u["dm_ok"] else "НЕТ"))
    print("группа:  %s (id %s)" % (g["title"], g["id"]))
    if mark:
        print("снять:   отметка урока за %s (+%s, поставлена %s UTC)" % (mark["date"], mark["points"], mark["created_at"]))
    else:
        print("снять:   отметки за %s нет - снимать нечего" % a.date)
    if a.penalty:
        print("штраф:   −%s баллов, строка category=%s/%s за %s" % (a.penalty, PENALTY_CATEGORY, PENALTY_SUB, get_date()))
        if already:
            print("         ВНИМАНИЕ: штраф за сегодня уже записан (%s, %s) - второй не ляжет" % (already["points"], already["note"]))
    text = pathlib.Path(a.text_file).read_text(encoding="utf-8").strip() if a.text_file else ""
    if text:
        print("-" * 40)
        print(text)
        print("-" * 40)

    if not a.send:
        print("\n(проверка: ничего не изменено; применить - добавь --send)")
        return 0

    with db() as c:
        if mark:
            n = remove_scores(
                c, "student_id=? AND group_id=? AND category='attendance' AND subcategory='online' AND date=?",
                (u["id"], g["id"], a.date), by="lesson_penalty.py", why="ложная отметка урока: " + a.why)
            print("снято строк:", n)
    if a.penalty:
        add_bonus(u["id"], g["id"], get_date(), -abs(a.penalty), PENALTY_CATEGORY, PENALTY_SUB,
                  note="ложная отметка урока за " + a.date + ": " + a.why)
        print("штраф записан")
    if text and u["phone"] and u["dm_ok"]:
        from core.tg import send_message
        asyncio.run(send_message(u["phone"], text))
        print("сообщение отправлено")
    elif text:
        print("сообщение НЕ отправлено: личка закрыта")
    return 0


if __name__ == "__main__":
    sys.exit(main())
