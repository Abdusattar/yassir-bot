"""Чужой бот не должен оставлять следа (10.09.2026).

Прямой страх пользователя: «если братья начнут по ошибке региться в женской
базе, это большой трабл». Здесь проверяется, что этого не происходит вообще —
не «его не сделают студентом», а что после захода в чужого бота в его базе
нет НИ ОДНОЙ новой строки.

Ловушка, из-за которой тест и написан: `mark_dm_ok_by_phone` в личке заводит
пустую строку `users` даже незнакомцу (это отметка «боту можно писать
первым»). Поэтому обработчик входа обязан стоять ПЕРВЫМ действием в ветке
лички, до неё.
"""
import asyncio

import core.db as db
import core.handlers as h
from core import web_auth as wa


def _start(monkeypatch, phone, code):
    """Прогоняем настоящий process_message: проверять надо порядок действий
    внутри него, а не отдельно взятую функцию."""
    sent = []
    monkeypatch.setattr(h, "send_message",
                        lambda cid, text, **kw: _noop(sent.append(text)))
    asyncio.run(h.process_message(
        chat_id=phone,                      # личка: chat_id == user_id
        sender=phone,
        text="/start " + wa.LOGIN_START_PREFIX + code,
    ))
    return sent


async def _noop(_):
    return None


def _users_count():
    with db.db() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


def test_stranger_leaves_no_trace_in_this_bots_database(test_db, monkeypatch):
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    code = wa.new_login_code()
    before = _users_count()

    sent = _start(monkeypatch, "777000", code)

    assert _users_count() == before, "чужой заход завёл строку в users"
    with db.db() as c:
        assert c.execute("SELECT COUNT(*) FROM user_groups").fetchone()[0] == 0
        assert c.execute("SELECT COUNT(*) FROM students").fetchone()[0] == 0
    assert sent and "не вижу тебя" in sent[0]


def test_stranger_gets_no_session(test_db, monkeypatch):
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    code = wa.new_login_code()

    _start(monkeypatch, "777000", code)

    assert wa.take_session_for_code(code) is None
    assert wa.poll_login_code(code) == "refused"


def test_own_student_logs_in_normally(test_db, monkeypatch):
    """Оборотная сторона: свой должен войти, а не попасть под тот же отсев."""
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    db.save_group("-100901", "N-1", tasks="m,r,t")
    group = db.get_group("-100901")
    db.add_student("Сатар", group["id"], phone="555111")

    code = wa.new_login_code()
    sent = _start(monkeypatch, "555111", code)

    assert sent and "Вход подтверждён" in sent[0]
    token, user_id = wa.take_session_for_code(code)
    assert user_id == "555111" and wa.resolve_session(token) == "555111"


def test_ustaz_of_a_group_logs_in_too(test_db, monkeypatch):
    """Устаз — не студент, но приложение открывается и ему (кабинет разбора)."""
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    db.save_group("-100901", "N-1", tasks="m,r,t")
    group = db.get_group("-100901")
    db.add_group_admin(group["id"], "555222")

    code = wa.new_login_code()
    sent = _start(monkeypatch, "555222", code)

    assert sent and "Вход подтверждён" in sent[0]
    assert wa.take_session_for_code(code)[1] == "555222"


def test_second_guard_holds_even_if_the_first_is_moved(test_db, monkeypatch):
    """Проверка членства стоит в двух местах, и это не забытый дубль.

    Верхний рубеж следит, чтобы чужой не оставил следа в базе; нижний — чтобы
    ему не выдали ключ от приложения. В обычной жизни нижний недостижим:
    верхний ловит раньше. Здесь он проверяется в лоб — подсовываем may_use_app,
    которая пропускает первый вопрос и отвечает правду на второй, то есть
    ровно то, что случится, если кто-то однажды переставит верхний рубеж.
    """
    answers = iter([True, False])
    monkeypatch.setattr(h, "may_use_app", lambda phone: next(answers, False))

    code = wa.new_login_code()
    sent = _start(monkeypatch, "777000", code)

    assert sent and "не вижу тебя" in sent[0]
    assert wa.take_session_for_code(code) is None
    assert wa.poll_login_code(code) == "refused"
