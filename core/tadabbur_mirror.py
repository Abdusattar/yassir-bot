"""Дубль объявлений Тадаббура сёстрам (23.09.2026).

Зачем. Объявления об изменениях пользователь пишет в общую мужскую группу
Тадаббур, а в женскую приходилось переписывать руками. Теперь каждое его
сообщение там, кроме ответов на чужие (решение пользователя: реплай - это
разговор с братьями, а не объявление), само уходит в женский Тадаббур от
имени женского бота. Текст - как есть, без замены «братья» на «сёстры»:
пользователь пишет объявления нейтрально, а автозамена исказила бы текст.
Правки и удаления не повторяются: дубль уходит один раз.

Как. Женский бот в мужской группе не состоит и сообщения не видит, а чужой
file_id ему не годится (file_id привязан к боту). Поэтому мужской процесс
сам скачивает вложение в общую папку и кладёт запись в очередь в ОБЩЕЙ
базе sources/hadiths.db (как банк насых и bot_registry), а женский раз в
несколько секунд забирает очередь, загружает файл заново и шлёт в свой
Тадаббур. Токен соседа ни одному процессу не нужен.

Разово переслать уже прошедшее сообщение - scripts/tadabbur_mirror_push.py.
"""
import asyncio
import json
from datetime import datetime
import logging
import os
import sqlite3
import uuid

import aiohttp

import config
import core.sampler as sampler   # путь читаем через модуль: тесты подменяют его там
from core.db import get_now, get_tadabbur_group
from core.feed import record_outgoing

log = logging.getLogger(__name__)

# Вид вложения -> (метод отправки, поле файла, вид для ленты). Подпись есть у
# всех, кроме кружка. Стикеры, опросы и прочее не дублируем.
MEDIA = {
    "photo": ("sendPhoto", "photo", "photo"),
    "video": ("sendVideo", "video", "video"),
    "animation": ("sendAnimation", "animation", "video"),
    "document": ("sendDocument", "document", "document"),
    "voice": ("sendVoice", "voice", "voice"),
    "audio": ("sendAudio", "audio", "voice"),
    "video_note": ("sendVideoNote", "video_note", "voice"),
}
# Порядок важен: у гифки Telegram кладёт и animation, и document.
_MEDIA_ORDER = ("photo", "video", "animation", "voice", "audio", "video_note", "document")

POLL_SECONDS = 5
MAX_ATTEMPTS = 3
# Если женский бот лежал дольше - старое объявление не всплывает посреди
# другого разговора.
STALE_HOURS = 24


def _dir():
    return os.path.join(os.path.dirname(str(sampler.HADITHS_DB)), "tadabbur_mirror")


