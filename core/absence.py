"""Узр и пауза «Цикл» (03.11.2026, решение пользователя).

Узр - уважительная причина на один день: не больше одного в день и
EXCUSE_MONTHLY_LIMIT в календарный месяц, без балла (wiki/excuse_detection.md).
Одна функция apply_excuse на оба входа - текст «узр» в Telegram и кнопку
в «Работе с устазом», чтобы правила не разъехались.

Пауза «Цикл» - только у сестёр. Часть сестёр по своему мазхабу не учит
Коран во время хайда; это вопрос фикха, мы его не решаем, а только не
считаем такие дни пропусками. Правила:
- нажала - пауза с сегодняшнего учебного дня;
- каждый день паузы - событие score_events category='pause' с 0 баллов:
  по нему день не пропуск (счётчики пропусков смотрят на любое событие
  дня), а напоминания, отчёт группы и серия исключают его явно;
- день пишется только «сегодня» (tick после 03:00), наперёд никогда:
  иначе любое MAX(date) увидело бы день из будущего;
- конец сам: первая сдача после нажатия (on_task_saved из save_report),
  либо PAUSE_MAX_DAYS дней (15 - максимум хайда у шафиитов);
- в лимит узров не идёт; группе не видно, устазу - «пауза» в календаре;
- недельный +5 на такой неделе не даётся (неделя не полная - само собой);
- серия на паузе не рвётся и не растёт (db.get_streak_days).
"""
from datetime import datetime, timedelta

import core.db as dbm   # через модуль: тесты подменяют dbm.get_date


def db():
    return dbm.db()


def add_bonus(*a, **kw):
    return dbm.add_bonus(*a, **kw)


def get_date(uid=None):
    return dbm.get_date(uid)


def get_excuse_count_month(uid, group_id):
    return dbm.get_excuse_count_month(uid, group_id)

EXCUSE_MONTHLY_LIMIT = 3
PAUSE_MAX_DAYS = 15
PAUSE_CATEGORY = "pause"
PAUSE_CYCLE = "cycle"


def init():
    with db() as c:
        c.execute(
            "CREATE TABLE IF NOT EXISTS absence_pauses("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " student_id INTEGER NOT NULL,"
            " group_id INTEGER NOT NULL,"
            " kind TEXT NOT NULL DEFAULT 'cycle',"
            " start_date TEXT NOT NULL,"
            " created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,"
            " closed_at TEXT,"
            " close_reason TEXT)"
        )
        c.execute("CREATE INDEX IF NOT EXISTS idx_absence_pauses_open"
                  " ON absence_pauses(student_id, closed_at)")


# ── Узр ───────────────────────────────────────────────────────────────────────

def excuse_status(uid, group_id):
    """Для экрана: узр уже сегодня? сколько осталось в месяце?"""
    with db() as c:
        today = c.execute(
            "SELECT note FROM score_events WHERE student_id=? AND group_id=? AND date=?"
            " AND category='excuse'", (uid, group_id, get_date(uid))
        ).fetchone()
    used = get_excuse_count_month(uid, group_id)
    return {"today": today is not None, "left": max(0, EXCUSE_MONTHLY_LIMIT - used),
            "limit": EXCUSE_MONTHLY_LIMIT}


def apply_excuse(uid, group_id, reason=None):
    """'ok' | 'already' (уже был сегодня) | 'limit' (месяц исчерпан).

    Во время паузы «Цикл» - 'already': день и так не пропуск, лимит не
    тратим, а ответ в группе нейтральный и паузу не выдаёт."""
    if active_pause(uid):
        return "already"
    with db() as c:
        already = c.execute(
            "SELECT 1 FROM score_events WHERE student_id=? AND group_id=? AND date=?"
            " AND category='excuse'", (uid, group_id, get_date(uid))
        ).fetchone()
    if already:
        return "already"
    if get_excuse_count_month(uid, group_id) >= EXCUSE_MONTHLY_LIMIT:
        return "limit"
    # Узр без балла (30.09.2026): событие остаётся - по нему день не пропуск
    # и считается месячный лимит.
    add_bonus(uid, group_id, get_date(uid), 0, "excuse", note=(reason or "").strip()[:300] or None)
    return "ok"


# ── Пауза ─────────────────────────────────────────────────────────────────────

def _row(r):
    return dict(r) if r else None


