"""Апелляция: снять долг пересдачи, который студент закрыл, а бот не засчитал
(28.10.2026).

Первый случай - Айкол (женская, группа 1): долг по мадинской стр. 32, строка 8
пришёл 17.10, а 19.10 она перешла на Дар аль-Маариф. Приложение открывало
пересдачу по мадинским номерам, а отправляло с раскладкой из настроек - семь
пересдач легли как «египетская стр. 32, строка 8», там другой текст, и стена
пересдачи держала её на месте неделю.

Долг снимается тем же путём, что и «Принято» устаза (set_submission_verdict),
вердикт_by - метка «appeal», а не телефон устаза: в кабинете видно, что это
не его решение. Пометки устаза остаются.

    python scripts/retake_close.py --profile female --user-id 14                    # открытые долги
    python scripts/retake_close.py --profile female --submission 5459 --why "..."  # снять

Запускать на сервере из корня репозитория от владельца базы (stursunkul).
"""
import argparse
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
APPEAL = "appeal"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="male", choices=["male", "female"])
    ap.add_argument("--user-id", type=int, help="users.id - показать открытые долги")
    ap.add_argument("--submission", type=int, help="id сдачи с вердиктом retake")
    ap.add_argument("--why", help="причина; без неё только показать")
    a = ap.parse_args()

    os.environ["BOT_PROFILE"] = a.profile
    os.environ.setdefault("DB_PATH", str(ROOT / ("quran_%s.db" % a.profile)))
    sys.path.insert(0, str(ROOT))
    from core.db import (db, get_open_retakes, set_submission_verdict,   # noqa: E402
                         VERDICT_ACCEPTED, VERDICT_RETAKE)

    if a.user_id and not a.submission:
        with db() as c:
            groups = [r["group_id"] for r in c.execute(
                "SELECT group_id FROM user_groups WHERE user_id=? AND active=1", (a.user_id,))]
        for g in groups:
            for r in get_open_retakes(a.user_id, g):
                print("сдача %s · группа %s · стр. %s, строка %s (индекс %s), этап %s, %s, %s" % (
                    r["id"], g, r["hifz_page"], (r["hifz_line"] or 0) + 1, r["hifz_line"],
                    r["hifz_stage"], r["hifz_layout"] or "madani", r["date"]))
        return 0

    if not a.submission:
        ap.error("нужен --user-id или --submission")
    with db() as c:
        row = c.execute("SELECT * FROM voice_submissions WHERE id=?", (a.submission,)).fetchone()
    if not row or row["verdict"] != VERDICT_RETAKE:
        print("сдача %s не на пересдаче" % a.submission)
        return 1
    print("сдача %s · студент %s · стр. %s, строка %s, этап %s, %s" % (
        row["id"], row["student_id"], row["hifz_page"], (row["hifz_line"] or 0) + 1,
        row["hifz_stage"], row["hifz_layout"] or "madani"))
    if not a.why:
        print("без --why ничего не меняю")
        return 0
    set_submission_verdict(row["id"], VERDICT_ACCEPTED, APPEAL,
                           error_words=json.loads(row["error_words"] or "[]"))
    print("долг снят: %s" % a.why)
    return 0


if __name__ == "__main__":
    sys.exit(main())
