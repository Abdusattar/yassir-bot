"""Лента: кому что видно и что попадает в строку дашборда (11.09.2026).

Две вещи, ради которых тесты здесь и нужны:

* **доступ** — лента отдаётся по членству в группах, а не по тому, что
  попросил клиент. Сюда же служебные группы, которые не пишутся вовсе, и
  вложения, доступные по номеру записи, а не по подобранному file_id;
* **выбор строки для дашборда** — она показывает не самое свежее, а самое
  важное непрочитанное, и считает только адресованное тебе. Это решение
  принято против группового шума (см. docstring `brief`), и молча съехать
  обратно на «последнее по времени» оно не должно.
"""
import core.db as db
from core.feed import (
    brief, feed_chats_for, get_media, list_feed, mark_read, purge_feed,
    record, record_incoming,
)


MY_CHAT = "-100777001"      # своя учебная группа
OTHER_CHAT = "-100777002"   # чужая группа
STAFF_CHAT = "-100777003"   # рабочий чат устазов
ME = "555001"
FRIEND = "555002"


def _setup():
    db.save_group(MY_CHAT, "N-2а", tasks="m,r,t")
    db.save_group(OTHER_CHAT, "N-5", tasks="m,r,t")
    db.save_group(STAFF_CHAT, "Устазат", tasks="m,r,t")
    db.update_group_type(STAFF_CHAT, "staff")
    mine = db.get_group(MY_CHAT)
    other = db.get_group(OTHER_CHAT)
    db.add_student("Сатар", mine["id"], phone=ME)
    db.add_student("Абдулла", mine["id"], phone=FRIEND)
    db.add_student("Талас", other["id"], phone="555003")
    return mine, other


# ── доступ ────────────────────────────────────────────────────────────────

def test_вижу_свою_группу_и_свою_личку(test_db):
    _setup()

    chats = feed_chats_for(ME)

    assert ME in chats           # личка: chat_id личной переписки == telegram id
    assert MY_CHAT in chats
    assert OTHER_CHAT not in chats


def test_служебная_группа_не_видна_никому(test_db):
    _setup()
    db.add_student("Сатар-устаз", db.get_group(STAFF_CHAT)["id"], phone=ME)

    assert STAFF_CHAT not in feed_chats_for(ME)


def test_чужая_группа_в_ленту_не_попадает(test_db):
    _setup()
    record(MY_CHAT, text="наше", sender_id=FRIEND, sender_name="Абдулла")
    record(OTHER_CHAT, text="чужое", sender_id="555003", sender_name="Талас")

    texts = [i["text"] for i in list_feed(ME)]

    assert "наше" in texts
    assert "чужое" not in texts


def test_личка_чужого_человека_не_видна(test_db):
    _setup()
    record(FRIEND, text="личное сообщение Абдулле", is_bot=1, sender_name="Яссир")

    assert [i["text"] for i in list_feed(ME)] == []


def test_служебная_группа_не_пишется_вовсе(test_db):
    """Не «не показываем», а не кладём к себе: чужой рабочий чат незачем
    держать в своей базе даже скрытым."""
    _setup()
    record_incoming({
        "message_id": 7, "chat": {"id": STAFF_CHAT},
        "from": {"id": FRIEND, "first_name": "Абдулла"}, "text": "рабочее",
    })

    with db.db() as c:
        rows = c.execute("SELECT * FROM feed_messages").fetchall()
    assert rows == []


def test_вложение_чужой_группы_не_отдаётся(test_db):
    """Номер записи подобрать легко — проверка доступа висит не на нём."""
    _setup()
    record(OTHER_CHAT, kind="photo", file_id="AgACc", sender_id="555003",
           sender_name="Талас")
    with db.db() as c:
        alien = c.execute("SELECT id FROM feed_messages").fetchone()["id"]

    assert get_media(ME, alien) == (None, None)


def test_вложение_своей_группы_отдаётся(test_db):
    _setup()
    record(MY_CHAT, kind="voice", file_id="AwACv", sender_id=FRIEND,
           sender_name="Абдулла")
    with db.db() as c:
        own = c.execute("SELECT id FROM feed_messages").fetchone()["id"]

    assert get_media(ME, own) == ("AwACv", "voice")


# ── разбор входящего ──────────────────────────────────────────────────────

