"""Лента (11.09.2026) — что пишут в твоей группе, в Тадаббуре и тебе лично.

Зачем она: человек, который учится через YassirApp, всё равно вынужден был
уходить в Telegram, чтобы прочитать разбор устаза или насыху Тадаббура. Лента
приносит это внутрь приложения.

Чего лента НЕ делает — писать. Из приложения в группу не уходит ни одного
сообщения: отвечают по-прежнему в Telegram. Иначе пришлось бы вести половину
мессенджера (правки, удаления, реакции, пересылки), а разговор группы жил бы
в двух местах сразу.

Что здесь важно знать:

* **Хранение семь дней.** Это не архив переписки, а «что было на неделе»;
  держать чужие разговоры дольше незачем. Чистит `purge_feed` из scheduler.
* **Доступ считается на каждый запрос**, по членству в группе (`user_groups`),
  а не по тому, что прислал клиент. `chat_id` личной переписки равен
  telegram-id человека — на этом стоит проверка «это моя личка».
* **Служебные группы (`staff`) в ленту не пишутся вовсе** — рабочий чат
  устазов не место для показа студентам, и фильтровать его на чтении значило
  бы всё равно сложить его себе в базу.
* **Исходящие бот через getUpdates не получает** — свои сообщения он пишет в
  ленту сам, в момент отправки (см. четыре точки в `core/tg.py`).
"""
import logging

from core.db import db

log = logging.getLogger(__name__)

FEED_KEEP_DAYS = 7

# Имя, которым бот подписан в ленте. В Telegram у него своё имя, и подменять
# его на «бот» незачем — человек узнаёт отправителя по имени, как в чате.
BOT_SENDER_NAME = "Яссир"

# Виды вложений, которые лента показывает отдельной плашкой. Всё прочее
# сводится к "other" — плашка «вложение», текст подписи при этом сохраняется.
KIND_BY_FIELD = (
    ("voice", "voice"),
    ("photo", "photo"),
    ("video_note", "voice"),
    ("video", "video"),
    ("audio", "voice"),
    ("document", "document"),
)


def _kind_and_file(msg):
    """Вид сообщения и file_id самого крупного варианта (у фото Telegram
    присылает лесенку размеров, последний — самый большой)."""
    for field, kind in KIND_BY_FIELD:
        val = msg.get(field)
        if not val:
            continue
        if isinstance(val, list):          # photo: список размеров
            file_id = (val[-1] or {}).get("file_id")
        else:
            file_id = (val or {}).get("file_id")
        return kind, file_id
    return "text", None


def forget_chat_type(chat_id):
    """Забыть тип чата — зовётся из update_group_type после `/settype`."""
    _staff_cache.pop(str(chat_id), None)


def record(chat_id, text=None, sender_id=None, sender_name=None, is_bot=0,
           kind="text", file_id=None, message_id=None, reply_to_user=None):
    """Одна запись ленты. Ошибку глотаем: лента — вещь приятная, но не та,
    ради которой стоит уронить отправку сообщения или обработку апдейта."""
    try:
        with db() as c:
            c.execute("""
                INSERT INTO feed_messages(chat_id, message_id, sender_id, sender_name,
                                          is_bot, kind, text, file_id, reply_to_user)
                VALUES(?,?,?,?,?,?,?,?,?)
            """, (str(chat_id), message_id, sender_id, sender_name,
                  1 if is_bot else 0, kind, (text or "")[:4000], file_id, reply_to_user))
    except Exception as e:
        log.error("feed.record error: %s: %s", type(e).__name__, e)


_staff_cache = {}


def _is_staff_chat(chat_id):
    """Служебные группы в ленту не попадают (см. wiki/group_types).

    Запрос на каждое сообщение был бы лишним: в рассылке их сотни подряд.
    Личку узнаём по знаку (у групп chat_id отрицательный) и не спрашиваем
    базу вовсе, а тип группы держим в памяти - он меняется командой
    `/settype` раз в жизни группы, и переживать рестарт кэшу незачем."""
    cid = str(chat_id)
    if not cid.startswith("-"):
        return False
    if cid in _staff_cache:
        return _staff_cache[cid]
    try:
        with db() as c:
            row = c.execute("SELECT group_type FROM groups WHERE chat_id=?",
                            (cid,)).fetchone()
        val = bool(row) and row["group_type"] == "staff"
    except Exception:
        return False
    _staff_cache[cid] = val
    return val


