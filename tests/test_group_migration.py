"""Группа стала супергруппой — у неё меняется chat_id.

Реальный повод (06.09.2026): женская подготовительная осталась обычной
группой, а не супергруппой, из-за чего там не работает бан/разбан. При
преобразовании Telegram меняет chat_id и сообщает новый ровно один раз,
служебным сообщением в старый чат. Если его не поймать, бот перестаёт
узнавать группу и она молча отваливается вместе со студентами.
"""

import core.db as db


OLD = "-5587079248"
NEW = "-1005587079248"


def _prep_group(chat_id=OLD):
    db.save_group(chat_id, "Yassir подготовительная", tasks="m,r,t")
    db.update_group_type(chat_id, "prep")
    return db.get_group(chat_id)


def test_migration_keeps_the_same_group_row(test_db):
    """Главное: это ПЕРЕЕЗД, а не новая группа. Студенты, отчёты и роли
    висят на groups.id — он обязан остаться прежним."""
    group = _prep_group()
    gid = group["id"]
    sid = db.add_student("Сатар", gid, phone="777001")
    db.save_report(sid, gid, db.get_date(), {"m": True})

    assert db.update_group_chat_id(OLD, NEW) is True

    moved = db.get_group(NEW)
    assert moved is not None
    assert moved["id"] == gid                    # та же самая группа
    assert moved["group_type"] == "prep"
    assert db.get_group(OLD) is None             # старый id больше не отзывается
    assert [s["name"] for s in db.get_students(gid)] == ["Сатар"]
    assert db.get_student_month_days(sid, gid)   # отчёт на месте


def test_repeated_migration_message_is_harmless(test_db):
    """Telegram может прислать служебное сообщение дважды. Второй раз не
    должен ни дублировать группу, ни затирать уже переехавшую."""
    group = _prep_group()
    gid = group["id"]

    assert db.update_group_chat_id(OLD, NEW) is True
    assert db.update_group_chat_id(OLD, NEW) is False   # уже переехали

    assert db.get_group(NEW)["id"] == gid
    with db.db() as c:
        n = c.execute("SELECT COUNT(*) FROM groups WHERE id=?", (gid,)).fetchone()[0]
    assert n == 1