def _connect():
    c = sqlite3.connect(str(sampler.HADITHS_DB), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS tadabbur_mirror(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            src_message_id INTEGER UNIQUE,
            kind TEXT NOT NULL,
            text TEXT,
            entities TEXT,
            file_path TEXT,
            file_name TEXT,
            created_at TEXT NOT NULL,
            sent_at TEXT,
            attempts INTEGER NOT NULL DEFAULT 0,
            error TEXT
        )
    """)
    return c


def _media_of(msg):
    """(вид, file_id, имя файла) или (None, None, None) для текста."""
    for kind in _MEDIA_ORDER:
        val = msg.get(kind)
        if not val:
            continue
        if isinstance(val, list):          # photo: список размеров, берём крупный
            val = val[-1] or {}
        return kind, val.get("file_id"), val.get("file_name")
    return None, None, None


def should_mirror(msg):
    """Мужской Тадаббур, пишет суперадмин, не ответ на чужое сообщение."""
    if config.PROFILE != "male":
        return False
    frm = msg.get("from") or {}
    if str(frm.get("id", "")) not in config.SUPER_ADMIN_IDS:
        return False
    tad = get_tadabbur_group()
    if not tad or str((msg.get("chat") or {}).get("id", "")) != str(tad["chat_id"]):
        return False
    if msg.get("reply_to_message"):
        return False
    kind, _, _ = _media_of(msg)
    if kind:
        return True
    return bool((msg.get("text") or "").strip())


async def _download(file_id):
    api = config.TG_API
    async with aiohttp.ClientSession() as s:
        async with s.get(api + "/getFile", params={"file_id": file_id}) as r:
            meta = await r.json()
        path = (meta.get("result") or {}).get("file_path")
        if not meta.get("ok") or not path:
            raise RuntimeError("getFile: %s" % meta.get("description", meta))
        url = api.replace("/bot", "/file/bot", 1) + "/" + path
        async with s.get(url, timeout=aiohttp.ClientTimeout(total=120)) as r:
            if r.status != 200:
                raise RuntimeError("download status %s" % r.status)
            return await r.read(), path.rsplit("/", 1)[-1]


async def enqueue(msg):
    """Мужская сторона: положить сообщение в очередь. Повторный вызов на то же
    сообщение ничего не добавит (src_message_id уникален)."""
    kind, file_id, file_name = _media_of(msg)
    local = None
    if kind:
        body, tg_name = await _download(file_id)
        os.makedirs(_dir(), exist_ok=True)
        local = os.path.join(_dir(), uuid.uuid4().hex)
        with open(local, "wb") as f:
            f.write(body)
        file_name = file_name or tg_name
    text = msg.get("caption") if kind else msg.get("text")
    entities = msg.get("caption_entities") if kind else msg.get("entities")
    with _connect() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO tadabbur_mirror"
            " (src_message_id, kind, text, entities, file_path, file_name, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (msg.get("message_id"), kind or "text", text or "",
             json.dumps(entities, ensure_ascii=False) if entities else None,
             local, file_name, get_now().isoformat()))
        added = cur.rowcount
    if not added and local:
        os.remove(local)
    log.info("tadabbur mirror: queued msg %s (%s)%s", msg.get("message_id"),
             kind or "text", "" if added else " - already queued")
    return bool(added)


def capture(msg):
    """Вызов из цикла getUpdates мужского бота: проверка сразу, скачивание -
    фоном, чтобы не держать приём остальных сообщений."""
    try:
        if not should_mirror(msg):
            return
    except Exception:
        log.exception("tadabbur mirror: check failed")
        return

    async def _run():
        try:
            await enqueue(msg)
        except Exception:
            log.exception("tadabbur mirror: enqueue failed for msg %s", msg.get("message_id"))
    asyncio.create_task(_run())


async def _send(chat_id, row):
    """Отправить одну запись очереди. Возвращает ответ Telegram."""
    entities = json.loads(row["entities"]) if row["entities"] else None
    if row["kind"] == "text":
        from core.tg import tg_call   # tg_call сам пишет sendMessage в ленту
        payload = {"chat_id": chat_id, "text": row["text"]}
        if entities:
            payload["entities"] = entities
        return await tg_call("sendMessage", payload)

    method, field, feed_kind = MEDIA[row["kind"]]
    with open(row["file_path"], "rb") as f:
        body = f.read()
    data = aiohttp.FormData()
    data.add_field("chat_id", str(chat_id))
    if row["text"] and row["kind"] != "video_note":
        data.add_field("caption", row["text"])
        if entities:
            data.add_field("caption_entities", json.dumps(entities, ensure_ascii=False))
    data.add_field(field, body, filename=row["file_name"] or field)
    async with aiohttp.ClientSession() as s:
        async with s.post(config.TG_API + "/" + method, data=data,
                          timeout=aiohttp.ClientTimeout(total=180)) as r:
            result = await r.json()
    if result and result.get("ok"):
        record_outgoing(chat_id, result=result, text=row["text"], kind=feed_kind)
    return result


async def deliver_once():
    """Женская сторона: разослать всё, что ждёт. Возвращает число отправленных."""
    tad = get_tadabbur_group()
    if not tad:
        return 0
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM tadabbur_mirror WHERE sent_at IS NULL AND attempts < ?"
            " ORDER BY id", (MAX_ATTEMPTS,)).fetchall()
    sent = 0
    now = get_now()
    for row in rows:
        try:
            age_h = (now - datetime.fromisoformat(row["created_at"])).total_seconds() / 3600
        except (TypeError, ValueError):
            age_h = 0
        if age_h > STALE_HOURS:
            _finish(row, error="stale")
            continue
        try:
            result = await _send(tad["chat_id"], row)
        except Exception as e:
            result = {"ok": False, "description": "%s: %s" % (type(e).__name__, e)}
        if result and result.get("ok"):
            _finish(row, sent=True)
            sent += 1
            log.info("tadabbur mirror: sent #%s (%s)", row["id"], row["kind"])
        else:
            err = (result or {}).get("description") or "no response"
            with _connect() as c:
                c.execute("UPDATE tadabbur_mirror SET attempts=attempts+1, error=? WHERE id=?",
                          (err, row["id"]))
            log.error("tadabbur mirror: #%s failed: %s", row["id"], err)
            if row["attempts"] + 1 >= MAX_ATTEMPTS:
                _drop_file(row)
    return sent


def _drop_file(row):
    if row["file_path"]:
        try:
            os.remove(row["file_path"])
        except OSError:
            pass


def _finish(row, sent=False, error=None):
    with _connect() as c:
        c.execute("UPDATE tadabbur_mirror SET sent_at=?, error=? WHERE id=?",
                  (get_now().isoformat() if sent else None, error, row["id"]))
        if not sent:
            c.execute("UPDATE tadabbur_mirror SET attempts=? WHERE id=?",
                      (MAX_ATTEMPTS, row["id"]))
    _drop_file(row)


async def run():
    """Цикл женского бота."""
    while True:
        try:
            await deliver_once()
        except Exception:
            log.exception("tadabbur mirror: deliver failed")
        await asyncio.sleep(POLL_SECONDS)
