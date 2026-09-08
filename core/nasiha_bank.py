"""Копилка насых: всё, что бот сочинил, ложится сюда (08.09.2026).

Зачем. Сейчас на каждого молчащего студента уходит отдельный вызов ИИ, и так
каждый день: 40 вызовов в сутки на два бота при том, что текст по сути один и
тот же — меняются имя и число дней. Готовый банк снимет эту статью совсем.

Что здесь есть и чего нет. Здесь только накопление: бот сгенерировал текст —
он попал в банк. Выдача из банка (какой текст кому и как не повторяться)
делается отдельно, к ней возвращаемся через месяц, когда наберётся материал.
Пока это чистая копилка, на поведение бота она не влияет никак: любая ошибка
записи молча игнорируется, отправка сообщения от неё не зависит.

Имя студента заменяется на {name} — копим шаблоны, а не переписку конкретных
людей. Файл общий для мужского и женского ботов (sources/hadiths.db, как и
кэш дневной насыхи Тадаббура), но профиль пишется в строку: обращение
«брат»/«сестра» уже внутри текста, и перепутать их нельзя.
"""
import logging
import sqlite3
from datetime import datetime

from core.sampler import HADITHS_DB
from config import IS_FEMALE

log = logging.getLogger(__name__)

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS nasiha_bank(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,          -- absent | skips | streak | winner | ...
        profile TEXT NOT NULL,       -- male | female
        lang TEXT NOT NULL,
        gtype TEXT,                  -- pro | relaxed | prep | NULL
        bucket TEXT,                 -- '3-5', '6-10', '11+', 'near_limit', ...
        text TEXT NOT NULL,          -- с плейсхолдером {name}
        seen_count INTEGER DEFAULT 1,-- сколько раз модель выдала ровно этот текст
        approved INTEGER DEFAULT 0,  -- 1 - просмотрено человеком, годится к выдаче
        created_at TEXT NOT NULL
    )
"""

# Один и тот же текст модель выдаёт не раз - храним его единожды, а повторы
# считаем: частота потом подскажет, какие формулировки у неё «любимые».
_UNIQ = """
    CREATE UNIQUE INDEX IF NOT EXISTS nasiha_bank_uniq
    ON nasiha_bank(kind, profile, lang, IFNULL(gtype,''), IFNULL(bucket,''), text)
"""


def days_bucket(days):
    """Корзина для «молчит N дней». Внутри корзины тексты взаимозаменяемы -
    разница между «не сдавал 4 дня» и «не сдавал 5 дней» на содержание насыхи
    не влияет, а на число вариантов влияет сильно."""
    if days is None:
        return None
    if days <= 5:
        return "3-5"
    if days <= 10:
        return "6-10"
    return "11+"


def skips_bucket(skips, transfer_limit):
    """Корзина для пропусков: важно не само число, а близость к переводу."""
    if not transfer_limit:
        return None
    left = transfer_limit - (skips or 0)
    return "near_limit" if left <= 3 else "warning"


def _mask_name(text, name):
    """Имя в шаблон. Склонения («брату Имрану») останутся как есть - при
    выдаче такой текст просто не подойдёт под другое имя, и это лучше, чем
    портить его слепой заменой по корню."""
    if not name or not text:
        return text
    return text.replace(name, "{name}")


def save(kind, text, lang="ru", gtype=None, bucket=None, name=None):
    """Положить сгенерированный текст в банк. Никогда не бросает исключений:
    копилка не должна мешать отправке самой насыхи."""
    if not text or not HADITHS_DB.exists():
        return
    try:
        with sqlite3.connect(HADITHS_DB, timeout=5) as conn:
            conn.execute(_SCHEMA)
            conn.execute(_UNIQ)
            cur = conn.execute(
                "INSERT OR IGNORE INTO nasiha_bank"
                " (kind, profile, lang, gtype, bucket, text, created_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (kind, "female" if IS_FEMALE else "male", lang or "ru", gtype,
                 bucket, _mask_name(text, name), datetime.utcnow().isoformat())
            )
            if not cur.rowcount:
                conn.execute(
                    "UPDATE nasiha_bank SET seen_count = seen_count + 1"
                    " WHERE kind=? AND profile=? AND lang=? AND IFNULL(gtype,'')=IFNULL(?,'')"
                    "   AND IFNULL(bucket,'')=IFNULL(?,'') AND text=?",
                    (kind, "female" if IS_FEMALE else "male", lang or "ru", gtype,
                     bucket, _mask_name(text, name))
                )
    except Exception as e:
        log.debug("nasiha_bank: не записалось (%s)", e)


def stats():
    """Сколько чего накопилось - для отчёта «пора ли переходить на банк»."""
    if not HADITHS_DB.exists():
        return []
    try:
        with sqlite3.connect(HADITHS_DB, timeout=5) as conn:
            conn.execute(_SCHEMA)
            return [
                {"kind": r[0], "profile": r[1], "lang": r[2], "gtype": r[3],
                 "bucket": r[4], "texts": r[5]}
                for r in conn.execute(
                    "SELECT kind, profile, lang, gtype, bucket, COUNT(*)"
                    " FROM nasiha_bank GROUP BY kind, profile, lang, gtype, bucket"
                    " ORDER BY COUNT(*) DESC"
                )
            ]
    except Exception:
        return []