def record_incoming(msg):
    """Сообщение человека из апдейта getUpdates.

    Берём весь `msg`, а не разобранные поля: обработчику бота нужны только
    текст и признак медиа, а ленте — ещё id сообщения, file_id вложения и на
    чьё сообщение отвечают."""
    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    chat_id = str(chat.get("id", ""))
    if not chat_id or _is_staff_chat(chat_id):
        return

    name = (frm.get("first_name", "") or "").strip()
    if frm.get("last_name"):
        name = (name + " " + frm["last_name"]).strip()
    if not name:
        name = frm.get("username") or "—"

    kind, file_id = _kind_and_file(msg)
    reply = ((msg.get("reply_to_message") or {}).get("from") or {}).get("id")

    record(chat_id,
           text=msg.get("text") or msg.get("caption") or "",
           sender_id=str(frm.get("id", "")),
           sender_name=name,
           is_bot=0,
           kind=kind,
           file_id=file_id,
           message_id=msg.get("message_id"),
           reply_to_user=str(reply) if reply else None)


def record_outgoing(chat_id, result=None, text=None, kind="text", file_id=None,
                    reply_to_user=None):
    """Своё отправленное сообщение. Зовётся из четырёх нижних отправщиков
    core/tg.py — выше них одиннадцать `send_*`, и перехватывать каждую значило
    бы забыть следующую.

    `result` — ответ Telegram: из него берём message_id, а для фото и голоса
    ещё и file_id, который Telegram присваивает уже после загрузки."""
    if not chat_id or _is_staff_chat(chat_id):
        return
    res = (result or {}).get("result") or {}
    if not file_id:
        if res.get("voice"):
            file_id = (res["voice"] or {}).get("file_id")
        elif res.get("photo"):
            file_id = (res["photo"][-1] or {}).get("file_id")
    record(chat_id,
           text=text or res.get("text") or res.get("caption") or "",
           sender_id=None,
           sender_name=BOT_SENDER_NAME,
           is_bot=1,
           kind=kind,
           file_id=file_id,
           message_id=res.get("message_id"),
           reply_to_user=reply_to_user)


# ── кому что видно ────────────────────────────────────────────────────────

def feed_chats_for(phone):
    """Чаты, которые человек вправе читать: его группы (любая роль, активное
    членство) кроме служебных — и его личная переписка с ботом.

    Роль не сужаем: устаз читает ленту своей группы на тех же правах, что и
    студент, а Тадаббур попадает сюда сам, если человек в нём состоит."""
    chats = [str(phone)]        # личка: chat_id личной переписки == telegram id
    try:
        with db() as c:
            rows = c.execute("""
                SELECT g.chat_id FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                JOIN groups g ON ug.group_id=g.id
                WHERE u.phone=? AND ug.active=1 AND g.active=1
                  AND (g.group_type IS NULL OR g.group_type <> 'staff')
            """, (str(phone),)).fetchall()
        chats += [r["chat_id"] for r in rows if r["chat_id"]]
    except Exception as e:
        log.error("feed_chats_for error: %s: %s", type(e).__name__, e)
    return list(dict.fromkeys(chats))


def _chat_titles(chats):
    """Подпись источника у каждой строки ленты. Для лички подписи нет —
    «личное» ставит уже экран, названия чата у неё не существует."""
    if not chats:
        return {}
    q = ",".join("?" * len(chats))
    with db() as c:
        rows = c.execute(f"SELECT chat_id, title FROM groups WHERE chat_id IN ({q})",
                         chats).fetchall()
    return {r["chat_id"]: r["title"] for r in rows}


def last_read_id(phone):
    with db() as c:
        row = c.execute("SELECT last_id FROM feed_reads WHERE user_id=?",
                        (str(phone),)).fetchone()
    return row["last_id"] if row else 0


def mark_read(phone, last_id):
    """Докуда дочитано. Только вперёд: экран шлёт id самого свежего, что
    показал, и повторный заход со старым числом не должен «разчитывать»."""
    try:
        with db() as c:
            c.execute("""
                INSERT INTO feed_reads(user_id, last_id) VALUES(?,?)
                ON CONFLICT(user_id) DO UPDATE
                   SET last_id=MAX(last_id, excluded.last_id),
                       updated_at=datetime('now')
            """, (str(phone), int(last_id)))
    except Exception as e:
        log.error("mark_read error: %s: %s", type(e).__name__, e)


def _row_out(r, titles, me):
    return {
        "id": r["id"],
        "chat_id": r["chat_id"],
        "source": titles.get(r["chat_id"]) or ("личное" if r["chat_id"] == me else ""),
        "who": r["sender_name"] or "—",
        "is_bot": bool(r["is_bot"]),
        "kind": r["kind"],
        "text": r["text"] or "",
        "has_media": bool(r["file_id"]),
        "mine": r["sender_id"] == me,
        "at": r["created_at"],
    }


def list_feed(phone, limit=200):
    """Лента человека, свежие сверху. Ограничение по числу, а не по дням:
    старое и так вычищено ретеншеном."""
    me = str(phone)
    chats = feed_chats_for(me)
    if not chats:
        return []
    q = ",".join("?" * len(chats))
    with db() as c:
        rows = c.execute(f"""
            SELECT * FROM feed_messages
            WHERE chat_id IN ({q})
            ORDER BY id DESC LIMIT ?
        """, (*chats, int(limit))).fetchall()
    titles = _chat_titles(chats)
    return [_row_out(r, titles, me) for r in rows]


