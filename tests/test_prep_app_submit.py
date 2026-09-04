"""Сдача заданий из YassirApp студентом ПОДГОТОВИТЕЛЬНОЙ группы.

Жалоба (04.09.2026): в режиме заучивания кнопка «Сдать» отвечала «Ты пока не
в учебной группе» — get_learning_group по определению отдаёт только
pro/relaxed, а prep исключён. При этом задания у prep-группы те же (m,r,t) и
сдаёт их студент туда же, в свою группу.

Флаг include_prep намеренно точечный, а не снятие исключения для всех
вызовов: на этой же функции висит проверка регистрации в handlers.py — если
считать prep учебной группой, выпускник подготовительной при входе в
постоянную группу получал бы «ты уже студент группы ...», то есть ломался бы
сам переход. Тест ниже это и охраняет.
"""

import asyncio

import core.db as db
import core.mufradat_bot as mufradat_bot


PREP_CHAT = "-100777001"
PRO_CHAT = "-100777002"


def _group(chat_id, title, gtype):
    db.save_group(chat_id, title, tasks="m,r,t")
    db.update_group_type(chat_id, gtype)
    return db.get_group(chat_id)


def test_prep_student_invisible_without_flag(test_db):
    """Поведение по умолчанию не изменилось - на нём держится регистрация."""
    prep = _group(PREP_CHAT, "Подготовительная", "prep")
    db.add_student("Сатар", prep["id"], phone="555001")

    assert db.get_learning_group("555001") is None


def test_prep_student_visible_with_flag(test_db):
    """С флагом приложение видит группу, куда студенту сдавать."""
    prep = _group(PREP_CHAT, "Подготовительная", "prep")
    db.add_student("Сатар", prep["id"], phone="555001")

    group = db.get_learning_group("555001", include_prep=True)

    assert group is not None
    assert group["id"] == prep["id"]


def test_permanent_group_wins_over_prep(test_db):
    """Момент перехода: студент недолго активен и в prep, и в постоянной -
    сдача должна уйти в постоянную."""
    prep = _group(PREP_CHAT, "Подготовительная", "prep")
    pro = _group(PRO_CHAT, "N-1", "pro")
    db.add_student("Сатар", prep["id"], phone="555001")
    db.add_student("Сатар", pro["id"], phone="555001")

    group = db.get_learning_group("555001", include_prep=True)

    assert group["id"] == pro["id"]


def test_prep_student_revision_credited(test_db, monkeypatch):
    """Сквозная проверка на реальном пути сдачи: кнопка «повторение»
    засчитывает задание prep-студенту и сообщает в его группу."""
    prep = _group(PREP_CHAT, "Подготовительная", "prep")
    sid = db.add_student("Сатар", prep["id"], phone="555001")
    sent = []

    async def fake_send_message(chat_id, text):
        sent.append((chat_id, text))

    monkeypatch.setattr(mufradat_bot, "send_message", fake_send_message)

    assert asyncio.run(mufradat_bot.credit_revision_task("555001")) is True
    assert (db.get_today_report(sid, prep["id"]) or {}).get("r")
    assert sent and sent[0][0] == PREP_CHAT
