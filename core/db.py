import sqlite3
from datetime import datetime, timedelta
import pytz
from config import DB, TZ
from core.content import TASK_KEYS, TASK_WORDS, TASK_EMOJIS


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init():
    with db() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS groups(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id TEXT UNIQUE NOT NULL,
                title TEXT,
                tasks TEXT DEFAULT 'm,r,t',
                lang TEXT DEFAULT 'ru',
                active INTEGER DEFAULT 1,
                group_type TEXT DEFAULT 'relaxed',
                fallback_chat_id TEXT,
                summary_chat_id TEXT
            );
            CREATE TABLE IF NOT EXISTS students(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                group_id INTEGER NOT NULL,
                active INTEGER DEFAULT 1,
                added_date TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS reports(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sid INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                m INTEGER DEFAULT 0,
                r INTEGER DEFAULT 0,
                t INTEGER DEFAULT 0,
                j INTEGER DEFAULT 0,
                n INTEGER DEFAULT 0,
                h INTEGER DEFAULT 0,
                score INTEGER DEFAULT 0,
                UNIQUE(sid, date)
            );
            CREATE TABLE IF NOT EXISTS bonus_points(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sid INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                points INTEGER DEFAULT 0,
                reason TEXT,
                UNIQUE(sid, date, reason)
            );
            CREATE TABLE IF NOT EXISTS online_lessons(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                UNIQUE(group_id, date)
            );
            CREATE TABLE IF NOT EXISTS attendance(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sid INTEGER NOT NULL,
                lesson_id INTEGER NOT NULL,
                UNIQUE(sid, lesson_id)
            );
            CREATE TABLE IF NOT EXISTS yassir_knowledge(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                added_date TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS group_admins(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                phone TEXT NOT NULL,
                UNIQUE(group_id, phone)
            );
            CREATE TABLE IF NOT EXISTS pending_names(
                phone TEXT NOT NULL,
                group_id INTEGER NOT NULL,
                pending_text TEXT DEFAULT '',
                PRIMARY KEY(phone, group_id)
            );
            CREATE TABLE IF NOT EXISTS chat_history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                group_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                ts TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS unregistered_members(
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                joined_date TEXT DEFAULT (date('now')),
                PRIMARY KEY(user_id, chat_id)
            );
            CREATE TABLE IF NOT EXISTS bot_settings(
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS student_transfers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                from_chat_id TEXT NOT NULL,
                to_chat_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                transferred_at TEXT DEFAULT (datetime('now'))
            );
        """)
        _run_migrations(c)


def _run_migrations(c):
    gcols = [r["name"] for r in c.execute("PRAGMA table_info(groups)").fetchall()]
    rcols = [r["name"] for r in c.execute("PRAGMA table_info(reports)").fetchall()]

    if "h" not in rcols:
        c.execute("ALTER TABLE reports ADD COLUMN h INTEGER DEFAULT 0")
    if "lang" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN lang TEXT DEFAULT 'ru'")
    if "group_type" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN group_type TEXT DEFAULT 'relaxed'")
    if "fallback_chat_id" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN fallback_chat_id TEXT")
    if "summary_chat_id" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN summary_chat_id TEXT")


# ── Time ──────────────────────────────────────────────────────────────────────

def get_date():
    return datetime.now(pytz.timezone(TZ)).date().isoformat()


def get_now():
    return datetime.now(pytz.timezone(TZ))


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key):
    with db() as c:
        row = c.execute("SELECT value FROM bot_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key, value):
    with db() as c:
        c.execute("INSERT OR REPLACE INTO bot_settings(key,value) VALUES(?,?)", (key, value))


def delete_setting(key):
    with db() as c:
        c.execute("DELETE FROM bot_settings WHERE key=?", (key,))


# ── Knowledge ─────────────────────────────────────────────────────────────────

def add_knowledge(text):
    with db() as c:
        c.execute("INSERT INTO yassir_knowledge(text) VALUES(?)", (text,))


def get_knowledge():
    with db() as c:
        return c.execute("SELECT * FROM yassir_knowledge ORDER BY id").fetchall()


def get_yassir_knowledge():
    rows = get_knowledge()
    if not rows:
        return ""
    return "\n".join("- " + r["text"] for r in rows)


def delete_knowledge(kid):
    with db() as c:
        c.execute("DELETE FROM yassir_knowledge WHERE id=?", (kid,))


# ── Groups ────────────────────────────────────────────────────────────────────

def save_group(chat_id, title, tasks="m,r,t"):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO groups(chat_id,title,tasks) VALUES(?,?,?)",
            (chat_id, title, tasks)
        )


def get_group(chat_id):
    with db() as c:
        return c.execute("SELECT * FROM groups WHERE chat_id=? AND active=1", (chat_id,)).fetchone()


def get_all_groups():
    with db() as c:
        return c.execute("SELECT * FROM groups WHERE active=1").fetchall()


def get_groups_by_type(group_type):
    with db() as c:
        return c.execute(
            "SELECT * FROM groups WHERE active=1 AND group_type=?", (group_type,)
        ).fetchall()


def get_group_tasks(group):
    return group["tasks"].split(",") if group["tasks"] else ["m", "r", "t"]


def update_group_tasks(chat_id, tasks):
    with db() as c:
        c.execute("UPDATE groups SET tasks=? WHERE chat_id=?", (tasks, chat_id))


def update_group_lang(chat_id, lang):
    with db() as c:
        c.execute("UPDATE groups SET lang=? WHERE chat_id=?", (lang, chat_id))


def update_group_type(chat_id, group_type):
    """group_type: 'pro' | 'relaxed' | 'tadabbur'"""
    with db() as c:
        c.execute("UPDATE groups SET group_type=? WHERE chat_id=?", (group_type, chat_id))


def update_group_fallback(chat_id, fallback_chat_id):
    with db() as c:
        c.execute("UPDATE groups SET fallback_chat_id=? WHERE chat_id=?", (fallback_chat_id, chat_id))


def update_group_summary(chat_id, summary_chat_id):
    with db() as c:
        c.execute("UPDATE groups SET summary_chat_id=? WHERE chat_id=?", (summary_chat_id, chat_id))


def get_group_lang(group):
    try:
        return group["lang"] or "ru"
    except (IndexError, KeyError):
        return "ru"


# ── Group admins ──────────────────────────────────────────────────────────────

def add_group_admin(group_id, phone):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO group_admins(group_id,phone) VALUES(?,?)", (group_id, phone))


def remove_group_admin(group_id, phone):
    with db() as c:
        c.execute("DELETE FROM group_admins WHERE group_id=? AND phone=?", (group_id, phone))


def get_group_admins(group_id):
    with db() as c:
        rows = c.execute("SELECT phone FROM group_admins WHERE group_id=?", (group_id,)).fetchall()
    return [r["phone"] for r in rows]


# ── Students ──────────────────────────────────────────────────────────────────

def add_student(name, group_id, phone=None):
    with db() as c:
        existing = c.execute(
            "SELECT id FROM students WHERE LOWER(name)=LOWER(?) AND group_id=? AND active=1",
            (name, group_id)
        ).fetchone()
        if existing:
            if phone:
                c.execute("UPDATE students SET phone=? WHERE id=?", (phone, existing["id"]))
            return existing["id"]
        c.execute("INSERT INTO students(name,group_id,phone) VALUES(?,?,?)", (name, group_id, phone))
        return c.execute("SELECT last_insert_rowid()").fetchone()[0]


def get_students(group_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM students WHERE group_id=? AND active=1 ORDER BY name",
            (group_id,)
        ).fetchall()


def find_by_phone(phone, group_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM students WHERE phone=? AND group_id=? AND active=1",
            (phone, group_id)
        ).fetchone()


def find_by_name(name, group_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM students WHERE LOWER(name)=LOWER(?) AND group_id=? AND active=1",
            (name, group_id)
        ).fetchone()


def register_student(sid, phone):
    with db() as c:
        c.execute("UPDATE students SET phone=? WHERE id=?", (phone, sid))


def deactivate_student(sid):
    with db() as c:
        c.execute("UPDATE students SET active=0 WHERE id=?", (sid,))


def rename_student(sid, new_name):
    with db() as c:
        c.execute("UPDATE students SET name=? WHERE id=?", (new_name, sid))


def remove_all_students(group_id):
    with db() as c:
        c.execute("UPDATE students SET active=0 WHERE group_id=?", (group_id,))


# ── Pending names ─────────────────────────────────────────────────────────────

def set_pending_name(phone, group_id, pending_text=""):
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO pending_names(phone,group_id,pending_text) VALUES(?,?,?)",
            (phone, group_id, pending_text)
        )


def get_pending_text(phone, group_id):
    with db() as c:
        row = c.execute(
            "SELECT pending_text FROM pending_names WHERE phone=? AND group_id=?",
            (phone, group_id)
        ).fetchone()
    return row["pending_text"] if row else ""


def is_pending_name(phone, group_id):
    with db() as c:
        row = c.execute(
            "SELECT 1 FROM pending_names WHERE phone=? AND group_id=?", (phone, group_id)
        ).fetchone()
    return row is not None


def clear_pending_name(phone, group_id):
    with db() as c:
        c.execute("DELETE FROM pending_names WHERE phone=? AND group_id=?", (phone, group_id))


# ── Chat memory ───────────────────────────────────────────────────────────────

def save_chat(phone, group_id, role, content):
    with db() as c:
        c.execute(
            "INSERT INTO chat_history(phone,group_id,role,content) VALUES(?,?,?,?)",
            (phone, group_id, role, content[:1000])
        )
        c.execute("""
            DELETE FROM chat_history WHERE id IN (
                SELECT id FROM chat_history
                WHERE phone=? AND group_id=?
                ORDER BY id DESC LIMIT -1 OFFSET 10
            )
        """, (phone, group_id))


def get_student_memory(phone, group_id, limit=6):
    with db() as c:
        rows = c.execute(
            "SELECT role, content FROM chat_history WHERE phone=? AND group_id=? ORDER BY id DESC LIMIT ?",
            (phone, group_id, limit)
        ).fetchall()
    return list(reversed(rows))


# ── Reports ───────────────────────────────────────────────────────────────────

def check_text(text):
    t = text.lower()
    result = {k: False for k in TASK_KEYS}
    for key, words in TASK_WORDS.items():
        for w in words:
            if w in t:
                result[key] = True
                break
    for key, emojis in TASK_EMOJIS.items():
        if not result[key]:
            for em in emojis:
                if em in text:
                    result[key] = True
                    break
    return result


def count_checkmarks(text):
    marks = ["✅", "✔️", "✔", "☑️", "☑", "✓", "👍"]
    count = 0
    for m in marks:
        count += text.count(m)
    return count


def is_checkmarks_only(text):
    cleaned = text
    for ch in ["✅","✔️","✔","☑️","☑","✓","👍"," ","\n","\r","\t",".",")","(","-","1","2","3","4","5","6","7","8","9","0"]:
        cleaned = cleaned.replace(ch, "")
    return count_checkmarks(text) > 0 and len(cleaned.strip()) == 0


def save_report(sid, group_id, date, tasks_done):
    m = int(tasks_done.get("m", False))
    r = int(tasks_done.get("r", False))
    t = int(tasks_done.get("t", False))
    j = int(tasks_done.get("j", False))
    n = int(tasks_done.get("n", False))
    h = int(tasks_done.get("h", False))
    score = m + r + t + j + n + h
    with db() as c:
        c.execute("""
            INSERT INTO reports(sid,group_id,date,m,r,t,j,n,h,score) VALUES(?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(sid,date) DO UPDATE SET
            m=MAX(m,excluded.m), r=MAX(r,excluded.r), t=MAX(t,excluded.t),
            j=MAX(j,excluded.j), n=MAX(n,excluded.n), h=MAX(h,excluded.h),
            score=MAX(score,excluded.score)
        """, (sid, group_id, date, m, r, t, j, n, h, score))


def get_today_report(sid):
    with db() as c:
        return c.execute("SELECT * FROM reports WHERE sid=? AND date=?", (sid, get_date())).fetchone()


def get_days_since_last_report(sid):
    tz = pytz.timezone(TZ)
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 400", (sid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    today = datetime.now(tz).date()
    missed = 0
    for i in range(400):
        day = (today - timedelta(days=i)).isoformat()
        if day in dates:
            break
        missed += 1
    return missed


def get_consecutive_skips(sid):
    with db() as c:
        student = c.execute("SELECT added_date FROM students WHERE id=?", (sid,)).fetchone()
        if not student:
            return 0
        rows = c.execute("SELECT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 30", (sid,)).fetchall()
    dates = {r["date"] for r in rows}
    tz = pytz.timezone(TZ)
    skips = 0
    for i in range(1, 31):
        day = (datetime.now(tz).date() - timedelta(days=i)).isoformat()
        if day < student["added_date"]:
            break
        if day not in dates:
            skips += 1
        else:
            break
    return skips


def get_skip_count_month(sid):
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    today = datetime.now(tz).date()
    with db() as c:
        student = c.execute("SELECT added_date FROM students WHERE id=?", (sid,)).fetchone()
        if not student:
            return 0
        rows = c.execute("SELECT date FROM reports WHERE sid=? AND date>=?", (sid, month_start)).fetchall()
    dates = {r["date"] for r in rows}
    start = max(month_start, student["added_date"])
    skips = 0
    d = datetime.strptime(start, "%Y-%m-%d").date()
    while d < today:
        if d.isoformat() not in dates:
            skips += 1
        d += timedelta(days=1)
    return skips


def get_miss_count_last_30_days(sid):
    """Сколько дней студент не сдавал за последние 30 дней (для upgrade-проверки)."""
    tz = pytz.timezone(TZ)
    today = datetime.now(tz).date()
    with db() as c:
        student = c.execute("SELECT added_date FROM students WHERE id=?", (sid,)).fetchone()
        if not student:
            return 30
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 60", (sid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    misses = 0
    for i in range(30):
        day = (today - timedelta(days=i)).isoformat()
        if day < student["added_date"]:
            break
        if day not in dates:
            misses += 1
    return misses


def get_streak_days(sid):
    tz = pytz.timezone(TZ)
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 400", (sid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    today = datetime.now(tz).date()
    streak = 0
    for i in range(400):
        day = (today - timedelta(days=i)).isoformat()
        if day in dates:
            streak += 1
        else:
            break
    return streak


def check_no_skip_week(sid):
    tz = pytz.timezone(TZ)
    with db() as c:
        student = c.execute("SELECT added_date FROM students WHERE id=?", (sid,)).fetchone()
        if not student:
            return False
        rows = c.execute("SELECT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 7", (sid,)).fetchall()
    dates = {r["date"] for r in rows}
    today = datetime.now(tz).date()
    for i in range(7):
        day = (today - timedelta(days=i)).isoformat()
        if day < student["added_date"]:
            return False
        if day not in dates:
            return False
    return True


def get_lesson_skip_count_month(sid, group_id):
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    with db() as c:
        lessons = c.execute(
            "SELECT id FROM online_lessons WHERE group_id=? AND date>=?",
            (group_id, month_start)
        ).fetchall()
        attended = c.execute("SELECT lesson_id FROM attendance WHERE sid=?", (sid,)).fetchall()
    attended_ids = {a["lesson_id"] for a in attended}
    return sum(1 for l in lessons if l["id"] not in attended_ids)


def add_bonus(sid, group_id, date, points, reason):
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO bonus_points(sid,group_id,date,points,reason) VALUES(?,?,?,?,?)",
            (sid, group_id, date, points, reason)
        )


def get_missing_students(group_id, group_tasks):
    students = get_students(group_id)
    result = []
    for s in students:
        rep = get_today_report(s["id"])
        missing = []
        for key in group_tasks:
            if not rep or not rep[key]:
                missing.append(key)
        if missing:
            result.append((s, missing))
    return result


# ── Transfers ─────────────────────────────────────────────────────────────────

def log_transfer(student_id, from_chat_id, to_chat_id, reason):
    with db() as c:
        c.execute(
            "INSERT INTO student_transfers(student_id,from_chat_id,to_chat_id,reason) VALUES(?,?,?,?)",
            (student_id, from_chat_id, to_chat_id, reason)
        )


# ── Formatting helpers ────────────────────────────────────────────────────────

def get_cumulative_avg(group_id):
    with db() as c:
        result = c.execute("""
            SELECT ROUND(AVG(r.score), 2) as avg
            FROM reports r JOIN students s ON s.id=r.sid
            WHERE r.group_id=? AND s.active=1
        """, (group_id,)).fetchone()
    return result["avg"] if result and result["avg"] else 0


def get_today_avg(group_id):
    with db() as c:
        result = c.execute("""
            SELECT ROUND(AVG(r.score), 2) as avg
            FROM reports r JOIN students s ON s.id=r.sid
            WHERE r.group_id=? AND r.date=? AND s.active=1
        """, (group_id, get_date())).fetchone()
    return result["avg"] if result and result["avg"] else 0


# ── Online lessons ─────────────────────────────────────────────────────────────

def start_online_lesson(group_id):
    today = get_date()
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO online_lessons(group_id,date) VALUES(?,?)",
            (group_id, today)
        )
        return c.execute(
            "SELECT * FROM online_lessons WHERE group_id=? AND date=?", (group_id, today)
        ).fetchone()


def get_active_lesson(group_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM online_lessons WHERE group_id=? AND date=?",
            (group_id, get_date())
        ).fetchone()


def mark_attendance(sid, lesson_id):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO attendance(sid,lesson_id) VALUES(?,?)", (sid, lesson_id))


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_daily_report(group_id, group_title, group_tasks, for_date=None):
    from core.content import DEFAULT_TASKS
    if for_date is None:
        for_date = get_date()
    date_str = datetime.strptime(for_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    with db() as c:
        rows = c.execute("""
            SELECT s.name, s.phone, r.m, r.r, r.t, r.j, r.n, r.h, r.score
            FROM students s
            LEFT JOIN reports r ON s.id=r.sid AND r.date=?
            WHERE s.group_id=? AND s.active=1
            ORDER BY r.score DESC NULLS LAST, s.name
        """, (for_date, group_id)).fetchall()

    total_tasks = len(group_tasks)
    legend = "  ".join(DEFAULT_TASKS[k] for k in group_tasks)
    lines = ["📋 Отчёт — " + group_title + " за " + date_str + "\n"]
    lines.append("Порядок заданий:\n" + legend + "\n")

    done_count = 0
    for r in rows:
        marks = ""
        cnt = 0
        for key in group_tasks:
            if r[key]:
                marks += "✅"
                cnt += 1
            else:
                marks += "❌"
        if cnt > 0:
            done_count += 1
        celebrate = " 🎉" if cnt == total_tasks else ""
        lines.append(r["name"] + ": " + marks + " " + str(cnt) + "/" + str(total_tasks) + celebrate)

    lines.append("\n📊 Сдали хоть что-то: " + str(done_count) + "/" + str(len(rows)))
    lines.append("📈 Средний балл сегодня: " + str(get_today_avg(group_id)))
    lines.append("📊 Средний за всё время: " + str(get_cumulative_avg(group_id)))
    return "\n".join(lines)


def get_period_winner(group_id, days):
    start = (datetime.now(pytz.timezone(TZ)).date() - timedelta(days=days)).isoformat()
    with db() as c:
        return c.execute("""
            SELECT s.name, COALESCE(SUM(r.score),0) as points
            FROM students s
            LEFT JOIN reports r ON s.id=r.sid AND r.date>=? AND r.group_id=?
            WHERE s.group_id=? AND s.active=1
            GROUP BY s.id ORDER BY points DESC LIMIT 1
        """, (start, group_id, group_id)).fetchone()


def format_period_report(group_id, group_title, group_tasks, days):
    start = (datetime.now(pytz.timezone(TZ)).date() - timedelta(days=days)).isoformat()
    label = "неделю" if days == 7 else ("месяц" if days == 30 else "год")
    with db() as c:
        rows = c.execute("""
            SELECT s.name,
                   COALESCE(SUM(r.score),0) as total,
                   COUNT(r.id) as days_done
            FROM students s
            LEFT JOIN reports r ON s.id=r.sid AND r.date>=? AND r.group_id=?
            WHERE s.group_id=? AND s.active=1
            GROUP BY s.id ORDER BY total DESC
        """, (start, group_id, group_id)).fetchall()
        bonus_rows = c.execute("""
            SELECT s.name, COALESCE(SUM(b.points),0) as bonus
            FROM students s
            LEFT JOIN bonus_points b ON b.sid=s.id AND b.date>=? AND b.group_id=?
            WHERE s.group_id=? AND s.active=1
            GROUP BY s.id
        """, (start, group_id, group_id)).fetchall()

    bonus_map = {b["name"]: b["bonus"] for b in bonus_rows}
    medals = ["🥇", "🥈", "🥉"]

    def day_word(n):
        return "день" if n == 1 else ("дня" if 2 <= n <= 4 else "дней")

    lines = ["📊 Отчёт за " + label + " — " + group_title + ":\n"]
    for i, r in enumerate(rows):
        medal = medals[i] if i < 3 else str(i + 1) + "."
        bonus = bonus_map.get(r["name"], 0)
        total = r["total"] + bonus
        bonus_str = " (+{} бонус)".format(bonus) if bonus > 0 else ""
        lines.append(
            medal + " " + r["name"] + " — 💎 " + str(total) + " очков"
            + " (" + str(r["days_done"]) + " " + day_word(r["days_done"]) + ")" + bonus_str
        )
    lines.append("\n📊 Средний балл за всё время: " + str(get_cumulative_avg(group_id)))
    return "\n".join(lines)