def brief(phone):
    """Строка ленты для дашборда: что показать и сколько непрочитанного.

    Показываем НЕ самое свежее, а самое важное непрочитанное (решение
    11.09.2026). В группе за день набегает полсотни «м р т», и строка,
    набранная по времени, почти всегда занята чужой отметкой, а разбор устаза
    остаётся под ней невидимым.

    Порядок: адресованное тебе → сообщение бота (насыха, задания) → самое
    свежее. Если непрочитанного нет — последнее в ленте, без счётчика.

    Счётчик — только адресованное тебе; на остальное новое отдаётся `more`, и
    экран рисует его точкой. Считать всё подряд нельзя: в группе из двадцати
    человек цифра не обнулялась бы никогда и превратилась бы в несбрасываемый
    долг на экране, а красное в этом приложении означает именно долг."""
    me = str(phone)
    chats = feed_chats_for(me)
    if not chats:
        return None
    q = ",".join("?" * len(chats))
    seen = last_read_id(me)

    with db() as c:
        rows = c.execute(f"""
            SELECT * FROM feed_messages
            WHERE chat_id IN ({q}) AND id > ?
            ORDER BY id DESC LIMIT 200
        """, (*chats, seen)).fetchall()

        latest = None
        if not rows:
            latest = c.execute(f"""
                SELECT * FROM feed_messages WHERE chat_id IN ({q})
                ORDER BY id DESC LIMIT 1
            """, chats).fetchone()

    titles = _chat_titles(chats)
    if not rows:
        if not latest:
            return None
        out = _row_out(latest, titles, me)
        return {"item": out, "unread": 0, "more": False, "top_id": latest["id"]}

    # Адресовано тебе: ответили на твоё сообщение или бот написал в личку.
    mine = [r for r in rows
            if r["reply_to_user"] == me or (r["is_bot"] and r["chat_id"] == me)]
    # Свои же сообщения непрочитанными не считаем.
    others = [r for r in rows if r["sender_id"] != me]

    # Внутри адресованного человек важнее бота: разбор устаза по твоей сдаче
    # ждёт ответа, а ежедневная насыха просто свежее по времени и иначе
    # вытесняла бы его из строки каждое утро.
    people = [r for r in mine if not r["is_bot"]]
    pick = (people or mine)[0] if mine else next(
        (r for r in others if r["is_bot"]), others[0] if others else rows[0])
    return {
        "item": _row_out(pick, titles, me),
        "unread": len(mine),
        "more": bool([r for r in others if r not in mine]),
        "top_id": rows[0]["id"],
    }


def my_group_link(phone):
    """Ссылка-приглашение своей учебной группы — для кнопки «Открыть группу»
    в подвале ленты. Отвечают по-прежнему в Telegram, и путь туда должен быть
    в один тап.

    Ссылка есть не у каждой группы (`groups.invite_link` заполняется, когда
    устаз её присылает) — тогда кнопки просто нет, остаётся фраза."""
    try:
        with db() as c:
            row = c.execute("""
                SELECT g.invite_link FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                JOIN groups g ON ug.group_id=g.id
                WHERE u.phone=? AND ug.role='student' AND ug.active=1
                  AND g.invite_link IS NOT NULL AND g.invite_link <> ''
                LIMIT 1
            """, (str(phone),)).fetchone()
        return row["invite_link"] if row else None
    except Exception as e:
        log.error("my_group_link error: %s: %s", type(e).__name__, e)
        return None


def get_media(phone, feed_id):
    """file_id вложения — по номеру записи ленты, а НЕ по file_id с клиента.

    Разница принципиальная: file_id в Telegram — это ключ к файлу, и приняв
    его от клиента, мы отдавали бы любой файл любому, кто этот ключ где-то
    подобрал. По номеру записи доступ проверяется тем же правилом, что и вся
    лента: сообщение должно лежать в чате, где человек состоит."""
    me = str(phone)
    chats = feed_chats_for(me)
    if not chats:
        return None, None
    q = ",".join("?" * len(chats))
    with db() as c:
        row = c.execute(f"""
            SELECT file_id, kind FROM feed_messages
            WHERE id=? AND chat_id IN ({q})
        """, (int(feed_id), *chats)).fetchone()
    if not row or not row["file_id"]:
        return None, None
    return row["file_id"], row["kind"]


def purge_feed(days=FEED_KEEP_DAYS):
    """Ретеншен. Зовётся раз в сутки из scheduler."""
    try:
        with db() as c:
            cur = c.execute(
                "DELETE FROM feed_messages WHERE created_at < datetime('now', ?)",
                ("-%d days" % int(days),))
            return cur.rowcount
    except Exception as e:
        log.error("purge_feed error: %s: %s", type(e).__name__, e)
        return 0
