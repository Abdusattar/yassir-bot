"""«След» студента в приложении (13.09.2026, идея пользователя).

Разбирая случаи Муслима и Ибрахима (Н-1), картину собирали из трёх мест -
лог nginx, журнал бота, база - и всё равно не видели главного: что человек
ТАПАЛ. nginx не знает студента (адрес на LTE меняется), сервер видит только
запросы. Здесь лежит ровно то, чего нигде нет (правило пользователя: «то,
что и так хранится в других таблицах, не стоит»):

- действия на экране: 📖, «поправить», выбор единицы, тап по строке/половине,
  ✕ посреди выбора, перелистывание, открытие пересдачи, отправка сдачи;
- попытка сохранить место вместе с ответом сервера - в mushaf_hifz_pointer
  только последнее состояние, истории попыток нет;
- устройство один раз на открытие: iOS/Android, Telegram или браузер,
  размер экрана.

НЕ дублируем: voice_submissions, mushaf_hifz_pointer, страницы (nginx),
fitlog (журнал). Склеивает всё в одну ленту scripts/user_trail.py.

Приложение копит события и шлёт пачкой вместе с heartbeat (раз в 20 с) -
новых запросов нет. Хранение TRAIL_DAYS, чистка при каждой записи. Никаких
текстов сообщений и содержимого записей - только действия."""
import re
import sqlite3
from datetime import datetime, timedelta, timezone

from core import mushaf_words as _mw  # HADITHS_DB берём в момент вызова: тесты подменяют

TRAIL_DAYS = 3
TRAIL_MAX_BATCH = 60
TRAIL_NOTE_MAX = 80
TRAIL_EVENTS = {"open", "page", "enter", "exit", "fix", "unit", "pick",
                "save", "retake", "submit", "rec"}

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS app_trail (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        user_id TEXT NOT NULL,
        profile TEXT NOT NULL,
        event TEXT NOT NULL,
        page INTEGER,
        line INTEGER,
        stage INTEGER,
        note TEXT
    )
"""
_INDEX = "CREATE INDEX IF NOT EXISTS app_trail_user_ts ON app_trail(user_id, ts)"


def ua_short(ua):
    """«iOS 18.7» / «Android 14» / «other» - чтобы строку читать глазами."""
    m = re.search(r"OS (\d+)_(\d+)", ua or "")
    if m and ("iPhone" in ua or "iPad" in ua):
        return "iOS %s.%s" % m.groups()
    m = re.search(r"Android (\d+)", ua or "")
    if m:
        return "Android " + m.group(1)
    return "other"


def _int_or_none(v):
    if isinstance(v, bool) or v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _event_ts(raw, now):
    """Время события с телефона (мс эпохи). Часы телефона могут врать -
    принимаем только в пределах часа от серверного, иначе берём серверное."""
    try:
        t = datetime.fromtimestamp(int(raw) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return now
    if abs((now - t).total_seconds()) > 3600:
        return now
    return t


def add_trail(user_id, profile, events, ua=""):
    """Пачка событий от приложения. Неизвестные события и мусор
    отбрасываются молча - отчёт студента не касается. Возвращает, сколько
    записано."""
    if not isinstance(events, list):
        return 0
    now = datetime.now(timezone.utc)
    rows = []
    for ev in events[:TRAIL_MAX_BATCH]:
        if not isinstance(ev, dict) or ev.get("e") not in TRAIL_EVENTS:
            continue
        note = str(ev.get("n") or "")[:TRAIL_NOTE_MAX]
        if ev["e"] == "open":
            note = (ua_short(ua) + " · " + note).strip(" ·")
        rows.append((_event_ts(ev.get("t"), now).isoformat(), str(user_id), profile,
                     ev["e"], _int_or_none(ev.get("p")), _int_or_none(ev.get("l")),
                     _int_or_none(ev.get("s")), note))
    if not rows:
        return 0
    cutoff = (now - timedelta(days=TRAIL_DAYS)).isoformat()
    with sqlite3.connect(_mw.HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        conn.execute(_INDEX)
        conn.execute("DELETE FROM app_trail WHERE ts < ?", (cutoff,))
        conn.executemany(
            "INSERT INTO app_trail (ts, user_id, profile, event, page, line, stage, note) "
            "VALUES (?,?,?,?,?,?,?,?)", rows)
    return len(rows)


def get_trail(user_id, hours=72):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(_mw.HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT ts, profile, event, page, line, stage, note FROM app_trail "
            "WHERE user_id=? AND ts >= ? ORDER BY ts, id", (str(user_id), since)).fetchall()
    return [dict(r) for r in rows]


def users_seen_since(profile, hours=72):
    """user_id (Telegram ID строкой) всех, у кого за окно есть хоть один
    след в приложении этого бота (15.09.2026, для утреннего напоминания
    «переходи в приложение»: кто сдаёт, но приложение не открывал)."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(_mw.HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        rows = conn.execute(
            "SELECT DISTINCT user_id FROM app_trail WHERE profile=? AND ts >= ?",
            (profile, since)).fetchall()
    return {r[0] for r in rows}

