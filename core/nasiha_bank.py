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
import random
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


def _ensure_schema(conn):
    """Таблица + миграции: template (15.09.2026, шаблон с подстановками, не
    живой текст) и used_count (сколько раз выдан из банка; seen_count - про
    другое: сколько раз модель повторила ровно этот текст)."""
    conn.execute(_SCHEMA)
    conn.execute(_UNIQ)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(nasiha_bank)")}
    if "template" not in cols:
        conn.execute("ALTER TABLE nasiha_bank ADD COLUMN template INTEGER DEFAULT 0")
    if "used_count" not in cols:
        conn.execute("ALTER TABLE nasiha_bank ADD COLUMN used_count INTEGER DEFAULT 0")


def save(kind, text, lang="ru", gtype=None, bucket=None, name=None, template=False):
    """Положить сгенерированный текст в банк. Никогда не бросает исключений:
    копилка не должна мешать отправке самой насыхи. template=True - это
    шаблон с подстановками (см. pick), имя в нём не маскируется, его там нет."""
    if not text or not HADITHS_DB.exists():
        return
    try:
        with sqlite3.connect(HADITHS_DB, timeout=5) as conn:
            _ensure_schema(conn)
            cur = conn.execute(
                "INSERT OR IGNORE INTO nasiha_bank"
                " (kind, profile, lang, gtype, bucket, text, created_at, template)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (kind, "female" if IS_FEMALE else "male", lang or "ru", gtype,
                 bucket, text if template else _mask_name(text, name),
                 datetime.utcnow().isoformat(), 1 if template else 0)
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


# ── Выдача из банка (15.09.2026) ────────────────────────────────────────────
# Решение пользователя: типовые тексты не сочинять каждый раз, а брать готовые
# («очень много вызовов»). Накопленные с 08.09 живые тексты несут числа
# конкретного студента («уже 5 дней», «31 балл», «осталось 2 дня») - проверено
# по проду: у absent цифры в 247 из 314, у skips в 20 из 21, у winner в 23 из
# 25. Выдавать их другому человеку нельзя. Поэтому для таких типов выдаются
# ШАБЛОНЫ с подстановками ({name}, {days}, {points}...), сгенерированные пачкой
# один раз (scripts/seed_nasiha_templates.py, template=1). Типы без личных
# чисел (morning_miss, tadabbur_morning) берутся из обычных накопленных
# текстов (template=False). Пока в банке меньше MIN_TEMPLATES подходящих
# текстов (так у кыргызского), вызывающий код сочиняет как раньше - и банк
# дорастает сам.
MIN_TEMPLATES = 8


def pick(kind, lang="ru", bucket=None, template=True, min_count=MIN_TEMPLATES):
    """Готовый текст из банка или None (тогда сочинять как раньше). Берётся
    наименее выданный (used_count), при равенстве - случайный: ротация без
    повторов подряд. Профиль (брат/сестра) - этого бота.

    Только approved=1 (15.09.2026, требование пользователя: «надо потом эти
    заготовки проверить соответствие Корану и хадисам, ничто не должно
    браться просто так»). Пока текст не проверен человеком, он в выдачу не
    попадает - бот сочиняет как раньше. Отметка ставится вручную после
    сверки аятов и хадисов (см. wiki/ai_costs.md)."""
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB, timeout=5) as conn:
            _ensure_schema(conn)
            where = "kind=? AND profile=? AND lang=? AND IFNULL(bucket,'')=IFNULL(?,'') AND approved=1"
            if template:
                where += " AND template=1"
            rows = conn.execute(
                "SELECT id, text, used_count FROM nasiha_bank WHERE " + where,
                (kind, "female" if IS_FEMALE else "male", lang or "ru", bucket)
            ).fetchall()
            if len(rows) < min_count:
                return None
            least = min(r[2] for r in rows)
            rid, text, _ = random.choice([r for r in rows if r[2] == least])
            conn.execute("UPDATE nasiha_bank SET used_count = used_count + 1 WHERE id=?", (rid,))
            return text
    except Exception as e:
        log.warning("nasiha_bank.pick(%s): %s", kind, e)
        return None


def count_templates(kind, lang="ru", bucket=None, template=True):
    """Сколько подходящих текстов в банке - для скрипта засева и отчётов."""
    if not HADITHS_DB.exists():
        return 0
    with sqlite3.connect(HADITHS_DB, timeout=5) as conn:
        _ensure_schema(conn)
        where = "kind=? AND profile=? AND lang=? AND IFNULL(bucket,'')=IFNULL(?,'')"
        if template:
            where += " AND template=1"
        return conn.execute(
            "SELECT COUNT(*) FROM nasiha_bank WHERE " + where,
            (kind, "female" if IS_FEMALE else "male", lang or "ru", bucket)
        ).fetchone()[0]


class _Keep(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def render(text, **vals):
    """Подстановка в шаблон; незнакомые плейсхолдеры остаются как есть."""
    return text.format_map(_Keep(vals))


def plural_ru(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        form = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        form = few
    else:
        form = many
    return f"{n} {form}"


def days_text(n, lang="ru"):
    return plural_ru(n, "день", "дня", "дней") if lang == "ru" else str(n)


def points_text(n, lang="ru"):
    return plural_ru(n, "балл", "балла", "баллов") if lang == "ru" else str(n)


def skips_text(n, lang="ru"):
    return plural_ru(n, "пропуск", "пропуска", "пропусков") if lang == "ru" else str(n)


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
