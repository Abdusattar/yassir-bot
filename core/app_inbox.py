"""Входящие из лички @YassirAppBot -> процесс половины (01.10.2026).

Зачем. Студент, чей канал - YassirApp (core/app_route.py), получает от него
вопросы с кнопками: джуз, «Далее» в онбординге, переход в pro. Нажатие
приходит слушателю YassirApp - а он живёт в мужском процессе, и в женскую
базу не пишет никогда (принцип 18.09). Поэтому нажатие ложится в очередь в
ОБЩЕЙ базе sources/hadiths.db с пометкой половины, а процесс этой половины
раз в секунду забирает своё и обрабатывает теми же обработчиками, что и
нажатие в своей личке (bot.handle_callback). Так же устроен tadabbur_mirror,
только в обратную сторону. Мужские нажатия идут той же дорогой: один путь -
меньше мест для ошибки.

Ещё одно событие - «started»: человек впервые написал YassirApp, уже будучи
в подготовительной (вошёл по пересланной ссылке). Половина делает то же,
что при первом «Старте» у себя: онбординг, отложенное предложение.

Запись помечается взятой ДО обработки: лучше потерять одно нажатие при
падении процесса, чем дважды отправить человеку одно и то же.
"""
import asyncio
from datetime import datetime
import logging
import os
import sqlite3

import config
import core.sampler as sampler   # путь читаем через модуль: тесты подменяют его там

log = logging.getLogger(__name__)

POLL_SECONDS = 1
# Нажатие старше - не исполняем: процесс половины лежал, человек давно ушёл,
# а ответ на кнопку часовой давности только удивит.
STALE_MINUTES = 60

# Кнопки, которые пишут половины (bot.py, ветка callback_query). «side:» сюда
# не входит - на «брат или сестра» YassirApp отвечает сам (core/app_bot.py).
FORWARDED = ("pjz:", "upg:", "ponb:", "inv:")


def _connect():
    c = sqlite3.connect(str(sampler.HADITHS_DB), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_inbox(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile TEXT NOT NULL,
            kind TEXT NOT NULL,
            user_id TEXT NOT NULL,
            data TEXT,
            message_id INTEGER,
            created_at TEXT NOT NULL,
            taken_at TEXT
        )
    """)
    return c


def _now():
    from core.db import get_now
    return get_now().strftime("%Y-%m-%d %H:%M:%S")


def enqueue(profile, kind, uid, data=None, message_id=None):
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO app_inbox(profile, kind, user_id, data, message_id, created_at)"
                " VALUES(?,?,?,?,?,?)",
                (profile, kind, str(uid), data, message_id, _now()))
        log.info("app_inbox: %s %s от %s -> %s", kind, data or "", uid, profile)
        return True
    except sqlite3.Error as e:
        log.error("app_inbox: не положил %s от %s (%s)", kind, uid, e)
        return False


def take():
    """Забрать свои непрочитанные записи (и сразу пометить взятыми)."""
    if not os.path.exists(str(sampler.HADITHS_DB)):
        return []
    with _connect() as c:
        rows = c.execute(
            "SELECT * FROM app_inbox WHERE profile=? AND taken_at IS NULL ORDER BY id",
            (config.PROFILE,)).fetchall()
        if rows:
            c.execute(
                "UPDATE app_inbox SET taken_at=? WHERE id IN (%s)" % ",".join("?" * len(rows)),
                [_now()] + [r["id"] for r in rows])
    return rows


def _stale(row):
    from core.db import get_now
    try:
        made = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return False
    return (get_now().replace(tzinfo=None) - made).total_seconds() > STALE_MINUTES * 60


async def on_started(uid):
    """Первый «Старт» у YassirApp того, кто уже у нас: то же, что при первом
    «Старте» у своего бота (handlers.py, ветка was_dm_ok). Только если его
    канал и правда YassirApp - иначе писать ему всё равно некуда."""
    from core.app_route import via_app
    if not via_app(uid):
        return
    from core.prep import send_prep_onboarding_if_pending
    from core.transfers import handle_dm_unlocked
    await handle_dm_unlocked(uid)
    await send_prep_onboarding_if_pending(uid)


async def deliver_once(handle_callback):
    """handle_callback(uid, data, chat_id, message_id) - из bot.py."""
    done = 0
    for row in take():
        if _stale(row):
            log.info("app_inbox: #%s устарело - пропускаю", row["id"])
            continue
        try:
            if row["kind"] == "callback":
                # Чат лички с YassirApp = id человека; ответ уйдёт туда же
                # через core/tg.py (канал YassirApp).
                await handle_callback(row["user_id"], row["data"] or "", row["user_id"], row["message_id"])
            elif row["kind"] == "started":
                await on_started(row["user_id"])
            done += 1
        except Exception:
            log.exception("app_inbox: #%s (%s) упало", row["id"], row["kind"])
    return done


async def run(handle_callback):
    while True:
        try:
            await deliver_once(handle_callback)
        except Exception:
            log.exception("app_inbox: цикл")
        await asyncio.sleep(POLL_SECONDS)
