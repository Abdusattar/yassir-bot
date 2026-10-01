"""Личка через @YassirAppBot (01.10.2026).

Зачем. Новичок путался в трёх дверях: YassirApp -> бот своей половины
(«Старт») -> подготовительная. Решение пользователя: YassirApp - единственный
голос в личке студента, боты половин - в группах. Переход мягкий: у
человека ОДИН канал, и никто из старых ничего не замечает.

Как. Решение принимается здесь, а применяется в core/tg.py - в той же
точке, где лента ловит исходящие (десятки send_* выше неё, перехватывать
каждую значило бы забыть следующую). Личное сообщение студенту, чей канал -
YassirApp, уходит токеном YassirApp; не дошло (заблокировал) - отметка
blocked и тут же старым путём.

Отметка «нажал Старт у YassirApp» лежит в ОБЩЕЙ базе sources/hadiths.db:
ставит её слушатель YassirApp (мужской процесс), читают оба. Вместе с ней
запоминается, пришёл ли человек новичком - нигде не учился в момент первой
встречи. Режим new переводит только таких: старый студент, входивший через
YassirApp на сайт, по-прежнему получает личку от своего бота.
"""
import contextvars
import logging
import os
import sqlite3

import config
import core.sampler as sampler   # путь читаем через модуль: тесты подменяют его там

log = logging.getLogger(__name__)

MODES = ("off", "test", "new", "all")

# Ответы Telegram, после которых писать человеку этим ботом бессмысленно.
_UNREACHABLE = ("bot was blocked", "user is deactivated", "can't initiate conversation",
                "chat not found", "bot can't send messages to the user")


# Чат, в котором бот половины сейчас отвечает человеку на ЕГО сообщение или
# нажатие. Ответ уходит туда же, где спросили, а не в YassirApp: иначе
# написавший своему боту получил бы ответ в другом чате. Ставится в начале
# задачи-обработчика (bot.py) и живёт только в ней.
_answering_in = contextvars.ContextVar("app_route_answering_in", default=None)


def answering_in(chat_id):
    """Вызывать только внутри задачи-обработчика: значение живёт в её контексте."""
    _answering_in.set(str(chat_id))


async def in_chat(chat_id, coro):
    """Обёртка для asyncio.create_task: обработчик нажатия в личке бота
    половины отвечает туда же."""
    answering_in(chat_id)
    return await coro


def _connect():
    c = sqlite3.connect(str(sampler.HADITHS_DB), timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS app_dm(
            user_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            newcomer INTEGER NOT NULL DEFAULT 0,
            blocked_at TEXT
        )
    """)
    return c


def _now():
    from core.db import get_now
    return get_now().strftime("%Y-%m-%d %H:%M:%S")


def mark_started(uid, newcomer):
    """Человек написал YassirApp (или нажал его кнопку) - личка с ним
    открыта. Новичок ли он, решается ОДИН раз, при первой встрече; блокировка
    снимается: раз написал - значит разблокировал."""
    uid = str(uid)
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO app_dm(user_id, started_at, newcomer) VALUES(?,?,?)"
                " ON CONFLICT(user_id) DO UPDATE SET blocked_at=NULL",
                (uid, _now(), 1 if newcomer else 0))
    except sqlite3.Error as e:
        log.error("app_dm: не отметил %s (%s)", uid, e)


def mark_blocked(uid):
    try:
        with _connect() as c:
            c.execute("UPDATE app_dm SET blocked_at=? WHERE user_id=?", (_now(), str(uid)))
    except sqlite3.Error as e:
        log.error("app_dm: не отметил блокировку %s (%s)", uid, e)
    log.info("app_dm: %s недоступен через YassirApp - дальше старым путём", uid)


def _state(uid):
    if not os.path.exists(str(sampler.HADITHS_DB)):
        return None
    try:
        with _connect() as c:
            return c.execute("SELECT * FROM app_dm WHERE user_id=?", (str(uid),)).fetchone()
    except sqlite3.Error as e:
        log.error("app_dm: не прочитал %s (%s)", uid, e)
        return None


def via_app(chat_id):
    """Писать ли в этот чат токеном YassirApp. Только личка (id > 0)."""
    if not config.APP_SEND_TOKEN or config.DM_VIA_APP not in MODES[1:]:
        return False
    uid = str(chat_id or "")
    if not uid.isdigit() or _answering_in.get() == uid:
        return False
    is_test = uid in config.DM_VIA_APP_TEST_IDS
    if not is_test:
        if config.DM_VIA_APP == "test":
            return False
        # Служебная личка устазов и суперадминов - у ботов половин (решение
        # пользователя 01.10: на этапе 1 их не трогаем).
        from core.db import is_any_group_admin
        if uid in config.SUPER_ADMIN_IDS or is_any_group_admin(uid):
            return False
    st = _state(uid)
    if not st or st["blocked_at"]:
        return False
    if is_test or config.DM_VIA_APP == "all":
        return True
    return bool(st["newcomer"])


def unreachable(result):
    """Ответ Telegram говорит, что YassirApp этому человеку писать не может."""
    if not result or result.get("ok"):
        return False
    desc = (result.get("description") or "").lower()
    return result.get("error_code") == 403 or any(m in desc for m in _UNREACHABLE)


def api_base():
    return "https://api.telegram.org/bot" + config.APP_SEND_TOKEN
