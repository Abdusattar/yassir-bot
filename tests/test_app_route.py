"""Личка через @YassirAppBot (01.10.2026, core/app_route.py).

Что проверяем: выключатель (off - ничего не меняется ни для кого), круги
включения test/new/all, что устазы и суперадмины остаются на своих ботах,
что ответ на сообщение в личке бота половины уходит туда же, и запасной
путь: YassirApp не смог - сразу старым, «заблокировал» снимает с YassirApp.
"""
import asyncio

import pytest

import config
import core.app_bot as app_bot
import core.app_inbox as ai
import core.app_route as ar
import core.db as db
import core.tg as tg

pytestmark = pytest.mark.usefixtures("test_db", "test_hadiths_db")

NEWBIE = "5001"      # пришёл к YassirApp, нигде не учась
OLD = "5002"         # старый студент, входил через YassirApp на сайт
TESTER = "5003"
USTAZ = "5004"
SUPER = "5005"


@pytest.fixture
def mode(monkeypatch):
    monkeypatch.setattr(config, "APP_SEND_TOKEN", "app-token")
    monkeypatch.setattr(config, "DM_VIA_APP_TEST_IDS", [TESTER])
    monkeypatch.setattr(config, "SUPER_ADMIN_IDS", [SUPER])
    ar.mark_started(NEWBIE, newcomer=True)
    ar.mark_started(OLD, newcomer=False)
    ar.mark_started(TESTER, newcomer=False)
    ar.mark_started(SUPER, newcomer=True)
    ar.mark_started(USTAZ, newcomer=True)
    db.save_group("-100500", "N-1", tasks="m,r,t")
    db.add_group_admin(db.get_group("-100500")["id"], USTAZ)

    def set_mode(m):
        monkeypatch.setattr(config, "DM_VIA_APP", m)
    return set_mode


def test_off_nobody(mode):
    mode("off")
    assert not any(ar.via_app(u) for u in (NEWBIE, OLD, TESTER, USTAZ, SUPER))


def test_no_token_nobody(mode, monkeypatch):
    """Женский процесс без токена в .env - всё как раньше."""
    mode("all")
    monkeypatch.setattr(config, "APP_SEND_TOKEN", "")
    assert not any(ar.via_app(u) for u in (NEWBIE, OLD, TESTER))


def test_test_mode_only_testers(mode):
    mode("test")
    assert ar.via_app(TESTER)
    assert not ar.via_app(NEWBIE)
    assert not ar.via_app(OLD)


def test_new_mode_only_newcomers(mode):
    mode("new")
    assert ar.via_app(NEWBIE)
    assert ar.via_app(TESTER)
    assert not ar.via_app(OLD), "старый студент не должен ничего заметить"


def test_all_mode_everyone_who_started(mode):
    mode("all")
    assert ar.via_app(NEWBIE) and ar.via_app(OLD)
    assert not ar.via_app("5999"), "не нажимал Старт у YassirApp - писать им нельзя"


def test_staff_stay_on_own_bot(mode):
    mode("all")
    assert not ar.via_app(USTAZ)
    assert not ar.via_app(SUPER)


def test_groups_never(mode):
    mode("all")
    assert not ar.via_app("-100500")


def test_blocked_then_back(mode):
    mode("new")
    ar.mark_blocked(NEWBIE)
    assert not ar.via_app(NEWBIE)
    ar.mark_started(NEWBIE, newcomer=False)   # написал снова - разблокировал
    assert ar.via_app(NEWBIE), "новичком остаётся: решается один раз, при первой встрече"


def test_answer_where_asked(mode):
    """Написал в личку боту половины - ответ туда же, остальным - как обычно."""
    mode("new")
    other = "5006"
    ar.mark_started(other, newcomer=True)

    async def handler():
        return ar.via_app(NEWBIE), ar.via_app(other)

    here, elsewhere = asyncio.run(ar.in_chat(NEWBIE, handler()))
    assert not here and elsewhere
    assert ar.via_app(NEWBIE), "метка живёт только в задаче-обработчике"


