"""Устаз одной группы — студент другой.

Правило пользователя (08.09.2026): устазами у нас работают сами студенты —
кроме Умар устаза все ведут одну группу и учатся в другой, и обычные правила
на них действуют: пропустил — ушёл в подготовительную, отучился — вернулся.

Живой случай: Имран ведёт группу «Отбор.» и учится в N-1. Его кикнули из N-1
за пропуски, он прошёл подготовительную, Умар устаз подтвердил джуз, бот
выдал ссылку — а вход в N-1 бот пропустил молча, потому что «человек где-то
устаз». Наутро первое же его сообщение выкинуло его из группы как
«вернувшегося без подготовительной», и так по кругу четыре раза.
"""
import core.db as db


def _group(chat_id, title, gtype="pro"):
    db.save_group(chat_id, title, tasks="m,r,t")
    with db.db() as c:
        c.execute("UPDATE groups SET group_type=? WHERE chat_id=?", (gtype, chat_id))
    return db.get_group(chat_id)


def test_ustaz_entering_a_new_group_is_left_alone(test_db):
    """Устаза, которого ставят вести новую группу, бот не трогает."""
    own = _group("-100777001", "Отбор.", "relaxed")
    other = _group("-100777002", "G-5", "relaxed")
    db.add_group_admin(own["id"], "500001")

    assert not db.joins_as_student("500001", other["id"])


def test_returning_from_prep_is_a_student(test_db):
    """Случай Имрана: метка «вернуться только через prep» — это про учёбу."""
    own = _group("-100777001", "Отбор.", "relaxed")
    home = _group("-100777002", "N-1", "pro")
    db.add_group_admin(own["id"], "500001")
    db.add_student("Имран", home["id"], phone="500001")
    db.mark_pending_prep_return("500001", home["id"], "inactive")

    assert db.joins_as_student("500001", home["id"])


def test_active_in_prep_is_a_student(test_db):
    """Он проходит подготовительную, а не ведёт её."""
    own = _group("-100777001", "Отбор.", "relaxed")
    prep = _group("-100777003", "Yassir подготовительная", "prep")
    target = _group("-100777002", "N-1", "pro")
    db.add_group_admin(own["id"], "500001")
    db.add_student("Имран", prep["id"], phone="500001")

    assert db.joins_as_student("500001", target["id"])


def test_coming_back_to_his_own_group(test_db):
    """Был студентом именно здесь — возвращается к себе, даже без метки."""
    own = _group("-100777001", "Отбор.", "relaxed")
    home = _group("-100777002", "N-1", "pro")
    db.add_group_admin(own["id"], "500001")
    student = db.add_student("Имран", home["id"], phone="500001")
    db.deactivate_student(student if isinstance(student, int) else
                          db.find_user_by_phone("500001")["id"], home["id"])

    assert db.joins_as_student("500001", home["id"])
