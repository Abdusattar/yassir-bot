"""«Мой день» на дашборде: отметка по каждому заданию своей группы.

Решение пользователя 07.09.2026. Дыхание сверху говорит, что сделал джамаат,
эта полоса — что осталось самому. Заданий столько, сколько стоит у группы
(`groups.tasks`), а не жёсткая тройка: у кого-то есть таджвид и нахв.
"""
import core.db as db
from core.mufradat_api import _my_day


CHAT = "-100555001"


def _student(tasks):
    db.save_group(CHAT, "N-1", tasks=tasks)
    group = db.get_group(CHAT)
    sid = db.add_student("Сатар", group["id"], phone="777501")
    return db.find_user_by_phone("777501"), group


def test_отметки_по_заданиям_группы(test_db):
    user, group = _student("m,r,t,j")
    db.save_report(user["id"], group["id"], db.get_date(), {"m": True, "j": True})

    day = _my_day(user)

    assert [t["k"] for t in day["tasks"]] == ["m", "r", "t", "j"]
    assert [t["done"] for t in day["tasks"]] == [True, False, False, True]
    assert (day["done"], day["total"]) == (2, 4)


def test_пустой_день_это_ноль_из_трёх(test_db):
    user, _group = _student("m,r,t")

    day = _my_day(user)

    assert (day["done"], day["total"]) == (0, 3)
    assert all(not t["done"] for t in day["tasks"])


def test_вчерашние_сдачи_не_считаются(test_db):
    """Полоса про СЕГОДНЯ — вчерашнее закрытие дня её не заполняет."""
    user, group = _student("m,r,t")
    db.save_report(user["id"], group["id"], "2026-01-01", {"m": True, "r": True})

    assert _my_day(user)["done"] == 0


def test_без_группы_полосы_нет(test_db):
    """Человек без учебной группы (устаз со снятой ролью, новичок) — показывать
    нечего, экран просто не рисует полосу."""
    with db.db() as c:
        c.execute("INSERT INTO users(name, phone) VALUES('Гость', '777502')")

    assert _my_day(db.find_user_by_phone("777502")) is None