def test_dm_ok_counts_app(mode):
    mode("new")
    assert db.get_dm_ok_by_phone(NEWBIE)
    assert not db.get_dm_ok_by_phone(OLD)
    mode("off")
    assert not db.get_dm_ok_by_phone(NEWBIE)


# ── Запасной путь (core/tg.py) ──────────────────────────────────────────────

def _run(mode_fn, chat, app_answer, method="sendMessage"):
    calls = []

    async def attempt(base, label):
        via = "app" if base == ar.api_base() else "own"
        calls.append(via)
        return app_answer if via == "app" else {"ok": True}

    res = asyncio.run(tg._routed(method, chat, attempt))
    return calls, res


def test_route_app_ok(mode):
    mode("new")
    calls, res = _run(mode, NEWBIE, {"ok": True})
    assert calls == ["app"] and res["ok"]


def test_route_blocked_falls_back_and_marks(mode):
    mode("new")
    calls, res = _run(mode, NEWBIE, {"ok": False, "error_code": 403,
                                     "description": "Forbidden: bot was blocked by the user"})
    assert calls == ["app", "own"] and res["ok"]
    assert not ar.via_app(NEWBIE)


def test_route_edit_of_old_message_falls_back_without_block(mode):
    mode("new")
    calls, _ = _run(mode, NEWBIE, {"ok": False, "error_code": 400,
                                   "description": "Bad Request: message to edit not found"},
                    method="editMessageReplyMarkup")
    assert calls == ["app", "own"]
    assert ar.via_app(NEWBIE)


def test_route_network_silence_no_duplicate(mode):
    mode("new")
    calls, res = _run(mode, NEWBIE, None)
    assert calls == ["app"] and res is None


def test_route_other_methods_untouched(mode):
    mode("all")
    calls, _ = _run(mode, NEWBIE, {"ok": True}, method="banChatMember")
    assert calls == ["own"]


def test_route_off_own(mode):
    mode("off")
    calls, _ = _run(mode, NEWBIE, {"ok": True})
    assert calls == ["own"]


# ── Отметка от YassirApp ────────────────────────────────────────────────────

def test_note_contact_newcomer_decided_once(mode, monkeypatch):
    mode("new")
    monkeypatch.setattr(app_bot, "is_newcomer", lambda uid: True)
    monkeypatch.setattr(app_bot, "studies_in", lambda uid: None)
    app_bot.note_contact("5010")
    assert ar.via_app("5010")
    monkeypatch.setattr(app_bot, "is_newcomer", lambda uid: False)
    app_bot.note_contact("5011")
    assert not ar.via_app("5011")
    app_bot.note_contact("5010")          # уже не новичок - решение не меняется
    assert ar.via_app("5010")


def test_is_newcomer_rules(mode):
    assert app_bot.is_newcomer("5020"), "нигде и никогда - новичок"
    gid = db.get_group("-100500")["id"]
    db.add_student("Старый", gid, phone="5021")
    assert not app_bot.is_newcomer("5021"), "учился в постоянной - не новичок"
    assert not app_bot.is_newcomer(USTAZ)
    db.mark_dm_ok_by_phone("5022")
    assert not app_bot.is_newcomer("5022"), "привык к своему боту - остаётся на нём"
    db.save_group("-100600", "prep", tasks="m,r,t")
    with db.db() as c:
        c.execute("UPDATE groups SET group_type='prep' WHERE chat_id='-100600'")
    db.add_student("Новый", db.get_group("-100600")["id"], phone="5023")
    assert app_bot.is_newcomer("5023"), "подготовительная не в счёт"


def test_first_contact_of_prep_student_sends_started(mode, monkeypatch):
    monkeypatch.setattr(app_bot, "studies_in", lambda uid: "female")
    app_bot.note_contact("5030")
    app_bot.note_contact("5030")          # вторая встреча - без события
    monkeypatch.setattr(config, "PROFILE", "female")
    rows = ai.take()
    assert [(r["kind"], r["user_id"]) for r in rows] == [("started", "5030")]