def test_из_апдейта_берём_вложение_и_ответ(test_db):
    """У фото Telegram присылает лесенку размеров — нужен самый крупный."""
    _setup()
    record_incoming({
        "message_id": 12, "chat": {"id": MY_CHAT},
        "from": {"id": FRIEND, "first_name": "Абдулла", "last_name": "Т."},
        "caption": "страница 7",
        "photo": [{"file_id": "small"}, {"file_id": "big"}],
        "reply_to_message": {"from": {"id": ME}},
    })

    with db.db() as c:
        row = c.execute("SELECT * FROM feed_messages").fetchone()
    assert row["kind"] == "photo"
    assert row["file_id"] == "big"
    assert row["sender_name"] == "Абдулла Т."
    assert row["reply_to_user"] == ME


# ── строка дашборда ───────────────────────────────────────────────────────

def test_в_строку_идёт_адресованное_мне_а_не_последнее(test_db):
    """Главное решение 11.09.2026: в группе льётся «м р т», и строка,
    набранная по времени, почти всегда занята чужой отметкой."""
    _setup()
    record(MY_CHAT, text="МашаАллах, приняли", sender_id="555009",
           sender_name="Умар устаз", reply_to_user=ME)
    record(MY_CHAT, text="м р т", sender_id=FRIEND, sender_name="Абдулла")

    b = brief(ME)

    assert b["item"]["who"] == "Умар устаз"
    assert b["unread"] == 1          # считаем только адресованное мне
    assert b["more"] is True         # остальное новое — точкой


def test_разбор_устаза_важнее_свежей_насыхи(test_db):
    """Оба адресованы мне, но насыха приходит каждое утро и иначе вытесняла
    бы разбор из строки — а ответа ждёт как раз разбор."""
    _setup()
    record(MY_CHAT, text="приняли, дальше 7 страница", sender_id="555009",
           sender_name="Умар устаз", reply_to_user=ME)
    record(ME, text="Он видит тебя прямо сейчас", is_bot=1, sender_name="Яссир")

    b = brief(ME)

    assert b["item"]["who"] == "Умар устаз"
    assert b["unread"] == 2


def test_групповой_шум_не_идёт_в_счётчик(test_db):
    """Иначе цифра не обнулялась бы никогда и стала бы вечным долгом."""
    _setup()
    for _ in range(20):
        record(MY_CHAT, text="м р т", sender_id=FRIEND, sender_name="Абдулла")

    b = brief(ME)

    assert b["unread"] == 0
    assert b["more"] is True


def test_личное_от_бота_считается_адресованным(test_db):
    _setup()
    record(ME, text="Задания на сегодня", is_bot=1, sender_name="Яссир")

    b = brief(ME)

    assert b["unread"] == 1
    assert b["item"]["source"] == "личное"


def test_свои_сообщения_себе_в_непрочитанное_не_идут(test_db):
    _setup()
    record(MY_CHAT, text="м р т", sender_id=ME, sender_name="Сатар")

    b = brief(ME)

    assert b["unread"] == 0
    assert b["more"] is False


def test_после_прочтения_счётчик_гаснет(test_db):
    _setup()
    record(MY_CHAT, text="приняли", sender_id="555009", sender_name="Умар устаз",
           reply_to_user=ME)

    b = brief(ME)
    mark_read(ME, b["top_id"])
    after = brief(ME)

    assert after["unread"] == 0
    assert after["more"] is False
    assert after["item"]["text"] == "приняли"   # строка не пустеет


def test_отметка_прочтения_двигается_только_вперёд(test_db):
    _setup()
    record(MY_CHAT, text="раз", sender_id=FRIEND, sender_name="Абдулла")
    record(MY_CHAT, text="два", sender_id=FRIEND, sender_name="Абдулла")

    mark_read(ME, 2)
    mark_read(ME, 1)

    from core.feed import last_read_id
    assert last_read_id(ME) == 2


def test_ленты_нет_пока_ничего_не_написано(test_db):
    _setup()

    assert brief(ME) is None


# ── ретеншен ──────────────────────────────────────────────────────────────

def test_старое_удаляется_через_семь_дней(test_db):
    _setup()
    record(MY_CHAT, text="свежее", sender_id=FRIEND, sender_name="Абдулла")
    record(MY_CHAT, text="старое", sender_id=FRIEND, sender_name="Абдулла")
    with db.db() as c:
        c.execute("UPDATE feed_messages SET created_at=datetime('now','-8 days') "
                  "WHERE text='старое'")

    purge_feed()

    assert [i["text"] for i in list_feed(ME)] == ["свежее"]
