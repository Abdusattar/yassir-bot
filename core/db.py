import sqlite3
from datetime import datetime, timedelta
import pytz
from config import DB, TZ
from core.content import TASK_KEYS, TASK_WORDS


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
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

            CREATE TABLE IF NOT EXISTS users(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT UNIQUE,
                active INTEGER DEFAULT 1,
                added_date TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS user_groups(
                user_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                role TEXT NOT NULL DEFAULT 'student',
                active INTEGER DEFAULT 1,
                joined_date TEXT DEFAULT (date('now')),
                PRIMARY KEY(user_id, group_id, role),
                FOREIGN KEY(user_id) REFERENCES users(id),
                FOREIGN KEY(group_id) REFERENCES groups(id)
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
                UNIQUE(sid, group_id, date)
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
            CREATE TABLE IF NOT EXISTS teachers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                telegram_id TEXT UNIQUE NOT NULL,
                langs TEXT DEFAULT 'ru',
                role TEXT DEFAULT 'group_admin'
            );
            CREATE TABLE IF NOT EXISTS teacher_groups(
                teacher_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                PRIMARY KEY (teacher_id, group_id),
                FOREIGN KEY (teacher_id) REFERENCES teachers(id),
                FOREIGN KEY (group_id) REFERENCES groups(id)
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
    if "started_at" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN started_at TEXT")
        c.execute("UPDATE groups SET started_at = date('now') WHERE started_at IS NULL")
    if "invite_link" not in gcols:
        c.execute("ALTER TABLE groups ADD COLUMN invite_link TEXT")

    migrated = c.execute(
        "SELECT value FROM bot_settings WHERE key='migrated_to_users'"
    ).fetchone()
    if not migrated:
        _migrate_to_users_table(c)
        c.execute(
            "INSERT OR REPLACE INTO bot_settings(key,value) VALUES('migrated_to_users','1')"
        )

    migrated_unique = c.execute(
        "SELECT value FROM bot_settings WHERE key='migrated_reports_unique'"
    ).fetchone()
    if not migrated_unique:
        _migrate_reports_unique(c)
        c.execute(
            "INSERT OR REPLACE INTO bot_settings(key,value) VALUES('migrated_reports_unique','1')"
        )


def _migrate_to_users_table(c):
    students = c.execute("SELECT * FROM students").fetchall()
    if not students:
        return

    by_phone = {}
    no_phone = []
    for s in students:
        if s["phone"]:
            by_phone.setdefault(s["phone"], []).append(dict(s))
        else:
            no_phone.append(dict(s))

    sid_to_uid = {}

    for phone, slist in by_phone.items():
        primary = min(slist, key=lambda x: x["id"])
        c.execute(
            "INSERT OR IGNORE INTO users(name, phone, active, added_date) VALUES(?,?,1,?)",
            (primary["name"], phone, primary["added_date"])
        )
        uid = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()["id"]
        for s in slist:
            sid_to_uid[s["id"]] = uid
            c.execute(
                "INSERT OR IGNORE INTO user_groups(user_id, group_id, role, active, joined_date)"
                " VALUES(?,?,'student',?,?)",
                (uid, s["group_id"], s["active"], s["added_date"])
            )

    for s in no_phone:
        c.execute(
            "INSERT INTO users(name, phone, active, added_date) VALUES(?,NULL,?,?)",
            (s["name"], s["active"], s["added_date"])
        )
        uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        sid_to_uid[s["id"]] = uid
        c.execute(
            "INSERT OR IGNORE INTO user_groups(user_id, group_id, role, active, joined_date)"
            " VALUES(?,?,'student',?,?)",
            (uid, s["group_id"], s["active"], s["added_date"])
        )

    admins = c.execute("SELECT * FROM group_admins").fetchall()
    for a in admins:
        phone = a["phone"]
        user = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if user:
            uid = user["id"]
        else:
            c.execute("INSERT INTO users(name, phone) VALUES(?,?)", ("", phone))
            uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute(
            "INSERT OR IGNORE INTO user_groups(user_id, group_id, role) VALUES(?,?,'admin')",
            (uid, a["group_id"])
        )

    for old_sid, new_uid in sid_to_uid.items():
        if old_sid == new_uid:
            continue
        c.execute("""
            INSERT INTO reports(sid, group_id, date, m, r, t, j, n, h, score)
            SELECT ?, group_id, date, m, r, t, j, n, h, score FROM reports WHERE sid=?
            ON CONFLICT(sid, group_id, date) DO UPDATE SET
                m=MAX(m, excluded.m), r=MAX(r, excluded.r), t=MAX(t, excluded.t),
                j=MAX(j, excluded.j), n=MAX(n, excluded.n), h=MAX(h, excluded.h),
                score=MAX(score, excluded.score)
        """, (new_uid, old_sid))
        c.execute("DELETE FROM reports WHERE sid=?", (old_sid,))

        c.execute("""
            INSERT OR IGNORE INTO bonus_points(sid, group_id, date, points, reason)
            SELECT ?, group_id, date, points, reason FROM bonus_points WHERE sid=?
        """, (new_uid, old_sid))
        c.execute("DELETE FROM bonus_points WHERE sid=?", (old_sid,))

        c.execute("""
            INSERT OR IGNORE INTO attendance(sid, lesson_id)
            SELECT ?, lesson_id FROM attendance WHERE sid=?
        """, (new_uid, old_sid))
        c.execute("DELETE FROM attendance WHERE sid=?", (old_sid,))


def _migrate_reports_unique(c):
    """Rebuild reports table: UNIQUE(sid, date) → UNIQUE(sid, group_id, date)."""
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("""
        CREATE TABLE reports_new(
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
            UNIQUE(sid, group_id, date)
        )
    """)
    c.execute("INSERT OR IGNORE INTO reports_new SELECT * FROM reports")
    c.execute("DROP TABLE reports")
    c.execute("ALTER TABLE reports_new RENAME TO reports")
    c.execute("PRAGMA foreign_keys = ON")


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


def cache_username(username: str, user_id: str):
    set_setting("uid:" + username.lower().lstrip("@"), user_id)


def lookup_username(username: str):
    return get_setting("uid:" + username.lower().lstrip("@"))


def cache_member_name(chat_id: str, name: str, user_id: str):
    set_setting("name:" + str(chat_id) + ":" + name.lower().strip(), user_id)


def lookup_by_name_in_chat(chat_id: str, name: str):
    key_prefix = "name:" + str(chat_id) + ":"
    needle = name.lower().strip()
    with db() as c:
        rows = c.execute(
            "SELECT key, value FROM bot_settings WHERE key LIKE ?",
            (key_prefix + "%",)
        ).fetchall()
    return [(r["key"][len(key_prefix):], r["value"]) for r in rows
            if needle in r["key"][len(key_prefix):]]


def get_students_not_in_tadabbur(group_id):
    """Активные студенты группы, которых нет в Тадаббур-группе."""
    tadabbur = get_tadabbur_group()
    if not tadabbur:
        return []
    with db() as c:
        tadabbur_uids = {r["user_id"] for r in c.execute(
            "SELECT user_id FROM user_groups WHERE group_id=? AND role='student' AND active=1",
            (tadabbur["id"],)
        ).fetchall()}
        students = c.execute("""
            SELECT u.id, u.name, u.phone FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
        """, (group_id,)).fetchall()
    return [s for s in students if s["id"] not in tadabbur_uids]


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


def get_tadabbur_group():
    rows = get_groups_by_type("tadabbur")
    return rows[0] if rows else None


def get_group_tasks(group):
    return group["tasks"].split(",") if group["tasks"] else ["m", "r", "t"]


def update_group_tasks(chat_id, tasks):
    with db() as c:
        c.execute("UPDATE groups SET tasks=? WHERE chat_id=?", (tasks, chat_id))


def update_group_lang(chat_id, lang):
    with db() as c:
        c.execute("UPDATE groups SET lang=? WHERE chat_id=?", (lang, chat_id))


def update_group_type(chat_id, group_type):
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
        user = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        if user:
            uid = user["id"]
        else:
            c.execute("INSERT INTO users(name, phone) VALUES(?,?)", ("", phone))
            uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]
        c.execute(
            "INSERT OR IGNORE INTO user_groups(user_id, group_id, role) VALUES(?,?,'admin')",
            (uid, group_id)
        )
        c.execute(
            "UPDATE user_groups SET active=1 WHERE user_id=? AND group_id=? AND role='admin'",
            (uid, group_id)
        )
        # устаз не должен числиться студентом в той же группе
        c.execute(
            "UPDATE user_groups SET active=0 WHERE user_id=? AND group_id=? AND role='student'",
            (uid, group_id)
        )


def remove_group_admin(group_id, phone):
    with db() as c:
        c.execute("""
            UPDATE user_groups SET active=0
            WHERE group_id=? AND role='admin'
              AND user_id=(SELECT id FROM users WHERE phone=?)
        """, (group_id, phone))


def get_group_admins(group_id):
    with db() as c:
        rows = c.execute("""
            SELECT u.phone FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            WHERE ug.group_id=? AND ug.role='admin' AND ug.active=1
        """, (group_id,)).fetchall()
    return [r["phone"] for r in rows if r["phone"]]


def is_any_group_admin(phone):
    with db() as c:
        row = c.execute("""
            SELECT 1 FROM user_groups ug
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='admin' AND ug.active=1
            LIMIT 1
        """, (phone,)).fetchone()
    return row is not None


# ── Users / Students ──────────────────────────────────────────────────────────

def _student_row_sql():
    """SELECT clause returning columns compatible with old students API."""
    return """
        SELECT u.id, u.name, u.phone, ug.active, u.added_date, ug.joined_date
        FROM users u
        JOIN user_groups ug ON u.id=ug.user_id
    """


def find_user_by_phone(phone):
    """Найти пользователя в глобальном реестре (без привязки к группе)."""
    with db() as c:
        return c.execute(
            "SELECT * FROM users WHERE phone=? AND active=1", (phone,)
        ).fetchone()


def get_learning_group(phone):
    """Возвращает учебную группу (pro/relaxed) в которой студент уже состоит, или None."""
    with db() as c:
        return c.execute("""
            SELECT g.id, g.title, g.group_type FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1
              AND (g.group_type='pro' OR g.group_type='relaxed' OR g.group_type IS NULL)
        """, (phone,)).fetchone()


def add_student(name, group_id, phone=None):
    """Найти или создать пользователя и добавить его в группу как студента."""
    with db() as c:
        if phone:
            user = c.execute("SELECT id FROM users WHERE phone=?", (phone,)).fetchone()
        else:
            user = None

        if user:
            uid = user["id"]
            c.execute("UPDATE users SET name=? WHERE id=? AND name=''", (name, uid))
        else:
            existing = c.execute(
                "SELECT id FROM users WHERE LOWER(name)=LOWER(?) AND phone IS NULL",
                (name,)
            ).fetchone()
            if existing:
                uid = existing["id"]
                if phone:
                    c.execute("UPDATE users SET phone=? WHERE id=?", (phone, uid))
            else:
                c.execute("INSERT INTO users(name, phone, added_date) VALUES(?,?,?)", (name, phone, get_date()))
                uid = c.execute("SELECT last_insert_rowid()").fetchone()[0]

        c.execute(
            "INSERT OR IGNORE INTO user_groups(user_id, group_id, role) VALUES(?,?,'student')",
            (uid, group_id)
        )
        c.execute(
            "UPDATE user_groups SET active=1 WHERE user_id=? AND group_id=? AND role='student'",
            (uid, group_id)
        )
        return uid


def get_students(group_id):
    with db() as c:
        return c.execute(
            _student_row_sql() +
            "WHERE ug.group_id=? AND ug.role='student' AND ug.active=1 ORDER BY u.name",
            (group_id,)
        ).fetchall()


def find_by_phone(phone, group_id):
    with db() as c:
        return c.execute(
            _student_row_sql() +
            "WHERE u.phone=? AND ug.group_id=? AND ug.role='student' AND ug.active=1",
            (phone, group_id)
        ).fetchone()


def find_by_name(name, group_id):
    with db() as c:
        return c.execute(
            _student_row_sql() +
            "WHERE LOWER(u.name)=LOWER(?) AND ug.group_id=? AND ug.role='student' AND ug.active=1",
            (name, group_id)
        ).fetchone()


def find_unlinked_by_name(name, group_id):
    """Студент без Telegram ID — точное совпадение, затем нечёткий поиск."""
    with db() as c:
        exact = c.execute(
            _student_row_sql() +
            "WHERE LOWER(u.name)=LOWER(?) AND ug.group_id=? AND ug.role='student'"
            " AND ug.active=1 AND u.phone IS NULL",
            (name, group_id)
        ).fetchone()
        if exact:
            return exact
        candidates = c.execute(
            _student_row_sql() +
            "WHERE ug.group_id=? AND ug.role='student' AND ug.active=1 AND u.phone IS NULL",
            (group_id,)
        ).fetchall()

    if not candidates:
        return None

    from difflib import SequenceMatcher
    needle = name.lower().strip()
    needle_words = set(needle.split())

    best, best_score = None, 0.0
    for row in candidates:
        stored = row["name"].lower().strip()
        stored_words = set(stored.split())
        if needle in stored or stored in needle:
            score = 0.9
        elif needle_words & stored_words:
            score = 0.7
        else:
            score = SequenceMatcher(None, needle, stored).ratio()
        if score > best_score:
            best_score, best = score, row

    return best if best_score >= 0.6 else None


def register_student(uid, phone):
    """Привязать Telegram ID к существующему пользователю."""
    with db() as c:
        c.execute("UPDATE users SET phone=? WHERE id=?", (phone, uid))


def deactivate_student(uid, group_id):
    """Деактивировать членство студента в конкретной группе."""
    with db() as c:
        c.execute(
            "UPDATE user_groups SET active=0 WHERE user_id=? AND group_id=? AND role='student'",
            (uid, group_id)
        )


def rename_student(uid, new_name):
    with db() as c:
        c.execute("UPDATE users SET name=? WHERE id=?", (new_name, uid))


def remove_all_students(group_id):
    with db() as c:
        c.execute(
            "UPDATE user_groups SET active=0 WHERE group_id=? AND role='student'", (group_id,)
        )


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


def save_report(uid, group_id, date, tasks_done):
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
            ON CONFLICT(sid,group_id,date) DO UPDATE SET
            m=MAX(m,excluded.m), r=MAX(r,excluded.r), t=MAX(t,excluded.t),
            j=MAX(j,excluded.j), n=MAX(n,excluded.n), h=MAX(h,excluded.h),
            score=MAX(score,excluded.score)
        """, (uid, group_id, date, m, r, t, j, n, h, score))


def get_today_report(uid, group_id=None):
    with db() as c:
        if group_id is not None:
            return c.execute(
                "SELECT * FROM reports WHERE sid=? AND date=? AND group_id=?",
                (uid, get_date(), group_id)
            ).fetchone()
        return c.execute(
            "SELECT * FROM reports WHERE sid=? AND date=? ORDER BY id LIMIT 1",
            (uid, get_date())
        ).fetchone()


def get_days_since_last_report(uid):
    tz = pytz.timezone(TZ)
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 400", (uid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    added = user["added_date"] if user else None
    today = datetime.now(tz).date()
    missed = 0
    for i in range(400):
        day = (today - timedelta(days=i)).isoformat()
        if added and day < added:
            break
        if day in dates:
            break
        missed += 1
    return missed


def get_consecutive_skips(uid):
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return 0
        rows = c.execute(
            "SELECT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 30", (uid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    tz = pytz.timezone(TZ)
    skips = 0
    for i in range(1, 31):
        day = (datetime.now(tz).date() - timedelta(days=i)).isoformat()
        if day < user["added_date"]:
            break
        if day not in dates:
            skips += 1
        else:
            break
    return skips


def get_skip_count_month(uid):
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    today = datetime.now(tz).date()
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return 0
        rows = c.execute(
            "SELECT date FROM reports WHERE sid=? AND date>=?", (uid, month_start)
        ).fetchall()
    dates = {r["date"] for r in rows}
    start = max(month_start, user["added_date"])
    skips = 0
    d = datetime.strptime(start, "%Y-%m-%d").date()
    while d < today:
        if d.isoformat() not in dates:
            skips += 1
        d += timedelta(days=1)
    return skips


def get_miss_count_last_30_days(uid):
    tz = pytz.timezone(TZ)
    today = datetime.now(tz).date()
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return 30
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 60", (uid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    added = user["added_date"]
    misses = 0
    days_checked = 0
    for i in range(30):
        day = (today - timedelta(days=i)).isoformat()
        if day < added:
            break
        days_checked += 1
        if day not in dates:
            misses += 1
    if days_checked < 30:
        return 30
    return misses


def get_streak_days(uid):
    tz = pytz.timezone(TZ)
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 400", (uid,)
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


def check_no_skip_week(uid):
    tz = pytz.timezone(TZ)
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return False
        rows = c.execute(
            "SELECT date FROM reports WHERE sid=? ORDER BY date DESC LIMIT 7", (uid,)
        ).fetchall()
    dates = {r["date"] for r in rows}
    today = datetime.now(tz).date()
    for i in range(7):
        day = (today - timedelta(days=i)).isoformat()
        if day < user["added_date"]:
            return False
        if day not in dates:
            return False
    return True


def get_lesson_skip_count_month(uid, group_id):
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    with db() as c:
        lessons = c.execute(
            "SELECT id FROM online_lessons WHERE group_id=? AND date>=?",
            (group_id, month_start)
        ).fetchall()
        attended = c.execute(
            "SELECT lesson_id FROM attendance WHERE sid=?", (uid,)
        ).fetchall()
    attended_ids = {a["lesson_id"] for a in attended}
    return sum(1 for l in lessons if l["id"] not in attended_ids)


def add_bonus(uid, group_id, date, points, reason):
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO bonus_points(sid,group_id,date,points,reason) VALUES(?,?,?,?,?)",
            (uid, group_id, date, points, reason)
        )


def get_missing_students(group_id, group_tasks):
    students = get_students(group_id)
    result = []
    for s in students:
        rep = get_today_report(s["id"], group_id)
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


def get_overdue_unregistered(days=14):
    """Возвращает (user_id, chat_id) незарегистрированных старше days дней."""
    with db() as c:
        return c.execute(
            "SELECT user_id, chat_id FROM unregistered_members "
            "WHERE julianday('now') - julianday(joined_date) >= ?",
            (days,)
        ).fetchall()


def remove_unregistered(user_id, chat_id):
    with db() as c:
        c.execute(
            "DELETE FROM unregistered_members WHERE user_id=? AND chat_id=?",
            (user_id, chat_id)
        )


def set_group_invite_link(group_id, link):
    with db() as c:
        c.execute("UPDATE groups SET invite_link=? WHERE id=?", (link, group_id))


def get_prep_students_due():
    """Студенты prep-групп у кого прошло ровно 14 дней с joined_date."""
    with db() as c:
        return c.execute("""
            SELECT u.id, u.name, u.phone, g.id as group_id, g.chat_id, g.title,
                   g.fallback_chat_id, ug.joined_date
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE ug.role='student' AND ug.active=1
              AND g.group_type='prep'
              AND julianday('now','localtime') - julianday(ug.joined_date) >= 14
        """).fetchall()


def count_report_days_since(uid, group_id, since_date):
    """Количество дней с отчётами начиная с даты (для prep проверки)."""
    with db() as c:
        row = c.execute(
            "SELECT COUNT(DISTINCT date) as cnt FROM reports WHERE sid=? AND group_id=? AND date>=?",
            (uid, group_id, since_date)
        ).fetchone()
        return row["cnt"] if row else 0


def get_relaxed_groups_by_lang(lang):
    """Relaxed-группы заданного языка, отсортированные по числу студентов (меньше → первая)."""
    with db() as c:
        return c.execute("""
            SELECT g.id, g.chat_id, g.title, g.invite_link,
                   COUNT(ug.user_id) as student_count
            FROM groups g
            LEFT JOIN user_groups ug ON ug.group_id=g.id AND ug.role='student' AND ug.active=1
            WHERE g.group_type='relaxed' AND g.lang=? AND g.active=1 AND g.invite_link IS NOT NULL
            GROUP BY g.id
            ORDER BY student_count ASC
        """, (lang,)).fetchall()


# ── Formatting helpers ────────────────────────────────────────────────────────

def get_cumulative_avg(group_id):
    with db() as c:
        result = c.execute("""
            SELECT ROUND(AVG(r.score), 2) as avg
            FROM reports r
            JOIN user_groups ug ON ug.user_id=r.sid AND ug.group_id=r.group_id
            WHERE r.group_id=? AND ug.role='student' AND ug.active=1
        """, (group_id,)).fetchone()
    return result["avg"] if result and result["avg"] else 0


def get_today_avg(group_id):
    with db() as c:
        result = c.execute("""
            SELECT ROUND(AVG(r.score), 2) as avg
            FROM reports r
            JOIN user_groups ug ON ug.user_id=r.sid AND ug.group_id=r.group_id
            WHERE r.group_id=? AND r.date=? AND ug.role='student' AND ug.active=1
        """, (group_id, get_date())).fetchone()
    return result["avg"] if result and result["avg"] else 0


# ── Online lessons ─────────────────────────────────────────────────────────────

_LESSON_KEY = "lesson_active:"


def open_lesson(group_id):
    """Устаз открывает урок: создаёт запись и активирует флаг."""
    today = get_date()
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO online_lessons(group_id,date) VALUES(?,?)",
            (group_id, today)
        )
        lesson = c.execute(
            "SELECT * FROM online_lessons WHERE group_id=? AND date=?", (group_id, today)
        ).fetchone()
    set_setting(_LESSON_KEY + str(group_id), str(lesson["id"]))
    return lesson


def close_lesson(group_id):
    """Устаз закрывает урок."""
    delete_setting(_LESSON_KEY + str(group_id))


def get_open_lesson(group_id):
    """Возвращает текущий активный (открытый устазом) урок или None."""
    lesson_id = get_setting(_LESSON_KEY + str(group_id))
    if not lesson_id:
        return None
    with db() as c:
        return c.execute(
            "SELECT * FROM online_lessons WHERE id=?", (int(lesson_id),)
        ).fetchone()


def get_lesson_attendance(lesson_id):
    """Список студентов отметившихся на уроке."""
    with db() as c:
        return c.execute(
            "SELECT u.name FROM attendance a JOIN users u ON a.sid=u.id WHERE a.lesson_id=?",
            (lesson_id,)
        ).fetchall()


# Оставляем для обратной совместимости с тестами/шедулером
def start_online_lesson(group_id):
    return open_lesson(group_id)


def get_active_lesson(group_id):
    return get_open_lesson(group_id)


def mark_attendance(uid, lesson_id):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO attendance(sid,lesson_id) VALUES(?,?)", (uid, lesson_id))


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_daily_report(group_id, group_title, group_tasks, for_date=None):
    from core.content import DEFAULT_TASKS
    if for_date is None:
        for_date = get_date()
    date_str = datetime.strptime(for_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    with db() as c:
        rows = c.execute("""
            SELECT u.name, u.phone, r.m, r.r, r.t, r.j, r.n, r.h, r.score
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN reports r ON u.id=r.sid AND r.date=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            ORDER BY r.score DESC NULLS LAST, u.name
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
            SELECT u.name, COALESCE(SUM(r.score),0) as points
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN reports r ON u.id=r.sid AND r.date>=? AND r.group_id=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            GROUP BY u.id ORDER BY points DESC LIMIT 1
        """, (start, group_id, group_id)).fetchone()


def format_period_report(group_id, group_title, group_tasks, days):
    start = (datetime.now(pytz.timezone(TZ)).date() - timedelta(days=days)).isoformat()
    label = "неделю" if days == 7 else ("месяц" if days == 30 else "год")
    with db() as c:
        rows = c.execute("""
            SELECT u.name,
                   COALESCE(SUM(r.score),0) as total,
                   COUNT(r.id) as days_done
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN reports r ON u.id=r.sid AND r.date>=? AND r.group_id=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            GROUP BY u.id ORDER BY total DESC
        """, (start, group_id, group_id)).fetchall()
        bonus_rows = c.execute("""
            SELECT u.name, COALESCE(SUM(b.points),0) as bonus
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN bonus_points b ON b.sid=u.id AND b.date>=? AND b.group_id=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            GROUP BY u.id
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
