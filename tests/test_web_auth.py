"""Вход в приложение с сайта (core/web_auth.py, 10.09.2026).

Проверяем не «функции возвращают что-то», а сами обещания входа: код
одноразовый, чужой его не перехватит, протухший не сработает, а в базе
лежит хэш, а не сам токен.
"""
import sqlite3

import pytest

from core import web_auth as wa


def test_code_becomes_token_only_after_bot_confirms(test_db):
    code = wa.new_login_code()
    # Пока бот не подтвердил, браузеру отдавать нечего
    assert wa.take_session_for_code(code) is None

    assert wa.claim_login_code(code, "12345") is True
    token, user_id = wa.take_session_for_code(code, "pytest")
    assert user_id == "12345"
    assert wa.resolve_session(token) == "12345"


def test_code_works_once(test_db):
    code = wa.new_login_code()
    wa.claim_login_code(code, "12345")
    assert wa.take_session_for_code(code) is not None
    # Второй раз тем же кодом (чужая вкладка, история браузера) - мимо
    assert wa.take_session_for_code(code) is None


def test_someone_else_cannot_claim_my_code(test_db):
    code = wa.new_login_code()
    assert wa.claim_login_code(code, "12345") is True
    # Повторный клик того же человека - не ошибка
    assert wa.claim_login_code(code, "12345") is True
    # А вот чужой перехватить уже занятый код не может
    assert wa.claim_login_code(code, "99999") is False
    _, user_id = wa.take_session_for_code(code)
    assert user_id == "12345"


def test_expired_code_is_refused(test_db):
    code = wa.new_login_code()
    with sqlite3.connect(test_db) as c:
        c.execute("UPDATE web_login_codes SET created_at=datetime('now','-2 hours')"
                  " WHERE code=?", (code,))
    assert wa.claim_login_code(code, "12345") is False


@pytest.mark.parametrize("bad", ["", "не-тот-токен", "x" * 43])
def test_garbage_token_gets_nobody_in(test_db, bad):
    assert wa.resolve_session(bad) is None


def test_database_keeps_only_the_hash(test_db):
    """Утечка базы не должна давать возможности войти за студента."""
    code = wa.new_login_code()
    wa.claim_login_code(code, "12345")
    token, _ = wa.take_session_for_code(code)
    with sqlite3.connect(test_db) as c:
        stored = [r[0] for r in c.execute("SELECT token_hash FROM web_sessions")]
    assert token not in stored
    assert len(stored) == 1 and len(stored[0]) == 64


def test_logout_kills_only_that_device(test_db):
    def login():
        code = wa.new_login_code()
        wa.claim_login_code(code, "12345")
        return wa.take_session_for_code(code)[0]

    phone, laptop = login(), login()
    wa.revoke_session(laptop)
    assert wa.resolve_session(laptop) is None
    assert wa.resolve_session(phone) == "12345"      # телефон не тронут


def test_revoke_all_kills_every_device(test_db):
    """Понадобится, если телефон потерян."""
    def login():
        code = wa.new_login_code()
        wa.claim_login_code(code, "12345")
        return wa.take_session_for_code(code)[0]

    a, b = login(), login()
    wa.revoke_all_sessions("12345")
    assert wa.resolve_session(a) is None
    assert wa.resolve_session(b) is None


def test_expired_session_is_refused(test_db):
    code = wa.new_login_code()
    wa.claim_login_code(code, "12345")
    token, _ = wa.take_session_for_code(code)
    with sqlite3.connect(test_db) as c:
        c.execute("UPDATE web_sessions SET expires_at=datetime('now','-1 day')")
    assert wa.resolve_session(token) is None


def test_wrong_side_is_reported_back_to_the_browser(test_db):
    """Человек выбрал мужскую сторону, а учится в женской группе. Бот скажет
    ему об этом в Telegram, но смотрит он в это время в браузер — вкладка
    обязана узнать об отказе и вернуть его к выбору."""
    code = wa.new_login_code()
    assert wa.poll_login_code(code) is None      # пока просто ждём

    wa.refuse_login_code(code)
    assert wa.poll_login_code(code) == "refused"
    # Отказ не выдаёт токен и не занимает код
    assert wa.take_session_for_code(code) is None


def test_refusal_cannot_undo_a_successful_login(test_db):
    """Подтверждённый код отказом уже не сбить — иначе чужой человек, ткнув
    в ту же ссылку, выбивал бы хозяина из входа."""
    code = wa.new_login_code()
    wa.claim_login_code(code, "12345")
    wa.refuse_login_code(code)

    assert wa.poll_login_code(code) is None
    token, user_id = wa.take_session_for_code(code)
    assert user_id == "12345" and wa.resolve_session(token) == "12345"
