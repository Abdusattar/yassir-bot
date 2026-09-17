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
import contextvars
import logging
import re
from contextlib import contextmanager
from datetime import date, timedelta

from config import SUPER_ADMIN_IDS
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


# ── Важные сообщения (17.09.2026) ────────────────────────────────────────────
#
# В ленте всё равно: отметки «м р т», насыха и «открылся урок» стоят в одном
# ряду, и важное тонет. Типов важного мало НАРОЧНО (решение пользователя):
# подсветка работает, пока она редкая. Насыху, рейтинги, итоги недели и
# «открылся навык» сюда не добавлять.
#
#   lesson   - открылся урок (всей группе), висит, пока не открыл
#   kick     - предупреждение: пропуски, нет имени (личное)
#   announce - объявление, которое шлём сами (переход на YassirApp)
#   retake   - устаз просит перезаписать сдачу (личное)
#   transfer - перевод в другую группу (личное)
#   task     - у группы появляется новое задание (таджвид, нахв)
#
# Живут на ДОСКЕ дашборда - отдельно от строки чата (решение пользователя
# 17.09.2026): бот пишет и в группу, и в личку, строка чата показывает
# последнее, а важное должно повисеть. Личное и урок уходят, когда человек
# открыл. Объявление и новое задание (STICKY) висят до своей даты `until` -
# после прочтения остаются спокойными, без свечения.
#
# Пометка ставится ТАМ, ГДЕ бот отправляет, а не угадывается по тексту:
#
#     with feed.important("lesson", link="lesson:n:12", title="Нахв: ..."):
#         await send_message(chat_id, text)
#
# Отправщиков в core/tg.py одиннадцать, и тянуть параметр через каждый значило
# бы забыть следующий - поэтому contextvar: record_outgoing читает его сам.
# `to` - кому адресовано, если сообщение идёт в группу: остальным не покажем.
NOTICE_TYPES = ("lesson", "kick", "announce", "retake", "transfer", "task")
STICKY_TYPES = ("announce", "task")
STICKY_DAYS = 2           # сколько висит объявление, если дата не названа
BOARD_MAX = 3
_notice = contextvars.ContextVar("feed_notice", default=None)


@contextmanager
def important(ntype, link=None, title=None, to=None, until=None):
    """until - дата ISO, до которой (включительно) висит объявление."""
    if ntype not in NOTICE_TYPES:
        raise ValueError("bad notice type: %s" % ntype)
    if ntype in STICKY_TYPES and not until:
        from core.db import get_date
        until = (date.fromisoformat(get_date()) + timedelta(days=STICKY_DAYS)).isoformat()
    token = _notice.set({"type": ntype, "link": link, "title": title,
                         "to": str(to) if to else None, "until": until})
    try:
        yield
    finally:
        _notice.reset(token)


