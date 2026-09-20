"""Две половины не смешиваются (18.09.2026).

Случай Динары 17.09: сестра однажды написала /start мужскому боту и с тех
пор открывала YassirApp из его чата - мусхаф работал, сдача отвечала «нет
группы», а следы шли в мужскую базу. Решение пользователя: ни одна дверь не
заводит человека у себя, пока не спросила соседа. Здесь проверяются все
двери разом - личка, вход с сайта, приложение внутри Telegram, группа.
"""
import asyncio
import sqlite3

import pytest

import config
import core.db as db
import core.bots as bots
import core.handlers as h
import core.mufradat_api as api
import core.transfers as tr
from core import web_auth as wa

pytestmark = pytest.mark.usefixtures("test_hadiths_db")

SISTER = "555"      # учится в женском боте
BROTHER = "999"     # учится здесь, в мужском
STRANGER = "777"    # нигде


@pytest.fixture
def two_bots(tmp_path, monkeypatch, fresh_db):
    """Мужская база - наша, женская лежит рядом (так other_bot_member её и
    находит), оба бота представились в общей базе."""
    other = tmp_path / "quran_female.db"
    c = sqlite3.connect(other)
    c.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
        CREATE TABLE groups(id INTEGER PRIMARY KEY, group_type TEXT);
        CREATE TABLE user_groups(user_id INT, group_id INT, role TEXT, active INT);
        INSERT INTO users VALUES(1, 'Динара', '555');
        INSERT INTO groups VALUES(6, 'relaxed');
        INSERT INTO user_groups VALUES(1, 6, 'student', 1);
    """)
    c.commit()
    c.close()
    monkeypatch.setattr(config, "PROFILE", "female")
    bots.register_self("yassir_female_bot")
    monkeypatch.setattr(config, "PROFILE", "male")
    bots.register_self("yassirquranbot")
    monkeypatch.setattr(db, "DB", fresh_db(tmp_path / "quran_male.db"))
    db.save_group("-100901", "N-1", tasks="m,r,t")
    db.add_student("Сатар", db.get_group("-100901")["id"], phone=BROTHER)
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    monkeypatch.setattr(tr, "SUPER_ADMIN_IDS", ["1"])
    return {"female_db": str(other)}


def _dm(monkeypatch, phone, text):
    sent = []

    async def fake(cid, text, **kw):
        sent.append((str(cid), text))
        return {"ok": True}
    monkeypatch.setattr(h, "send_message", fake)
    monkeypatch.setattr(tr, "send_message", fake)
    asyncio.run(h.process_message(chat_id=phone, sender=phone, text=text))
    return sent


def _users():
    with db.db() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── Личка ────────────────────────────────────────────────────────────────────

def test_sister_in_male_bot_gets_the_door_and_leaves_no_trace(test_db, two_bots, monkeypatch):
    before = _users()
    sent = _dm(monkeypatch, SISTER, "/start")
    assert _users() == before
    assert len(sent) == 1 and sent[0][0] == SISTER
    assert "женском джамаате" in sent[0][1]
    assert "https://t.me/yassir_female_bot" in sent[0][1]


def test_bots_registry_knows_the_neighbour(test_db, two_bots):
    other = bots.other_bot()
    assert other["profile"] == "female"
    assert other["chat_link"] == "https://t.me/yassir_female_bot"
    assert other["app_link"] == "https://t.me/yassir_female_bot"   # прямой ссылки нет - чат
    assert other["jamaat"] == "женском"


def test_without_registry_the_door_is_still_named(test_db, two_bots, monkeypatch):
    """Сосед ещё не запускался с новым кодом - ссылки нет, но и молчать
    нельзя: говорим, какой это джамаат."""
    monkeypatch.setattr(h, "other_bot", lambda: None)
    sent = _dm(monkeypatch, SISTER, "/start")
    assert "женском джамаате" in sent[0][1] and "t.me" not in sent[0][1]


def test_super_admin_is_not_redirected(test_db, two_bots, monkeypatch):
    """Id супер-админов прописаны в .env обоих ботов: в женском боте мужской
    супер-админ управляет, а не «ошибся дверью»."""
    with sqlite3.connect(two_bots["female_db"]) as c:
        c.execute("INSERT INTO users VALUES(2, 'Умар', '42')")
        c.execute("INSERT INTO user_groups VALUES(2, 6, 'admin', 1)")
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", ["42"])
    sent = _dm(monkeypatch, "42", "/start")
    assert all("джамаате" not in t for _, t in sent)


# ── Вход с сайта ─────────────────────────────────────────────────────────────

def test_sister_logs_in_through_the_male_bot_link(test_db, two_bots, monkeypatch, tmp_path):
    """На сайте одна кнопка, ссылка ведёт в мужской бот. Он находит сестру у
    соседа и подтверждает код ДЛЯ ЖЕНСКОГО профиля - сессию выдаст женский
    процесс из своей базы, мужской ничего у себя не пишет."""
    code = wa.new_login_code()
    before = _users()
    sent = _dm(monkeypatch, SISTER, "/start " + wa.LOGIN_START_PREFIX + code)

    assert _users() == before
    assert "Вход подтверждён" in sent[0][1]
    assert "бот" not in sent[0][1].lower().replace("возвращайся", "")   # где её бот - не говорим
    assert wa.login_code_profile(code) == "female"
    assert wa.take_session_for_code(code) is None      # мужской процесс не отдаёт
    assert wa.poll_login_code(code) is None            # и это не отказ

    # Теперь тот же код спрашивает женский процесс
    monkeypatch.setattr(config, "PROFILE", "female")
    monkeypatch.setattr(db, "DB", two_bots["female_db"])
    wa.init_web_auth()      # у женского процесса своя таблица сессий
    token, user_id = wa.take_session_for_code(code)
    assert user_id == SISTER and wa.resolve_session(token) == SISTER


def test_poll_tells_the_browser_to_ask_the_other_process(test_db, two_bots):
    code = wa.new_login_code()
    wa.claim_login_code(code, SISTER, profile="female")

    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("GET", "/api/muf/auth/poll?code=" + code)
            return resp.status, await resp.json()
        finally:
            await client.close()
    status, data = asyncio.run(run())
    assert status == 200 and data == {"pending": True, "profile": "female"}


def test_stranger_is_refused_without_a_hint_about_sides(test_db, two_bots, monkeypatch):
    code = wa.new_login_code()
    before = _users()
    sent = _dm(monkeypatch, STRANGER, "/start " + wa.LOGIN_START_PREFIX + code)
    assert _users() == before
    assert "не вижу тебя" in sent[0][1] and "женск" not in sent[0][1]
    assert wa.poll_login_code(code) == "refused"


# ── Приложение внутри Telegram ───────────────────────────────────────────────

def _get(path, user_id):
    async def run():
        from aiohttp.test_utils import TestClient, TestServer
        client = TestClient(TestServer(api.build_app()))
        await client.start_server()
        try:
            resp = await client.request("GET", path, headers={"X-Telegram-Init-Data": user_id})
            return resp.status, await resp.json()
        finally:
            await client.close()
    return asyncio.run(run())


def test_app_opened_from_the_wrong_bot_is_stopped_at_the_door(test_db, two_bots, monkeypatch):
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    status, data = _get("/api/muf/lang", SISTER)
    assert status == 403
    assert data == {"error": "wrong_bot", "jamaat": "женском",
                    "app_link": "https://t.me/yassir_female_bot"}


def test_own_student_and_stranger_pass_the_door(test_db, two_bots, monkeypatch):
    """Своего пускаем; незнакомца (ни в одной базе) тоже - ему приложение
    само объясняет, куда идти, это не смешение половин."""
    monkeypatch.setattr(api, "validate_init_data", lambda raw, token: {"id": raw})
    assert _get("/api/muf/lang", BROTHER)[0] == 200
    assert _get("/api/muf/lang", STRANGER)[0] == 200


# ── Группа ───────────────────────────────────────────────────────────────────

def test_sister_writing_in_a_male_group_is_not_registered(test_db, two_bots, monkeypatch):
    sent = _dm(monkeypatch, SISTER, "Ассаляму алейкум, м р т")   # chat_id=SISTER - личка
    # А теперь в группе:
    sent = []

    async def fake(cid, text, **kw):
        sent.append((str(cid), text))
        return {"ok": True}
    monkeypatch.setattr(h, "send_message", fake)
    monkeypatch.setattr(tr, "send_message", fake)
    asyncio.run(h.process_message(chat_id="-100901", sender=SISTER, text="м р т", sender_name="Динара"))

    with db.db() as c:
        assert c.execute("SELECT COUNT(*) FROM user_groups ug JOIN users u ON u.id=ug.user_id"
                         " WHERE u.phone=?", (SISTER,)).fetchone()[0] == 0
    to = {cid for cid, _ in sent}
    assert to == {SISTER, "1"}, sent                    # личка ей и супер-админу, не в группу
    dm = [t for cid, t in sent if cid == SISTER][0]
    assert "«N-1»" in dm and "женском джамаате" in dm and "t.me/yassir_female_bot" in dm
    admin = [t for cid, t in sent if cid == "1"][0]
    assert "Динара" in admin and "второго бота" in admin

    # Второе сообщение - тишина: отсчёт до кика уже идёт, повторять незачем
    sent.clear()
    asyncio.run(h.process_message(chat_id="-100901", sender=SISTER, text="м р т", sender_name="Динара"))
    assert sent == []


def test_join_handler_counts_down_like_any_unregistered(test_db, two_bots, monkeypatch):
    sent = []

    async def fake(cid, text, **kw):
        sent.append((str(cid), text))
        return {"ok": True}
    monkeypatch.setattr(tr, "send_message", fake)
    group = db.get_group("-100901")
    asyncio.run(tr.handle_other_bot_member_in_group("-100901", group, SISTER, "Динара"))
    with db.db() as c:
        row = c.execute("SELECT 1 FROM unregistered_members WHERE user_id=? AND chat_id=?",
                        (SISTER, "-100901")).fetchone()
    assert row is not None
    assert {cid for cid, _ in sent} == {SISTER, "1"}