# ── Очередь входящих ────────────────────────────────────────────────────────

@pytest.fixture
def app_wire(monkeypatch):
    calls = []

    async def fake_call(method, payload=None, timeout=35):
        calls.append((method, payload))
        return {"ok": True}
    monkeypatch.setattr(app_bot, "call", fake_call)
    return calls


def _cq(uid, data, message_id=77):
    return {"callback_query": {"id": "q1", "from": {"id": int(uid)}, "data": data,
                               "message": {"message_id": message_id,
                                           "chat": {"id": int(uid), "type": "private"}}}}


def test_callback_goes_to_owner_half(mode, app_wire, monkeypatch):
    monkeypatch.setattr(app_bot, "half_of", lambda uid: "female")
    asyncio.run(app_bot.handle_update(_cq(NEWBIE, "pjz:yes:" + NEWBIE)))
    assert ("editMessageReplyMarkup" in [m for m, _ in app_wire]), "кнопки снимает сам YassirApp"
    monkeypatch.setattr(config, "PROFILE", "male")
    assert ai.take() == [], "мужской процесс чужое не берёт"
    monkeypatch.setattr(config, "PROFILE", "female")
    rows = ai.take()
    assert [(r["kind"], r["data"]) for r in rows] == [("callback", "pjz:yes:" + NEWBIE)]
    assert ai.take() == [], "взятое второй раз не отдаётся"


def test_callback_unknown_half_dropped(mode, app_wire, monkeypatch):
    monkeypatch.setattr(app_bot, "half_of", lambda uid: None)
    asyncio.run(app_bot.handle_update(_cq(NEWBIE, "ponb:2:" + NEWBIE)))
    for p in ("male", "female"):
        monkeypatch.setattr(config, "PROFILE", p)
        assert ai.take() == []


def test_deliver_calls_same_handler(mode, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "male")
    ai.enqueue("male", "callback", NEWBIE, "upg:pro:%s:3" % NEWBIE)
    got = []

    async def handle(uid, data, chat_id, message_id):
        got.append((uid, data, chat_id, message_id))
    assert asyncio.run(ai.deliver_once(handle)) == 1
    assert got == [(NEWBIE, "upg:pro:%s:3" % NEWBIE, NEWBIE, None)]


def test_deliver_skips_stale(mode, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "male")
    ai.enqueue("male", "callback", NEWBIE, "pjz:no:" + NEWBIE)
    with ai._connect() as c:
        c.execute("UPDATE app_inbox SET created_at='2020-01-01 00:00:00'")
    got = []

    async def handle(*a):
        got.append(a)
    asyncio.run(ai.deliver_once(handle))
    assert got == []


def test_started_only_for_app_channel(mode, monkeypatch):
    import core.prep as prep
    import core.transfers as transfers
    hits = []

    async def unlocked(uid):
        hits.append(("unlocked", uid))

    async def onb(uid):
        hits.append(("onboarding", uid))
    monkeypatch.setattr(transfers, "handle_dm_unlocked", unlocked)
    monkeypatch.setattr(prep, "send_prep_onboarding_if_pending", onb)
    mode("new")
    asyncio.run(ai.on_started(OLD))
    assert hits == [], "старый - не наш канал, писать ему через YassirApp нельзя"
    asyncio.run(ai.on_started(NEWBIE))
    assert hits == [("unlocked", NEWBIE), ("onboarding", NEWBIE)]


def test_member_on_app_channel_not_sent_to_half_bot(mode, monkeypatch):
    mode("new")
    sent = []

    async def fake_send(chat_id, text, buttons=None):
        sent.append(text)
    monkeypatch.setattr(app_bot, "send", fake_send)
    monkeypatch.setattr(app_bot, "studies_in", lambda uid: "male")
    monkeypatch.setattr(config, "MUSHAF_APP_LINK", "https://t.me/yassirquranbot/app")
    asyncio.run(app_bot.way_in(NEWBIE))
    assert "на связи здесь" in sent[-1] and "t.me/yassirquranbot/app" in sent[-1]
    asyncio.run(app_bot.way_in(OLD))
    assert "Твой бот" in sent[-1], "старому - как раньше"


