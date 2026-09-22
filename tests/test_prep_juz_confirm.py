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

    async def fake_kick(chat_id, user_id):
        sent.append(("kick", chat_id, user_id, None))

    async def fake_unban(chat_id, user_id):
        pass

    monkeypatch.setattr(prep, "send_message", fake_send_message)
    monkeypatch.setattr(prep, "send_message_with_buttons", fake_send_message_with_buttons)
    monkeypatch.setattr(prep, "ban_member", fake_kick)
    monkeypatch.setattr(prep, "unban_member", fake_unban)
    return sent


def _dms(sent, phone):
    return [x for x in sent if x[0] == "msg" and x[1] == phone]


def _group_of(phone):
    g = db.get_learning_group(phone)
    return g["id"] if g else None


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


def test_juz_no_moves_to_relaxed_in_db(test_db, monkeypatch):
    """Ответ "не знаю" не требует подтверждения, и с 22.09.2026 переводит
    сразу в базе: человек уже в relaxed-группе и уже не в подготовительной,
    хотя в Telegram-группу по ссылке не вступал. Личка закрыта - в личку
    ничего, но объявления в обоих чатах и уборка из чата prep есть."""
    g = _setup_prep_group()
    relaxed = _setup_relaxed_group()
    db.add_student("Бахтияр", g["id"], phone="p2")
    sent = _capture(monkeypatch)

    asyncio.run(prep.handle_juz_answer("p2", False))

    assert _group_of("p2") == relaxed["id"]
    assert prep._get_prep_row("p2") is None
    assert _dms(sent, "p2") == []
    chats = {x[1] for x in sent if x[0] == "msg"}
    assert chats == {"-100802", "-100777"}
    assert ("kick", "-100777", "p2", None) in sent


