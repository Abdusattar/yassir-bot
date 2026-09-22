"""Общая дверь @YassirAppBot (22.09.2026, core/app_bot.py).

Что проверяем: вход с сайта через ОДИН бот для обеих половин (код
подтверждается для той базы, где человек учится), встреча знакомого,
вопрос «брат или сестра» незнакомцу и то, что общий бот не заводит строк
ни в одной базе - он только показывает дорогу.
"""
import asyncio
import sqlite3

import pytest

import config
import core.app_bot as app_bot
import core.bots as bots
import core.db as db
import core.mufradat_api as api
import core.side as side
import core.tg as tg
from core import web_auth as wa

pytestmark = pytest.mark.usefixtures("test_hadiths_db")

BROTHER = "111"          # активный студент мужской N-1
SISTER = "222"           # активна у сестёр
STRANGER = "333"         # нигде и никогда
MALE_PREP_CHAT = "-100777"
N1_CHAT = "-100901"


@pytest.fixture
def world(tmp_path, monkeypatch, fresh_db):
    """Мужская база - наша, женская - соседская, оба бота представлены,
    общий бот с токеном."""
    other = tmp_path / "quran_female.db"
    c = sqlite3.connect(other)
    c.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
        CREATE TABLE groups(id INTEGER PRIMARY KEY, group_type TEXT);
        CREATE TABLE user_groups(user_id INT, group_id INT, role TEXT, active INT);
        INSERT INTO groups VALUES(6, 'relaxed');
        INSERT INTO users VALUES(1, 'Динара', '222');
        INSERT INTO user_groups VALUES(1, 6, 'student', 1);
    """)
    c.commit()
    c.close()

    monkeypatch.setattr(config, "PROFILE", "female")
    bots.register_self("yassir_female_bot")
    monkeypatch.setattr(config, "PROFILE", "male")
    bots.register_self("yassirquranbot")
    bots.register_app("YassirAppBot")
    monkeypatch.setattr(config, "APP_BOT_TOKEN", "test-token")
    monkeypatch.setattr(tg, "_bot_username", "yassirquranbot", raising=False)

    monkeypatch.setattr(db, "DB", fresh_db(tmp_path / "quran_male.db"))
    db.save_group(N1_CHAT, "N-1", tasks="m,r,t")
    db.save_group(MALE_PREP_CHAT, "Yassir подготовительная", tasks="m,r,t")
    with db.db() as cc:
        cc.execute("UPDATE groups SET group_type='pro' WHERE chat_id=?", (N1_CHAT,))
        cc.execute("UPDATE groups SET group_type='prep', invite_link='https://t.me/+MALEPREP'"
                   " WHERE chat_id=?", (MALE_PREP_CHAT,))
    db.add_student("Сатар", db.get_group(N1_CHAT)["id"], phone=BROTHER)
    return {"female_db": str(other)}


@pytest.fixture
def wire(monkeypatch):
    """Перехват отправки общего бота: (chat_id, text, buttons|None)."""
    sent = []

    async def fake_send(chat_id, text, buttons=None):
        sent.append((str(chat_id), text, buttons))
        return {"ok": True}

    async def fake_ban(chat_id, uid):
        return {"ok": True}

    monkeypatch.setattr(app_bot, "send", fake_send)
    monkeypatch.setattr(side, "ban_member", fake_ban)
    monkeypatch.setattr(side, "unban_member", fake_ban)
    return sent


def _dm(uid, text):
    asyncio.run(app_bot.handle_text(uid, text))


def _users():
    with db.db() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── Вход с сайта ─────────────────────────────────────────────────────────────

def test_login_of_a_brother_is_claimed_for_the_male_base(test_db, world, wire):
    code = wa.new_login_code()
    _dm(BROTHER, "/start login_" + code)

    assert wa.login_code_profile(code) == "male"
    assert "Вход подтверждён" in wire[0][1]
    # Сессию выдаёт мужской процесс - он же и опрашивается вкладкой.
    assert wa.take_session_for_code(code)[1] == BROTHER


def test_login_of_a_sister_is_claimed_for_her_base(test_db, world, wire):
    """Сестра входит через тот же бот: код помечается женским профилем, а
    мужской процесс сессию по нему НЕ выдаёт - это делает женский."""
    code = wa.new_login_code()
    _dm(SISTER, "/start login_" + code)

    assert wa.login_code_profile(code) == "female"
    assert "Вход подтверждён" in wire[0][1]
    assert wa.take_session_for_code(code) is None
    assert _users() == 1        # в мужской базе следа сестры нет


def test_login_of_a_stranger_is_refused_and_he_gets_the_question(test_db, world, wire):
    code = wa.new_login_code()
    _dm(STRANGER, "/start login_" + code)

    assert wa.poll_login_code(code) == "refused"
    assert "не вижу тебя среди учащихся" in wire[0][1]
    assert "брат или сестра" in wire[1][1]
    assert [b[1] for b in wire[1][2]] == ["side:male:333", "side:female:333"]
    assert _users() == 1        # строки users незнакомцу не завели


# ── Первая встреча ───────────────────────────────────────────────────────────

def test_known_student_is_sent_to_his_own_bot(test_db, world, wire):
    _dm(BROTHER, "/start go")
    assert "мужском джамаате" in wire[0][1]
    assert "https://t.me/yassirquranbot" in wire[0][1]


def test_sister_is_sent_to_her_own_bot(test_db, world, wire):
    _dm(SISTER, "Ассаляму алейкум")
    assert "женском джамаате" in wire[0][1]
    assert "https://t.me/yassir_female_bot" in wire[0][1]


def test_answer_leads_to_the_bot_of_that_half_not_to_a_group(test_db, world, wire):
    """Ответ незнакомца ведёт в БОТ половины, а не сразу в группу: половине
    нужна открытая личка (онбординг, вопрос про джуз), а свой бот уже знает
    ответ и даст ссылку на подготовительную сам."""
    asyncio.run(app_bot.handle_side_answer(STRANGER, "female"))
    assert "женском джамаате" in wire[-1][1]
    assert "https://t.me/yassir_female_bot?start=go" in wire[-1][1]
    assert "t.me/+" not in wire[-1][1]
    assert side.known_side(STRANGER) == "female"

    wire.clear()
    asyncio.run(app_bot.handle_side_answer(STRANGER, "male"))
    assert "https://t.me/yassirquranbot?start=go" in wire[-1][1]
    assert side.known_side(STRANGER) == "male"

    # Вопрос второй раз не задаётся - половина уже известна.
    wire.clear()
    _dm(STRANGER, "привет")
    assert len(wire) == 1 and wire[0][2] is None


def test_penalised_student_of_the_neighbour_is_not_a_stranger(test_db, world, wire):
    """Кикнутая за пропуски сестра сейчас нигде не активна, но через её
    устаза проходила - вопроса ей не задаём, ведём к её боту."""
    c = sqlite3.connect(world["female_db"])
    c.executescript("INSERT INTO users VALUES(2, 'Арзу', '556');"
                    "INSERT INTO user_groups VALUES(2, 6, 'student', 0);")
    c.commit()
    c.close()

    _dm("556", "/start go")
    assert wire[0][2] is None
    assert "https://t.me/yassir_female_bot?start=go" in wire[0][1]


# ── Ссылки наружу ────────────────────────────────────────────────────────────

def test_site_login_link_goes_to_the_common_bot(test_db, world, monkeypatch):
    """Кнопка «Войти через Telegram» ведёт в общий бот, пока он есть."""
    assert bots.app_bot_username() == "YassirAppBot"
    assert api.app_bot_username() == "YassirAppBot"


def test_without_the_common_bot_everything_works_as_before(test_db, world, monkeypatch, wire):
    """Токена нет - общего бота нет: вход и приглашение идут через свои
    боты, как до 22.09."""
    with bots._connect() as c:
        c.execute("DELETE FROM bot_registry WHERE profile='app'")
    assert bots.app_bot_username() == ""
    assert bots.app_invite_link() is None
