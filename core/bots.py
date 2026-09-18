"""Два бота - одна пара (18.09.2026).

Мужской и женский боты - два процесса с разными базами, а люди путают
двери: сестра пишет /start мужскому боту, брат заходит по чужой ссылке в
женскую группу (случай Динары 17.09.2026: открывала YassirApp из чата
мужского бота, сдача отвечала «нет группы»). Единый принцип для всех дверей:
прежде чем завести человека у себя, бот спрашивает соседа
(core/db.py:other_bot_member), и если человек уже учится там - у себя
ничего не пишет, а показывает дорогу в его бот.

Чтобы показать дорогу, надо знать имя соседа. В конфиге его нет и не должно
быть (имена ботов узнаются из getMe, см. core/tg.py). Поэтому каждый бот
при старте записывает себя в ОБЩУЮ базу sources/hadiths.db - она одна на
оба процесса, как банк насых и след приложения, - а сосед читает оттуда.
Ничего настраивать руками на сервере не нужно: оба бота представятся сами
при первом же запуске нового кода.
"""
import logging
import os
import sqlite3

import config
import core.sampler as sampler   # путь читаем через модуль: тесты подменяют его там
from core.db import get_now

log = logging.getLogger(__name__)

# Как называется половина в текстах бота: «учишься в женском джамаате».
JAMAAT_IN = {"male": "мужском", "female": "женском"}


def other_profile():
    return "female" if config.PROFILE == "male" else "male"


def _connect():
    path = str(sampler.HADITHS_DB)
    c = sqlite3.connect(path, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("""
        CREATE TABLE IF NOT EXISTS bot_registry(
            profile TEXT PRIMARY KEY,
            username TEXT,
            app_link TEXT,
            updated_at TEXT
        )
    """)
    return c


def register_self(username):
    """Вызывается из bot.py сразу после getMe. Идемпотентно."""
    username = (username or "").lstrip("@")
    if not username:
        return
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO bot_registry(profile, username, app_link, updated_at)"
                " VALUES(?,?,?,?)"
                " ON CONFLICT(profile) DO UPDATE SET username=excluded.username,"
                " app_link=excluded.app_link, updated_at=excluded.updated_at",
                (config.PROFILE, username, config.MUSHAF_APP_LINK or "",
                 get_now().strftime("%Y-%m-%d %H:%M:%S")),
            )
    except sqlite3.Error as e:
        log.error("bot_registry: не записался (%s)", e)


def other_bot():
    """Сосед: {'profile', 'username', 'chat_link', 'app_link', 'jamaat'},
    либо None, если он ещё ни разу не запускался с этим кодом. Только
    чтение: базу не создаём - на раннере тестов её нет вовсе."""
    if not os.path.exists(str(sampler.HADITHS_DB)):
        return None
    try:
        with _connect() as c:
            row = c.execute(
                "SELECT username, app_link FROM bot_registry WHERE profile=?",
                (other_profile(),),
            ).fetchone()
    except sqlite3.Error as e:
        log.error("bot_registry: не прочитался (%s)", e)
        return None
    if not row or not row["username"]:
        return None
    chat_link = "https://t.me/" + row["username"]
    return {
        "profile": other_profile(),
        "username": row["username"],
        "chat_link": chat_link,
        # Прямая ссылка приложения открывает Mini App соседа из любого места;
        # если у него она не заведена - хотя бы чат, там кнопка меню.
        "app_link": row["app_link"] or chat_link,
        "jamaat": JAMAAT_IN[other_profile()],
    }