def test_juz_confirm_yes_routes_to_n1(test_db, monkeypatch):
    g = _setup_prep_group()
    _setup_n1_group()
    db.add_student("Азим", g["id"], phone="p1")
    db.mark_dm_ok_by_phone("p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_confirm("p1", True))

    n1 = db.get_group("-100801")
    assert _group_of("p1") == n1["id"]
    dm = _dms(sent, "p1")
    assert len(dm) == 1
    # Ссылка теперь - «чат группы для общения», а не условие перевода.
    assert "https://t.me/+n1" in dm[0][2] and "N-1" in dm[0][2]


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

    assert _group_of("p1") == db.get_group("-100802")["id"]


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


def test_group_without_invite_link_still_graduates(test_db, monkeypatch):
    """Ссылка на чат больше не условие перевода (22.09.2026): Н-1 без ссылки
    (её берут по названию, не по ссылке) - перевод всё равно в базе, в
    личке просто нет строки про чат. Relaxed-группы по-прежнему выбираются
    только со ссылкой: она у нас - признак «группа принимает выпускников»."""
    g = _setup_prep_group()
    db.save_group("-100801", "N-1", tasks="m,r,t")
    db.update_group_type("-100801", "pro")
    db.add_student("Азим", g["id"], phone="p1")
    db.mark_dm_ok_by_phone("p1")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p1", True))
    sent.clear()

    asyncio.run(prep.handle_juz_confirm("p1", True))

    assert _group_of("p1") == db.get_group("-100801")["id"]
    assert "t.me" not in _dms(sent, "p1")[0][2]


def test_decision_before_fix_is_caught_up_by_check(test_db, monkeypatch):
    """Решение, принятое ДО правки (ссылка ушла, человек в Telegram не
    вступил - живой случай Шиваза Арафат), переводится в базе ближайшей
    проверкой check_prep_students, а не ссылкой ещё раз."""
    g = _setup_prep_group()
    relaxed = _setup_relaxed_group()
    db.add_student("Шиваза", g["id"], phone="p9")
    st = db.find_by_phone("p9", g["id"])
    db.add_bonus(st["id"], g["id"], db.get_date(), 0, "prep_juz_answer",
                 subcategory="relaxed", note=str(relaxed["id"]))
    monkeypatch.setattr(prep, "count_report_days_since", lambda *a: prep.PREP_MIN_DAYS)
    sent = _capture(monkeypatch)

    asyncio.run(prep.check_prep_students())

    assert _group_of("p9") == relaxed["id"]
    assert prep._get_prep_row("p9") is None


def test_graduation_question_follows_the_db(test_db, monkeypatch):
    """Карточка в приложении: рано - ничего; условие выполнено - вопрос;
    «знаю» - ждём устаза; переведён - снова ничего."""
    g = _setup_prep_group()
    _setup_n1_group()
    _setup_relaxed_group()
    db.add_student("Азим", g["id"], phone="p1")
    _capture(monkeypatch)
    assert prep.graduation_question("p1") is None
    monkeypatch.setattr(prep, "count_report_days_since", lambda *a: prep.PREP_MIN_DAYS)
    assert prep.graduation_question("p1") == {"ask": True, "days": prep.PREP_MIN_DAYS}
    asyncio.run(prep.handle_juz_answer("p1", True))
    assert prep.graduation_question("p1") == {"pending": True}
    asyncio.run(prep.handle_juz_confirm("p1", False))
    assert prep.graduation_question("p1") is None


def test_joining_telegram_group_after_db_graduation_is_noop(test_db, monkeypatch):
    """Переведён в базе, потом всё же вступил в Telegram-чат группы -
    join-обработчик видит «уже в этой группе» и ничего не делает."""
    import core.transfers as transfers
    g = _setup_prep_group()
    relaxed = _setup_relaxed_group()
    db.add_student("Бахтияр", g["id"], phone="p2")
    sent = _capture(monkeypatch)
    asyncio.run(prep.handle_juz_answer("p2", False))
    sent.clear()
    tsent = []

    async def fake(*a, **k):
        tsent.append(a)
    monkeypatch.setattr(transfers, "send_message", fake)
    monkeypatch.setattr(transfers, "ban_member", fake)

    user = db.find_user_by_phone("p2")
    asyncio.run(transfers.handle_known_user_group_join("-100802", relaxed, "p2", user))

    assert tsent == [] and sent == []
    assert _group_of("p2") == relaxed["id"]


def _api(path, user_id, body=None):
    import core.mufradat_api as api

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("POST", path, json=body,
                                        headers={"X-Telegram-Init-Data": user_id})
            return resp.status, (await resp.json())
        finally:
            await client.close()
    return asyncio.run(run())


def test_app_answer_moves_and_repeat_is_refused(test_db, monkeypatch):
    """Ответ из YassirApp: «не знаю» - сразу в группу, ответ несёт её
    название; повторный тап после перевода - 409, ничего не ломает."""
    import core.mufradat_api as api
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    g = _setup_prep_group()
    relaxed = _setup_relaxed_group()
    db.add_student("Бахтияр", g["id"], phone="555")
    _capture(monkeypatch)
    monkeypatch.setattr(prep, "count_report_days_since", lambda *a: prep.PREP_MIN_DAYS)
    assert api._dashboard_facts("555")["prep_grad"] == {"ask": True, "days": prep.PREP_MIN_DAYS}

    status, data = _api("/api/muf/prep/juz", "555", {"knows": False})

    assert status == 200 and data["group"] == "Relaxed-A" and not data["pending"]
    assert _group_of("555") == relaxed["id"]
    assert api._dashboard_facts("555")["prep_grad"] is None
    assert _api("/api/muf/prep/juz", "555", {"knows": False})[0] == 409


def test_app_answer_too_early_is_refused(test_db, monkeypatch):
    """Кнопки нет, пока условие не выполнено, - и запрос в обход тоже не
    переводит."""
    import core.mufradat_api as api
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    g = _setup_prep_group()
    _setup_relaxed_group()
    db.add_student("Бахтияр", g["id"], phone="555")
    _capture(monkeypatch)

    assert _api("/api/muf/prep/juz", "555", {"knows": False})[0] == 409
    assert prep._get_prep_row("555") is not None
