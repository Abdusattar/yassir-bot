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
    monkeypatch.setattr(app_bot, "studies_in", lambda uid: None)
    app_bot.note_contact("5010")
    assert ar.via_app("5010")
    monkeypatch.setattr(app_bot, "studies_in", lambda uid: "male")
    app_bot.note_contact("5011")
    assert not ar.via_app("5011")
    app_bot.note_contact("5010")          # уже учится - новичком остаётся
    assert ar.via_app("5010")
