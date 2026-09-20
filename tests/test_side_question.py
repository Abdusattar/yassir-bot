"""Брат или сестра (20.09.2026, core/side.py).

Случаи из карты дверей 20.09: Бурулсун пришла с сайта в мужского бота и
получила ссылку на мужскую подготовительную; Канат по пересланной ссылке
вошёл в женскую; Муса, активный студент, написал в подготовительной - и
его перевели туда, выкинув из своей группы. Здесь проверяются вопрос,
память ответа, дорога к соседу, штрафница соседа и guard в сообщении.
"""
import asyncio
import sqlite3

import pytest

import config
import core.db as db
import core.bots as bots
import core.handlers as h
import core.side as side
import core.transfers as tr
import core.prep as prep
from core import web_auth as wa

pytestmark = pytest.mark.usefixtures("test_hadiths_db")

STRANGER = "777"
BROTHER = "999"          # активный студент N-1 (мужская)
SISTER_ACTIVE = "555"    # активна у сестёр
SISTER_PENALTY = "556"   # у сестёр была в relaxed, сейчас нигде не активна
MISPLACED = "558"        # сестра, по ошибке записанная в мужскую prep

MALE_PREP_CHAT = "-100777"
N1_CHAT = "-100901"


@pytest.fixture
def world(tmp_path, monkeypatch):
    other = tmp_path / "quran_female.db"
    c = sqlite3.connect(other)
    c.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY, name TEXT, phone TEXT);
        CREATE TABLE groups(id INTEGER PRIMARY KEY, group_type TEXT);
        CREATE TABLE user_groups(user_id INT, group_id INT, role TEXT, active INT);
        INSERT INTO groups VALUES(6, 'relaxed');
        INSERT INTO groups VALUES(7, 'prep');
        INSERT INTO users VALUES(1, 'Динара', '555');
        INSERT INTO user_groups VALUES(1, 6, 'student', 1);
        INSERT INTO users VALUES(2, 'Арзу', '556');
        INSERT INTO user_groups VALUES(2, 6, 'student', 0);
    """)
    c.commit()
    c.close()
    monkeypatch.setattr(config, "PROFILE", "female")
    bots.register_self("yassir_female_bot")
    monkeypatch.setattr(config, "PROFILE", "male")
    bots.register_self("yassirquranbot")
    monkeypatch.setattr(db, "DB", str(tmp_path / "quran_male.db"))
    db.init()
    db.save_group(N1_CHAT, "N-1", tasks="m,r,t")
    db.save_group(MALE_PREP_CHAT, "Yassir подготовительная", tasks="m,r,t")
    with db.db() as cc:
        cc.execute("UPDATE groups SET group_type='pro' WHERE chat_id=?", (N1_CHAT,))
        cc.execute("UPDATE groups SET group_type='prep', invite_link='https://t.me/+MALEPREP' WHERE chat_id=?", (MALE_PREP_CHAT,))
    db.add_student("Сатар", db.get_group(N1_CHAT)["id"], phone=BROTHER)
    db.add_student("Бурулсун", db.get_group(MALE_PREP_CHAT)["id"], phone=MISPLACED)
    monkeypatch.setattr(h, "SUPER_ADMIN_IDS", [])
    monkeypatch.setattr(tr, "SUPER_ADMIN_IDS", ["1"])
    return {"female_db": str(other)}


@pytest.fixture
def wire(monkeypatch):
    """Перехват всех исходящих: (chat_id, text, buttons|None), плюс список
    кикнутых из чатов."""
    sent, kicked = [], []

    async def fake(cid, text, **kw):
        sent.append((str(cid), text, None))
        return {"ok": True}

    async def fake_btn(cid, text, buttons):
        sent.append((str(cid), text, buttons))
        return {"ok": True}

    async def fake_ban(chat_id, uid):
        kicked.append((str(chat_id), str(uid)))
        return {"ok": True}

    async def fake_unban(chat_id, uid):
        return {"ok": True}

    for mod in (h, tr, side, prep):
        monkeypatch.setattr(mod, "send_message", fake, raising=False)
        monkeypatch.setattr(mod, "send_message_with_buttons", fake_btn, raising=False)
        monkeypatch.setattr(mod, "ban_member", fake_ban, raising=False)
        monkeypatch.setattr(mod, "unban_member", fake_unban, raising=False)
    return {"sent": sent, "kicked": kicked}


def _dm(phone, text):
    asyncio.run(h.process_message(chat_id=phone, sender=phone, text=text))


def _users():
    with db.db() as c:
        return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]


# ── Личка: незнакомцу вопрос, не ссылка ──────────────────────────────────────

def test_stranger_gets_the_question_not_a_link(test_db, world, wire):
    _dm(STRANGER, "Ассаляму алейкум, хочу учиться")
    assert len(wire["sent"]) == 1
    cid, text, buttons = wire["sent"][0]
    assert cid == STRANGER
    assert "брат или сестра" in text
    assert "t.me/+" not in text
    assert [b[1] for b in buttons] == ["side:male:777", "side:female:777"]


def test_answer_brother_gives_own_prep_link_and_is_remembered(test_db, world, wire):
    asyncio.run(side.handle_side_answer(STRANGER, "male"))
    assert wire["sent"][-1][0] == STRANGER
    assert "https://t.me/+MALEPREP" in wire["sent"][-1][1]
    assert side.known_side(STRANGER) == "male"
    # Второй раз вопроса нет - сразу ссылка
    wire["sent"].clear()
    _dm(STRANGER, "привет")
    assert len(wire["sent"]) == 1 and "https://t.me/+MALEPREP" in wire["sent"][0][1]
    assert wire["sent"][0][2] is None


def test_answer_sister_sends_to_the_neighbour_bot_not_his_group(test_db, world, wire):
    asyncio.run(side.handle_side_answer(STRANGER, "female"))
    cid, text, buttons = wire["sent"][-1]
    assert cid == STRANGER
    assert "женском джамаате" in text
    assert "https://t.me/yassir_female_bot?start=go" in text
    assert "t.me/+" not in text
    assert side.known_side(STRANGER) == "female"
    # и мужской бот дальше ведёт её к соседу, ссылку на свою prep не даёт
    wire["sent"].clear()
    _dm(STRANGER, "привет")
    assert "yassir_female_bot" in wire["sent"][0][1] and "t.me/+" not in wire["sent"][0][1]


def test_answer_is_shared_between_bots(test_db, world, wire, monkeypatch):
    """Ответ лежит в общей базе: сестра, ответившая мужскому боту, у
    женского уже опознана как своя."""
    asyncio.run(side.handle_side_answer(STRANGER, "female"))
    monkeypatch.setattr(config, "PROFILE", "female")
    assert side.known_side(STRANGER) == "female"


# ── Сестра, уже записанная в нашу подготовительную (пинг-понг) ──────────────

def test_misplaced_sister_is_removed_from_our_prep_before_going_to_neighbour(test_db, world, wire):
    prep_id = db.get_group(MALE_PREP_CHAT)["id"]
    assert db.find_by_phone(MISPLACED, prep_id) is not None
    asyncio.run(side.handle_side_answer(MISPLACED, "female", pressed_in=MALE_PREP_CHAT))
    assert (MALE_PREP_CHAT, MISPLACED) in wire["kicked"]
    assert db.get_learning_group(MISPLACED, include_prep=True) is None
    # ссылка на бота соседа ушла в личку (личка открыта - fake отвечает ok),
    # в группу ничего
    assert all(c != MALE_PREP_CHAT for c, _, _ in wire["sent"])
    assert "yassir_female_bot?start=go" in wire["sent"][-1][1]


def test_group_button_falls_back_to_the_group_when_dm_is_closed(test_db, world, wire, monkeypatch):
    """Личка закрыта (Start не нажимал): ссылку на БОТА соседа даём в самой
    группе - она безопасна публично, в отличие от ссылки на группу."""
    async def dm_fails(cid, text, **kw):
        wire["sent"].append((str(cid), text, None))
        return {"ok": False} if str(cid) == MISPLACED else {"ok": True}
    monkeypatch.setattr(side, "send_message", dm_fails)
    asyncio.run(side.handle_side_answer(MISPLACED, "female", pressed_in=MALE_PREP_CHAT))
    in_group = [t for c, t, _ in wire["sent"] if c == MALE_PREP_CHAT]
    assert len(in_group) == 1 and "yassir_female_bot?start=go" in in_group[0]
    assert "t.me/+" not in in_group[0]


# ── Сайт: отказ больше не тупик ──────────────────────────────────────────────

def test_site_refusal_offers_the_question_and_leaves_no_trace(test_db, world, wire):
    code = wa.new_login_code()
    before = _users()
    _dm(STRANGER, "/start " + wa.LOGIN_START_PREFIX + code)
    assert _users() == before
    assert wa.poll_login_code(code) == "refused"
    texts = [t for _, t, _ in wire["sent"]]
    assert any("не вижу тебя" in t for t in texts)
    assert wire["sent"][-1][2] is not None and "брат или сестра" in wire["sent"][-1][1]


# ── Штрафница соседа: видна, хоть и не активна ───────────────────────────────

def test_other_bot_penalty_sister_is_redirected_not_treated_as_stranger(test_db, world, wire):
    assert db.other_bot_member(SISTER_PENALTY) is False
    assert db.other_bot_known(SISTER_PENALTY) is True
    _dm(SISTER_PENALTY, "/start")
    assert len(wire["sent"]) == 1
    assert "женском джамаате" in wire["sent"][0][1]
    assert "t.me/+" not in wire["sent"][0][1]


def test_other_bot_prep_only_history_does_not_count_as_known(test_db, world):
    """Подготовительная соседа - не проверка устазом (Бурулсун сутки была
    активной студенткой мужской prep). Такая история половину не задаёт."""
    with sqlite3.connect(world["female_db"]) as c:
        c.execute("INSERT INTO users VALUES(3, 'Кто-то', '559')")
        c.execute("INSERT INTO user_groups VALUES(3, 7, 'student', 0)")
    assert db.other_bot_known("559") is False
    assert side.known_side("559") is None


# ── Рассылка «вернись» ───────────────────────────────────────────────────────

def _make_dropout(phone, name, via_group_chat):
    gid = db.get_group(via_group_chat)["id"]
    db.add_student(name, gid, phone=phone)
    db.mark_dm_ok_by_phone(phone)
    s = db.find_by_phone(phone, gid)
    db.deactivate_student(s["id"], gid)


def test_return_nudge_asks_when_side_unknown_and_links_when_ustaz_saw(test_db, world, wire):
    _make_dropout("601", "Ринат", MALE_PREP_CHAT)   # только prep - половина неизвестна
    _make_dropout("602", "Омар", N1_CHAT)           # был в учебной - устаз видел
    asyncio.run(tr.send_return_nudges())
    by = {c: (t, b) for c, t, b in wire["sent"]}
    assert "t.me/+" not in by["601"][0] and "брат или сестра" in by["601"][0]
    assert [b[1] for b in by["601"][1]] == ["side:male:601", "side:female:601"]
    assert "https://t.me/+MALEPREP" in by["602"][0] and by["602"][1] is None


def test_return_nudge_skips_neighbours_people(test_db, world, wire):
    _make_dropout("601", "Бурулсун", MALE_PREP_CHAT)
    side.remember_side("601", "female")              # ответила «я сестра»
    _make_dropout(SISTER_PENALTY, "Арзу", MALE_PREP_CHAT)   # штрафница сестёр со следом у нас
    asyncio.run(tr.send_return_nudges())
    assert all(c not in ("601", SISTER_PENALTY) for c, _, _ in wire["sent"])


# ── Активный студент пишет в подготовительной (Муса) ─────────────────────────

def test_active_student_message_in_prep_kicks_back_instead_of_transfer(test_db, world, wire):
    n1 = db.get_group(N1_CHAT)["id"]
    asyncio.run(h.process_message(chat_id=MALE_PREP_CHAT, sender=BROTHER, text="Ассаляму алейкум", sender_name="Сатар"))
    assert (MALE_PREP_CHAT, BROTHER) in wire["kicked"]
    assert (N1_CHAT, BROTHER) not in wire["kicked"]
    assert db.find_by_phone(BROTHER, n1) is not None
    assert db.get_learning_group(BROTHER)["id"] == n1
    assert db.find_by_phone(BROTHER, db.get_group(MALE_PREP_CHAT)["id"]) is None


# ── Приветствие на пороге подготовительной ───────────────────────────────────

def test_prep_greeting_names_the_half_and_offers_the_way_out(test_db, world, wire):
    g = db.get_group(MALE_PREP_CHAT)
    asyncio.run(tr.greet_new_member(MALE_PREP_CHAT, g, STRANGER, "Канат", "ru"))
    cid, text, buttons = wire["sent"][-1]
    assert cid == MALE_PREP_CHAT
    assert "подготовительная группа братьев" in text
    assert "Как тебя зовут" in text
    assert buttons == [("Я сестра, мне не сюда", "side:female:777")]
    assert "t.me" not in text


def test_learning_group_greeting_is_unchanged(test_db, world, wire):
    g = db.get_group(N1_CHAT)
    asyncio.run(tr.greet_new_member(N1_CHAT, g, STRANGER, "Канат", "ru"))
    cid, text, buttons = wire["sent"][-1]
    assert buttons is None and "братьев" not in text and "Как тебя зовут" in text


def test_prep_welcome_after_name_names_the_half_too(test_db, world, wire, monkeypatch):
    async def fake_link():
        return "https://t.me/yassirquranbot?start=go"
    monkeypatch.setattr(prep, "get_dm_start_link", fake_link)
    asyncio.run(prep.send_prep_onboarding_group_message(MALE_PREP_CHAT, "Канат", "ru", dm_ok=False, uid=STRANGER))
    cid, text, buttons = wire["sent"][-1]
    assert "подготовительную группу братьев" in text
    assert buttons == [("Я сестра, мне не сюда", "side:female:777")]


def test_female_bot_wording_is_mirrored(test_db, world, wire, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "female")
    assert side.half_word() == "сестёр"
    assert side.not_here_button("1")[0] == "Я брат, мне не сюда"
    assert side.not_here_button("1")[1] == "side:male:1"


# ── Устаз отмечает половину реплаем: /сестра, /брат, /нетуда ─────────────────

USTAZ = "31"


def _ustaz_reply(word, target, chat=MALE_PREP_CHAT, sender=USTAZ):
    asyncio.run(h.process_message(chat_id=chat, sender=sender, text=word, sender_name="Умар",
                                  reply_to_id=target, reply_to_message_id=5))


@pytest.fixture
def ustaz(world, monkeypatch):
    db.add_group_admin(db.get_group(MALE_PREP_CHAT)["id"], USTAZ)
    monkeypatch.setattr(side, "SUPER_ADMIN_IDS", ["1"])


def test_ustaz_sister_word_removes_and_tells_in_dm(test_db, world, wire, ustaz):
    db.mark_dm_ok_by_phone(MISPLACED)
    _ustaz_reply("/сестра", MISPLACED)
    assert (MALE_PREP_CHAT, MISPLACED) in wire["kicked"]
    assert side.known_side(MISPLACED) == "female"
    assert db.get_learning_group(MISPLACED, include_prep=True) is None
    dm = [t for c, t, _ in wire["sent"] if c == MISPLACED]
    assert len(dm) == 1 and "yassir_female_bot?start=go" in dm[0] and "Устаз подсказал" in dm[0]
    group = [t for c, t, _ in wire["sent"] if c == MALE_PREP_CHAT]
    assert len(group) == 1 and "снят" in group[0] and "Написал в личку" in group[0]
    assert any(c == "1" for c, _, _ in wire["sent"])     # супер-админу сказано


def test_ustaz_word_with_closed_dm_says_nothing_to_the_person(test_db, world, wire, ustaz):
    _ustaz_reply("/нетуда", MISPLACED)
    assert (MALE_PREP_CHAT, MISPLACED) in wire["kicked"]
    assert all(c != MISPLACED for c, _, _ in wire["sent"])
    group = [t for c, t, _ in wire["sent"] if c == MALE_PREP_CHAT]
    assert len(group) == 1 and "закрыта" in group[0]


def test_ustaz_brother_word_confirms_own_half_without_kick(test_db, world, wire, ustaz):
    _ustaz_reply("/брат", MISPLACED)
    assert wire["kicked"] == []
    assert side.known_side(MISPLACED) == "male"
    group = [t for c, t, _ in wire["sent"] if c == MALE_PREP_CHAT]
    assert len(group) == 1 and "половина своя" in group[0]


def test_ustaz_word_without_reply_explains(test_db, world, wire, ustaz):
    asyncio.run(h.process_message(chat_id=MALE_PREP_CHAT, sender=USTAZ, text="/сестра", sender_name="Умар"))
    assert wire["kicked"] == []
    assert "реплаем" in wire["sent"][-1][1]


def test_non_ustaz_cannot_use_the_word(test_db, world, wire, ustaz):
    """Не устаз (незнакомец в чате) пишет /сестра реплаем - слово не
    работает, адресата не трогаем. (Активный студент тут не годится: его
    самого выкинет prep-guard, и это правильно.)"""
    _ustaz_reply("/сестра", MISPLACED, sender=STRANGER)
    assert (MALE_PREP_CHAT, MISPLACED) not in wire["kicked"]
    assert side.known_side(MISPLACED) is None


def test_female_bot_words_are_mirrored(test_db, world, monkeypatch):
    monkeypatch.setattr(config, "PROFILE", "female")
    assert side.USTAZ_SIDE_WORDS["/брат"] == "male" != config.PROFILE      # чужой → снять
    assert side.USTAZ_SIDE_WORDS["/сестра"] == config.PROFILE               # свой → подтвердить
