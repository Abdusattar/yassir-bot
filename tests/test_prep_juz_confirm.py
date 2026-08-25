import asyncio

import core.db as db
import core.prep as prep


def _setup_prep_group():
    db.save_group("-100777", "Test Prep", tasks="m,r,t")
    db.update_group_type("-100777", "prep")
    return db.get_group("-100777")


def _setup_n1_group():
    db.save_group("-100801", "N-1", tasks="m,r,t")
    db.update_group_type("-100801", "pro")
    g = db.get_group("-100801")
    db.set_group_invite_link(g["id"], "https://t.me/+n1")
    return db.get_group("-100801")


def _setup_relaxed_group():
    db.save_group("-100802", "Relaxed-A", tasks="m,r,t")
    db.update_group_type("-100802", "relaxed")
    g = db.get_group("-100802")
    db.set_group_invite_link(g["id"], "https://t.me/+relaxed")
    return db.get_group("-100802")


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append(("msg", chat_id, text, None))

    async def fake_send_message_with_buttons(chat_id, text, buttons):
        sent.append(("btn", chat_id, text, buttons))

    monkeypatch.setattr(prep, "send_message", fake_send_message)
    monkeypatch.setattr(prep, "send_message_with_buttons", fake_send_message_with_buttons)
    return sent


def test_juz_yes_asks_ustaz_confirm_not_student(test_db, monkeypatch):
    """25.08.2026: самооценка "знаю" не переводит сразу - только запрос
    Умар устазу, студент пока ничего не получает."""
    g = _setup_prep_group()
    _setup_n1_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)

    asyncio.run(prep.handle_juz_answer("p1", True))

    assert len(sent) == 1
    kind, chat_id, text, buttons = sent[0]
    assert kind == "btn"
    assert chat_id == prep._PREP_GRADUATE_ADMIN_ID
    assert "Азим" in text
    assert buttons[0][1] == "pjzc:yes:p1"
    assert buttons[1][1] == "pjzc:no:p1"


def test_juz_no_routes_directly_to_relaxed(test_db, monkeypatch):
    """Ответ "не знаю" не требует подтверждения - как и раньше."""
    g = _setup_prep_group()
    _setup_relaxed_group()
    db.add_student("Бахтияр", g["id"], phone="p2")
    sent = _capture(monkeypatch)

    asyncio.run(prep.handle_juz_answer("p2", False))

    assert len(sent) == 1
    kind, chat_id, text, _ = sent[0]
    assert kind == "msg"
    assert "https://t.me/+relaxed" in text


def test_juz_confirm_yes_routes_to_n1(test_db, monkeypatch):
    g = _setup_prep_group()
    _setup_n1_group()
    db.add_student("Азим", g["id"], phone="p1")
    db.mark_dm_ok_by_phone("p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_confirm("p1", True))

    assert len(sent) == 1
    kind, chat_id, text, _ = sent[0]
    assert kind == "msg"
    assert chat_id == "p1"
    assert "https://t.me/+n1" in text


def test_juz_confirm_no_routes_to_relaxed(test_db, monkeypatch):
    """Умар отклоняет "знаю" - студент едет туда же, куда и честный "не знаю"."""
    g = _setup_prep_group()
    _setup_n1_group()
    _setup_relaxed_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_confirm("p1", False))

    assert len(sent) == 1
    kind, chat_id, text, _ = sent[0]
    assert "https://t.me/+relaxed" in text


def test_juz_confirm_double_tap_is_idempotent(test_db, monkeypatch):
    """Повторный тап Умара (двойной клик/сеть) не должен слать второй раз."""
    g = _setup_prep_group()
    _setup_n1_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()
    asyncio.run(prep.handle_juz_confirm("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_confirm("p1", True))

    assert sent == []


def test_juz_yes_second_tap_by_student_ignored(test_db, monkeypatch):
    """Пока висит pending_confirm, повторный тап студента по своей же
    кнопке "Знаю" не должен слать Умару второй запрос."""
    g = _setup_prep_group()
    _setup_n1_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_answer("p1", True))

    assert sent == []