# ── Шаг 3: куда звать «нажми Старт» ─────────────────────────────────────────

def test_start_link_for(mode):
    import core.bots as bots
    bots.register_app("YassirAppBot")
    mode("off")
    assert ar.start_link_for("5040") is None
    mode("new")
    assert ar.start_link_for("5040") == "https://t.me/YassirAppBot?start=go"
    gid = db.get_group("-100500")["id"]
    db.add_student("Старый", gid, phone="5041")
    assert ar.start_link_for("5041") is None, "старого зовём к его боту, как раньше"
    assert ar.start_link_for(USTAZ) is None
    mode("test")
    assert ar.start_link_for("5040") is None
    assert ar.start_link_for(TESTER) == "https://t.me/YassirAppBot?start=go"


def test_prep_greeting_points_newcomer_to_app(mode, monkeypatch):
    import core.bots as bots
    import core.prep as prep
    bots.register_app("YassirAppBot")
    sent = []

    async def fake_send(chat_id, text, *a, **k):
        sent.append(text)

    async def bot_link():
        return "https://t.me/yassirquranbot?start=go"
    monkeypatch.setattr(prep, "send_message", fake_send)
    monkeypatch.setattr(prep, "get_dm_start_link", bot_link)
    mode("new")
    asyncio.run(prep.send_prep_onboarding_group_message("-100600", "Али", "ru", False, uid="5050"))
    assert "YassirAppBot" in sent[-1]
    mode("off")
    asyncio.run(prep.send_prep_onboarding_group_message("-100600", "Али", "ru", False, uid="5050"))
    assert "yassirquranbot" in sent[-1], "выключено - как было"


# ── Шаг 4: две двери ────────────────────────────────────────────────────────

def test_side_answer_gives_prep_link_directly(mode, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, buttons=None):
        sent.append(text)
    monkeypatch.setattr(app_bot, "send", fake_send)
    monkeypatch.setattr(app_bot, "own_prep_link", lambda: "https://t.me/+MALEPREP")
    monkeypatch.setattr(app_bot, "other_bot_prep_link", lambda: "https://t.me/+FEMPREP")
    mode("new")
    asyncio.run(app_bot.send_to_side(NEWBIE, "male"))
    assert "t.me/+MALEPREP" in sent[-1] and "заявку" in sent[-1]
    asyncio.run(app_bot.send_to_side(NEWBIE, "female"))
    assert "t.me/+FEMPREP" in sent[-1]


def test_side_answer_old_way_when_not_routed(mode, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, buttons=None):
        sent.append(text)
    monkeypatch.setattr(app_bot, "send", fake_send)
    monkeypatch.setattr(app_bot, "_bot_links", lambda side: ("https://t.me/yassirquranbot",
                                                             "https://t.me/yassirquranbot?start=go"))
    monkeypatch.setattr(app_bot, "own_prep_link", lambda: "https://t.me/+MALEPREP")
    mode("off")
    asyncio.run(app_bot.send_to_side(NEWBIE, "male"))
    assert "yassirquranbot?start=go" in sent[-1] and "+MALEPREP" not in sent[-1]


def test_side_answer_no_prep_link_falls_back(mode, monkeypatch):
    sent = []

    async def fake_send(chat_id, text, buttons=None):
        sent.append(text)
    monkeypatch.setattr(app_bot, "send", fake_send)
    monkeypatch.setattr(app_bot, "_bot_links", lambda side: ("x", "https://t.me/yassirquranbot?start=go"))
    monkeypatch.setattr(app_bot, "own_prep_link", lambda: "")
    mode("new")
    asyncio.run(app_bot.send_to_side(NEWBIE, "male"))
    assert "yassirquranbot?start=go" in sent[-1]