def active_pause(uid):
    with db() as c:
        return _row(c.execute(
            "SELECT * FROM absence_pauses WHERE student_id=? AND closed_at IS NULL"
            " ORDER BY id DESC LIMIT 1", (uid,)
        ).fetchone())


def pause_day(p, today=None):
    """Какой по счёту день паузы (с 1)."""
    today = today or get_date(p["student_id"])
    start = datetime.strptime(p["start_date"], "%Y-%m-%d").date()
    return (datetime.strptime(today, "%Y-%m-%d").date() - start).days + 1


def _utc_now():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def start_pause(uid, group_id, kind=PAUSE_CYCLE):
    """Ставит паузу с сегодняшнего учебного дня. Уже идёт - возвращает её."""
    p = active_pause(uid)
    if p:
        return p
    today = get_date(uid)
    with db() as c:
        c.execute(
            "INSERT INTO absence_pauses(student_id, group_id, kind, start_date, created_at)"
            " VALUES(?,?,?,?,?)", (uid, group_id, kind, today, _utc_now()))
    add_bonus(uid, group_id, today, 0, PAUSE_CATEGORY, kind)
    return active_pause(uid)


def close_pause(pause_id, reason):
    with db() as c:
        c.execute("UPDATE absence_pauses SET closed_at=?, close_reason=? WHERE id=? AND closed_at IS NULL",
                  (_utc_now(), reason, pause_id))


def on_task_saved(uid, date):
    """Сдача закрывает паузу - если она за сегодняшний учебный день. Сдачу
    задним числом (устаз принял старую запись) сюда не зовут вовсе."""
    if date != get_date(uid):
        return
    p = active_pause(uid)
    if p:
        close_pause(p["id"], "submitted")


def tick():
    """Каждый учебный день, после 03:00: дописать сегодняшний день паузы или
    снять паузу после PAUSE_MAX_DAYS дней. Идемпотентно (INSERT OR IGNORE);
    пропущенный запуск догоняется - дни между последним и сегодня дописываются."""
    with db() as c:
        rows = c.execute("SELECT * FROM absence_pauses WHERE closed_at IS NULL").fetchall()
    closed = 0
    for r in rows:
        p = dict(r)
        uid, gid = p["student_id"], p["group_id"]
        with db() as c:
            member = c.execute(
                "SELECT 1 FROM user_groups WHERE user_id=? AND group_id=? AND role='student' AND active=1",
                (uid, gid)).fetchone()
        if not member:
            close_pause(p["id"], "left_group")
            closed += 1
            continue
        today = get_date(uid)
        start = datetime.strptime(p["start_date"], "%Y-%m-%d").date()
        last = start + timedelta(days=PAUSE_MAX_DAYS - 1)
        d = start
        end = min(datetime.strptime(today, "%Y-%m-%d").date(), last)
        while d <= end:
            add_bonus(uid, gid, d.isoformat(), 0, PAUSE_CATEGORY, p["kind"])
            d += timedelta(days=1)
        if pause_day(p, today) > PAUSE_MAX_DAYS:
            close_pause(p["id"], "limit")
            closed += 1
    return {"open": len(rows) - closed, "closed": closed}


def paused_ids(group_id, date):
    """Кто из группы в этот день на паузе."""
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT student_id FROM score_events WHERE group_id=? AND date=? AND category=?",
            (group_id, date, PAUSE_CATEGORY)).fetchall()
    return {r["student_id"] for r in rows}


def pause_dates(uid, group_id=None, start=None, end=None):
    """Даты паузы студента (по всем группам, если group_id не задан)."""
    sql = "SELECT DISTINCT date FROM score_events WHERE student_id=? AND category=?"
    params = [uid, PAUSE_CATEGORY]
    if group_id is not None:
        sql += " AND group_id=?"
        params.append(group_id)
    if start:
        sql += " AND date>=?"
        params.append(start)
    if end:
        sql += " AND date<?"
        params.append(end)
    with db() as c:
        return sorted(r["date"] for r in c.execute(sql + " ORDER BY date", params).fetchall())


def pause_status(uid):
    """Для экрана: идёт ли пауза и какой день."""
    p = active_pause(uid)
    if not p:
        return None
    return {"kind": p["kind"], "since": p["start_date"], "day": pause_day(p),
            "max": PAUSE_MAX_DAYS}
