import asyncio

import core.db as db
import core.prep as prep
import core.transfers as transfers


def _setup_prep_group():
    db.save_group("-100777", "Test Prep", tasks="m,r,t")
    db.update_group_type("-100777", "prep")
    return db.get_group("-100777")


def _capture(monkeypatch):
    sent = []

    async def fake_send_message(chat_id, text, reply_to_message_id=None):
        sent.append(("text", chat_id, text, None))

    async def fake_send_photo(chat_id, photo_path, caption=None):
        sent.append(("photo", chat_id, photo_path, None))

    async def fake_send_message_with_buttons(chat_id, text, buttons):
        sent.append(("text", chat_id, text, buttons))

    async def fake_send_photo_with_buttons(chat_id, photo_path, buttons, caption=None):
        sent.append(("photo", chat_id, photo_path, buttons))
        return {"ok": True}

    monkeypatch.setattr(prep, "send_message", fake_send_message)
    monkeypatch.setattr(prep, "send_photo", fake_send_photo)
    monkeypatch.setattr(prep, "send_message_with_buttons", fake_send_message_with_buttons)
    monkeypatch.setattr(prep, "send_photo_with_buttons", fake_send_photo_with_buttons)
    return sent


def test_is_active_prep_student_true_for_prep(test_db):
    g = _setup_prep_group()
    db.add_student("Азим", g["id"], phone="p1")
    assert db.is_active_prep_student("p1") is True


def test_is_active_prep_student_false_for_regular_group(test_db):
    db.save_group("-100778", "Regular Group")
    g = db.get_group("-100778")
    db.add_student("Бахтияр", g["id"], phone="p2")
    assert db.is_active_prep_student("p2") is False


def test_is_active_prep_student_false_unknown_phone(test_db):
    assert db.is_active_prep_student("nobody") is False


def test_onboarding_group_message_needs_start_when_dm_not_ok(test_db, monkeypatch):
    sent = _capture(monkeypatch)

    async def fake_link():
        return "https://t.me/testbot?start=go"
    monkeypatch.setattr(prep, "get_dm_start_link", fake_link)

    asyncio.run(prep.send_prep_onboarding_group_message("-100777", "Азим", "ru", dm_ok=False))

    assert len(sent) == 1
    assert "Start" in sent[0][2]
    assert "testbot" in sent[0][2]


def test_onboarding_group_message_skips_link_when_dm_ok(test_db, monkeypatch):
    sent = _capture(monkeypatch)
    asyncio.run(prep.send_prep_onboarding_group_message("-100777", "Азим", "ru", dm_ok=True))

    assert len(sent) == 1
    assert "личные сообщения" in sent[0][2]


def test_onboarding_dm_sends_only_first_screen_with_button(test_db, monkeypatch):
    """13.08.2026: онбординг теперь по экранам (кнопка "Далее"), не 9
    сообщений подряд - точка входа шлёт только первый экран (интро)."""
    sent = _capture(monkeypatch)

    asyncio.run(prep.send_prep_onboarding_dm("p1", "ru"))

    assert len(sent) == 1
    kind, chat_id, content, buttons = sent[0]
    assert kind == "text"
    assert chat_id == "p1"
    assert buttons is not None and buttons[0][1] == "ponb:1:p1"


def test_onboarding_photo_failure_falls_back_to_text_button(test_db, monkeypatch):
    """Если send_photo_with_buttons не вернул ok (битый файл/сбой Telegram),
    кнопка "Далее" всё равно должна дойти текстом - иначе стрим
    останавливается навсегда без единого способа продолжить."""
    sent = _capture(monkeypatch)

    async def failing_send_photo_with_buttons(chat_id, photo_path, buttons, caption=None):
        return {"ok": False, "description": "file not found"}
    monkeypatch.setattr(prep, "send_photo_with_buttons", failing_send_photo_with_buttons)

    asyncio.run(prep._send_onboarding_screen("p1", 1, "ru"))  # экран "Заучивание"

    texts_with_buttons = [s for s in sent if s[0] == "text" and s[3]]
    assert len(texts_with_buttons) == 1
    assert texts_with_buttons[0][3][0][1] == "ponb:2:p1"


def test_onboarding_full_walkthrough_six_screens(test_db, monkeypatch):
    """Проходим все экраны кнопками "Далее" (как реальный клик студента,
    через handle_prep_onboarding_next) - в сумме должно получиться то же
    содержимое, что раньше уходило одним потоком: 6 текстов, 3 фото,
    последний экран без кнопки."""
    g = _setup_prep_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)

    asyncio.run(prep.send_prep_onboarding_dm("p1", "ru"))
    screen = 1
    while sent[-1][3] is not None:
        next_idx = sent[-1][3][0][1].split(":")[1]
        asyncio.run(prep.handle_prep_onboarding_next("p1", int(next_idx)))
        screen += 1
        assert screen <= 10  # защита от бесконечного цикла, если что-то сломано

    texts = [s for s in sent if s[0] == "text"]
    photos = [s for s in sent if s[0] == "photo"]
    assert len(texts) == 6
    assert len(photos) == 3
    assert {p[2].split("\\")[-1].split("/")[-1] for p in photos} == {
        "Заучивание.PNG", "Повторение.PNG", "Слова.PNG"
    }
    assert sent[-1][3] is None  # последний экран (адаб) - без кнопки


def test_onboarding_if_pending_sends_for_active_prep_student(test_db, monkeypatch):
    g = _setup_prep_group()
    db.add_student("Азим", g["id"], phone="p1")
    sent = _capture(monkeypatch)

    asyncio.run(prep.send_prep_onboarding_if_pending("p1"))

    assert len([s for s in sent if s[0] == "text"]) == 1


def test_onboarding_if_pending_noop_for_non_prep_student(test_db, monkeypatch):
    db.save_group("-100779", "Regular")
    g = db.get_group("-100779")
    db.add_student("Санжар", g["id"], phone="p3")
    sent = _capture(monkeypatch)

    asyncio.run(prep.send_prep_onboarding_if_pending("p3"))

    assert sent == []


def test_join_onboarding_not_double_sent_on_chat_member_and_new_chat_members(test_db, monkeypatch):
    """Telegram шлёт и chat_member, и new_chat_members на один и тот же
    вход - bot.py вызывает handle_known_user_group_join дважды подряд для
    одного человека. Онбординг новичка должен уйти один раз, не два
    (25.08.2026, риск пойман advisor'ом: is_true_newcomer читает историю
    ДО add_student, но на втором вызове add_student первого вызова уже
    сделал его "не новичком")."""
    g = _setup_prep_group()
    db.mark_dm_ok_by_phone("p1")
    db.save_dm_registration_name("p1", "Азим")
    existing_user = db.find_user_by_phone("p1")

    group_sent = []

    async def fake_group_msg(chat_id, name, glang, dm_ok):
        group_sent.append(name)
    monkeypatch.setattr(transfers, "send_prep_onboarding_group_message", fake_group_msg)

    asyncio.run(transfers.handle_known_user_group_join("-100777", g, "p1", existing_user))
    asyncio.run(transfers.handle_known_user_group_join("-100777", g, "p1", existing_user))

    assert group_sent == ["Азим"]