def _notice_key(row):
    """Одно важное на ключ: урок - свой у каждого урока, у остальных - по
    типу. Предупреждение о пропусках приходит каждый день, длинный урок уходит
    несколькими сообщениями, вердикт - и в группу, и в личку: карточка одна."""
    return row["notice"] + "|" + (row["notice_link"] or "")


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
           kind="text", file_id=None, message_id=None, reply_to_user=None, notice=None):
    """Одна запись ленты. Ошибку глотаем: лента — вещь приятная, но не та,
    ради которой стоит уронить отправку сообщения или обработку апдейта."""
    try:
        with db() as c:
            c.execute("""
                INSERT INTO feed_messages(chat_id, message_id, sender_id, sender_name,
                                          is_bot, kind, text, file_id, reply_to_user,
                                          notice, notice_link, notice_title, notice_until)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (str(chat_id), message_id, sender_id, sender_name,
                  1 if is_bot else 0, kind, (text or "")[:4000], file_id, reply_to_user,
                  (notice or {}).get("type"), (notice or {}).get("link"), (notice or {}).get("title"),
                  (notice or {}).get("until")))
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


_tadabbur_cache = {}


def _is_tadabbur_chat(chat_id):
    cid = str(chat_id)
    if not cid.startswith("-"):
        return False
    if cid in _tadabbur_cache:
        return _tadabbur_cache[cid]
    try:
        with db() as c:
            row = c.execute("SELECT group_type FROM groups WHERE chat_id=?",
                            (cid,)).fetchone()
        val = bool(row) and row["group_type"] == "tadabbur"
    except Exception:
        return False
    _tadabbur_cache[cid] = val
    return val


def skip_in_feed(chat_id, sender_id, is_bot=False):
    """В Тадаббуре лента показывает только бота и супер-устазов (решение
    10.09.2026).

    Тадаббур — самая большая группа в базе (134 человека на 11.09.2026), и
    он не учебный: там пространство смыслов, а не отчёты. Пусти в ленту всех
    подряд — один разговорившийся вечер затопит ленту каждому, у кого она
    открыта, и разбор устаза утонет. Насыха и слово супер-устаза остаются."""
    if not _is_tadabbur_chat(chat_id):
        return False
    if is_bot:
        return False
    return str(sender_id or "") not in SUPER_ADMIN_IDS


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

    if skip_in_feed(chat_id, frm.get("id")):
        return

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
    notice = _notice.get()
    if notice and notice["to"] and not reply_to_user:
        reply_to_user = notice["to"]
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
           reply_to_user=reply_to_user,
           notice=notice)


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


def feed_chats_detailed(phone):
    """Чаты для чипов на экране ленты — с названием, видом и порядком.

    Порядок задан пользователем 11.09.2026: личное, общая (Тадаббур), своя
    учебная, дальше группы, где человек устаз. Личное первым потому, что там
    самое адресное — задания, насыха, ответ по твоей сдаче.

    Вкладки «Всё» нет намеренно: это единственный режим, где четыре группы
    смешиваются в один поток, то есть ровно та каша, от которой чипы и
    заводились. Найти новое помогают счётчики на самих чипах, а лента
    открывается сразу на том чате, откуда сообщение в строке дашборда.

    «Общая» — подпись Тадаббура в приложении (решение пользователя): для
    человека это общая группа, а не отдельное учреждение."""
    me = str(phone)
    out = [{"id": me, "title": "Яссир бот", "kind": "personal"}]
    try:
        with db() as c:
            rows = c.execute("""
                SELECT g.chat_id, g.title, COALESCE(g.group_type,'relaxed') gt, ug.role
                FROM users u
                JOIN user_groups ug ON u.id=ug.user_id
                JOIN groups g ON ug.group_id=g.id
                WHERE u.phone=? AND ug.active=1 AND g.active=1
                  AND (g.group_type IS NULL OR g.group_type <> 'staff')
            """, (me,)).fetchall()
    except Exception as e:
        log.error("feed_chats_detailed error: %s: %s", type(e).__name__, e)
        return out

    common, study, teaching = [], [], []
    for r in rows:
        if r["gt"] == "tadabbur":
            common.append({"id": r["chat_id"], "title": "Общая", "kind": "common"})
        elif r["role"] == "admin":
            teaching.append({"id": r["chat_id"], "title": r["title"] or "Группа",
                             "kind": "teaching"})
        else:
            study.append({"id": r["chat_id"], "title": r["title"] or "Группа",
                          "kind": "study"})
    # Человек может стоять в группе и студентом, и устазом - показываем один
    # раз, учебная важнее (там он сдаёт, а не принимает).
    seen = {c["id"] for c in study}
    teaching = [c for c in teaching if c["id"] not in seen]
    return out + common + study + teaching


def _chat_titles(chats):
    """Подпись источника у каждой строки ленты. Для лички подписи нет —
    «личное» ставит уже экран, названия чата у неё не существует."""
    if not chats:
        return {}
    q = ",".join("?" * len(chats))
    with db() as c:
        rows = c.execute(
            f"SELECT chat_id, title, group_type FROM groups WHERE chat_id IN ({q})",
            chats).fetchall()
    # Тадаббур подписан «Общая» и здесь тоже - иначе чип говорит одно, а
    # рамка у сообщения другое.
    return {r["chat_id"]: ("Общая" if r["group_type"] == "tadabbur" else r["title"])
            for r in rows}


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


def _has_open_retake(me):
    """Висит ли на человеке пересдача. Плашки «пересдать» в мусхафе больше нет
    (17.09.2026), поэтому строка на доске держится до самой пересдачи."""
    try:
        from core.db import find_user_by_phone, get_learning_group, get_open_retakes
        user = find_user_by_phone(me)
        group = get_learning_group(me, include_prep=True)
        return bool(user and group and get_open_retakes(user["id"], group["id"]))
    except Exception as e:
        log.error("_has_open_retake error: %s: %s", type(e).__name__, e)
        return False


def open_notices(phone, chats=None):
    """[(строка, прочитано)] - доска человека: по одному на ключ, свежее
    первым. Неоткрытое - всё; открытое - только объявления до их даты.
    Адресованное другому (reply_to_user) не показываем."""
    from core.db import get_date
    today = get_date()
    me = str(phone)
    chats = chats if chats is not None else feed_chats_for(me)
    if not chats:
        return []
    q = ",".join("?" * len(chats))
    with db() as c:
        rows = c.execute(f"""
            SELECT * FROM feed_messages
            WHERE notice IS NOT NULL AND chat_id IN ({q})
              AND (reply_to_user IS NULL OR reply_to_user = ? OR chat_id = ?)
            ORDER BY id DESC LIMIT 100
        """, (*chats, me, me)).fetchall()
        seen = {r["nkey"]: r["last_id"] for r in c.execute(
            "SELECT nkey, last_id FROM feed_notice_seen WHERE user_id=?", (me,)).fetchall()}
    out, taken = [], set()
    for r in rows:
        key = _notice_key(r)
        if key in taken:
            continue
        taken.add(key)                       # старое того же ключа не поднимаем
        if r["notice_until"] and r["notice_until"] < today:
            continue
        read = r["id"] <= seen.get(key, 0)
        if r["notice"] == "retake":
            # Пока не пересдал - висит (после открытия спокойная); пересдал -
            # уходит, даже если не открывал.
            if not _has_open_retake(me):
                continue
        elif read and not (r["notice"] in STICKY_TYPES and r["notice_until"]):
            continue
        out.append((r, read))
    out.sort(key=lambda x: x[1])             # непрочитанное выше
    return out


def mark_notice_seen(phone, feed_id=None, key=None):
    """Открыл важное - карточка уходит. По id сообщения (тап по карточке)
    или по ключу (открыл сам урок через «Знания»)."""
    me = str(phone)
    try:
        with db() as c:
            if feed_id is not None:
                row = c.execute("SELECT * FROM feed_messages WHERE id=? AND notice IS NOT NULL",
                                (int(feed_id),)).fetchone()
                if not row:
                    return
                key = _notice_key(row)
            top = c.execute("SELECT MAX(id) m FROM feed_messages").fetchone()["m"] or 0
            c.execute("""
                INSERT INTO feed_notice_seen(user_id, nkey, last_id) VALUES(?,?,?)
                ON CONFLICT(user_id, nkey) DO UPDATE SET last_id=MAX(last_id, excluded.last_id)
            """, (me, key, top))
    except Exception as e:
        log.error("mark_notice_seen error: %s: %s", type(e).__name__, e)


def _notice_out(rows, titles):
    out = []
    for r, read in rows[:BOARD_MAX]:
        # Значок типа рисует доска - свой эмодзи из начала текста убираем.
        text = r["notice_title"] or re.sub(r"^\W+", "", (r["text"] or "").strip().split("\n")[0])
        out.append({"id": r["id"], "type": r["notice"], "link": r["notice_link"] or "",
                    "text": text, "chat_id": r["chat_id"], "read": read,
                    "source": titles.get(r["chat_id"]) or ""})
    return out


def _row_out(r, titles, me):
    return {
        "id": r["id"],
        "chat_id": r["chat_id"],
        "source": titles.get(r["chat_id"]) or "",
        "who": r["sender_name"] or "—",
        "is_bot": bool(r["is_bot"]),
        "kind": r["kind"],
        "text": r["text"] or "",
        "has_media": bool(r["file_id"]),
        "mine": r["sender_id"] == me,
        "at": r["created_at"],
    }


def unread_by_chat(phone):
    """Сколько адресованного тебе не прочитано в каждом чате — числа на
    чипах. Правило то же, что у строки дашборда: считаем ответ на твоё
    сообщение и личное от бота, а не всё подряд."""
    me = str(phone)
    chats = feed_chats_for(me)
    if not chats:
        return {}
    q = ",".join("?" * len(chats))
    seen = last_read_id(me)
    with db() as c:
        rows = c.execute(f"""
            SELECT chat_id, count(*) n FROM feed_messages
            WHERE chat_id IN ({q}) AND id > ?
              AND (reply_to_user = ? OR (is_bot = 1 AND chat_id = ?))
            GROUP BY chat_id
        """, (*chats, seen, me, me)).fetchall()
    return {r["chat_id"]: r["n"] for r in rows}


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
    notices = _notice_out(open_notices(me, chats), titles)
    if not rows:
        if not latest:
            return None
        out = _row_out(latest, titles, me)
        return {"item": out, "unread": 0, "more": False, "top_id": latest["id"], "notices": notices}

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
        "notices": notices,
    }


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
