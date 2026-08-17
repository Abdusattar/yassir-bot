import re
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
            CREATE TABLE IF NOT EXISTS score_events(
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id  INTEGER NOT NULL,
                group_id    INTEGER NOT NULL,
                date        TEXT NOT NULL,
                category    TEXT NOT NULL,
                subcategory TEXT NOT NULL DEFAULT '',
                points      INTEGER NOT NULL DEFAULT 1,
                note        TEXT,
                created_at  TEXT DEFAULT (datetime('now')),
                UNIQUE(student_id, group_id, date, category, subcategory)
            );
            CREATE INDEX IF NOT EXISTS idx_se_student_date ON score_events(student_id, date);
            CREATE INDEX IF NOT EXISTS idx_se_group_date   ON score_events(group_id, date);
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
            CREATE TABLE IF NOT EXISTS prep_graduates(
                phone TEXT NOT NULL,
                target_group_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                from_group_id INTEGER NOT NULL,
                from_chat_id TEXT NOT NULL,
                created_date TEXT DEFAULT (date('now')),
                PRIMARY KEY(phone, target_group_id)
            );
            CREATE TABLE IF NOT EXISTS pending_prep_return(
                phone TEXT PRIMARY KEY,
                from_group_id INTEGER,
                reason TEXT,
                created_date TEXT DEFAULT (date('now'))
            );
            CREATE TABLE IF NOT EXISTS return_nudges(
                phone TEXT PRIMARY KEY,
                last_sent_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS upgrade_offers(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                target_group_id INTEGER,
                offered_at TEXT NOT NULL DEFAULT (datetime('now')),
                decision TEXT,
                decided_at TEXT,
                resolved INTEGER DEFAULT 0,
                channel TEXT NOT NULL DEFAULT 'dm'
            );
            CREATE INDEX IF NOT EXISTS idx_upgrade_offers_student ON upgrade_offers(student_id, group_id);
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
            CREATE TABLE IF NOT EXISTS voice_submissions(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                chat_id TEXT NOT NULL,
                message_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                sent_at TEXT,
                reviewed_at TEXT,
                UNIQUE(chat_id, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_vs_group_date ON voice_submissions(group_id, date);

            CREATE TABLE IF NOT EXISTS curriculum_parts(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                chapter TEXT NOT NULL,
                topic TEXT NOT NULL,
                part_number INTEGER NOT NULL,
                part_total INTEGER NOT NULL,
                order_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                review_chat_id TEXT,
                review_message_id INTEGER,
                approved_at TEXT,
                published_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_cp_subject_order ON curriculum_parts(subject, order_index);

            CREATE TABLE IF NOT EXISTS attendance_confirm(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                asked_at TEXT NOT NULL DEFAULT (datetime('now')),
                decision TEXT,
                decided_at TEXT,
                escalated_at TEXT,
                UNIQUE(group_id, date)
            );
            CREATE TABLE IF NOT EXISTS attendance_confirm_students(
                confirm_id INTEGER NOT NULL,
                student_id INTEGER NOT NULL,
                PRIMARY KEY(confirm_id, student_id),
                FOREIGN KEY(confirm_id) REFERENCES attendance_confirm(id)
            );

            CREATE TABLE IF NOT EXISTS verify_log(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                group_id INTEGER NOT NULL,
                checks TEXT NOT NULL,
                submitted_text TEXT NOT NULL,
                verdict TEXT NOT NULL,
                flagged INTEGER NOT NULL,
                date TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_vl_date ON verify_log(date);
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

    vscols = [r["name"] for r in c.execute("PRAGMA table_info(voice_submissions)").fetchall()]
    if "sent_at" not in vscols:
        c.execute("ALTER TABLE voice_submissions ADD COLUMN sent_at TEXT")
    if "file_id" not in vscols:
        c.execute("ALTER TABLE voice_submissions ADD COLUMN file_id TEXT")
    if "review_type" not in vscols:
        c.execute("ALTER TABLE voice_submissions ADD COLUMN review_type TEXT")
    if "review_file_id" not in vscols:
        c.execute("ALTER TABLE voice_submissions ADD COLUMN review_file_id TEXT")
    if "review_text" not in vscols:
        c.execute("ALTER TABLE voice_submissions ADD COLUMN review_text TEXT")

    ucols = [r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()]
    if "dm_ok" not in ucols:
        c.execute("ALTER TABLE users ADD COLUMN dm_ok INTEGER DEFAULT 0")
    if "survey_stage" not in ucols:
        # NULL - анкета ещё не начата, 'asked_location'/'asked_age' - ждём
        # ответа на соответствующий вопрос, 'done' - оба ответа получены
        # (13.08.2026, разовая анкета "откуда и сколько лет" через 30 дней).
        c.execute("ALTER TABLE users ADD COLUMN survey_stage TEXT")
        c.execute("ALTER TABLE users ADD COLUMN survey_location TEXT")
        c.execute("ALTER TABLE users ADD COLUMN survey_age TEXT")
    if "survey_stage_at" not in ucols:
        # Момент последнего перехода survey_stage - нужен, чтобы повторить
        # незавершённый вопрос через неделю молчания, не спрашивая заново с
        # начала (17.08.2026, редизайн анкеты).
        c.execute("ALTER TABLE users ADD COLUMN survey_stage_at TEXT")
        # Бэкфилл для рядов, где анкета уже была начата ДО этой колонки -
        # иначе julianday(NULL) всегда NULL и nudge их никогда не найдёт.
        c.execute(
            "UPDATE users SET survey_stage_at=datetime('now') "
            "WHERE survey_stage IS NOT NULL AND survey_stage != '' AND survey_stage_at IS NULL"
        )
    if "survey_birth_year" not in ucols:
        # Год рождения, посчитанный из ответа на "сколько лет" - не сам
        # возраст, чтобы не устаревал (17.08.2026). survey_age хранит сырой
        # ответ как есть, для сверки.
        c.execute("ALTER TABLE users ADD COLUMN survey_birth_year INTEGER")

    uocols = [r["name"] for r in c.execute("PRAGMA table_info(upgrade_offers)").fetchall()]
    if "channel" not in uocols:
        c.execute("ALTER TABLE upgrade_offers ADD COLUMN channel TEXT NOT NULL DEFAULT 'dm'")

    accols = [r["name"] for r in c.execute("PRAGMA table_info(attendance_confirm)").fetchall()]
    if "decision_reason" not in accols:
        # 'manual' - устаз лично нажал кнопку; 'auto' - тайм-аут 24ч без ответа
        # (12.08.2026, нужно различать при позднем "у" и при выборе текста в группу).
        c.execute("ALTER TABLE attendance_confirm ADD COLUMN decision_reason TEXT")

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

    migrated_se = c.execute(
        "SELECT value FROM bot_settings WHERE key='migrated_to_score_events'"
    ).fetchone()
    if not migrated_se:
        _migrate_to_score_events(c)
        c.execute(
            "INSERT OR REPLACE INTO bot_settings(key,value) VALUES('migrated_to_score_events','1')"
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


def _migrate_to_score_events(c):
    """Копирует reports + bonus_points в score_events."""
    for r in c.execute("SELECT * FROM reports").fetchall():
        for key in ("m", "r", "t", "j", "n", "h"):
            if r[key]:
                c.execute(
                    "INSERT OR IGNORE INTO score_events"
                    "(student_id,group_id,date,category,subcategory,points)"
                    " VALUES(?,?,?,'task',?,1)",
                    (r["sid"], r["group_id"], r["date"], key)
                )
    for b in c.execute("SELECT * FROM bonus_points").fetchall():
        reason = b["reason"] or ""
        if reason == "excuse":
            cat, sub, note = "excuse", "", None
        elif reason == "online_lesson":
            cat, sub, note = "attendance", "online", None
        elif reason.startswith("streak_week_"):
            cat, sub, note = "streak", reason[len("streak_"):], None
        else:
            cat, sub, note = "bonus", (reason[:50] if reason else ""), reason or None
        c.execute(
            "INSERT OR IGNORE INTO score_events"
            "(student_id,group_id,date,category,subcategory,points,note)"
            " VALUES(?,?,?,?,?,?,?)",
            (b["sid"], b["group_id"], b["date"], cat, sub, b["points"], note)
        )


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


def get_group_by_id(group_id):
    with db() as c:
        return c.execute("SELECT * FROM groups WHERE id=?", (group_id,)).fetchone()


def get_event_time(student_id, group_id, category):
    """created_at (UTC, 'YYYY-MM-DD HH:MM:SS') первой записи такой категории -
    для отслеживания "сколько часов студент не отвечает/не вступил" (24.07.2026)."""
    with db() as c:
        row = c.execute(
            "SELECT created_at FROM score_events WHERE student_id=? AND group_id=? AND category=? LIMIT 1",
            (student_id, group_id, category)
        ).fetchone()
    return row["created_at"] if row else None


def get_group_by_title(title):
    with db() as c:
        return c.execute(
            "SELECT * FROM groups WHERE active=1 AND title=? LIMIT 1", (title,)
        ).fetchone()


def get_best_group_for_transfer(group_type, lang):
    """Наименее заполненная активная группа нужного типа/языка со ссылкой-
    приглашением - для авто-перевода выпускника подготовительной (24.07.2026).
    Без invite_link смысла возвращать группу нет - некуда отправлять студента."""
    with db() as c:
        return c.execute("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM user_groups ug
                    WHERE ug.group_id=g.id AND ug.role='student' AND ug.active=1) as cnt
            FROM groups g
            WHERE g.active=1 AND g.group_type=? AND g.lang=?
              AND g.invite_link IS NOT NULL AND g.invite_link != ''
            ORDER BY cnt
            LIMIT 1
        """, (group_type, lang)).fetchone()


UPGRADE_MAX_GROUP_SIZE = 10  # для relaxed→pro предлагаем только группы < 10 студентов


def get_best_pro_group_for_upgrade(lang, exclude_title="N-1"):
    """Наименее заполненная pro-группа нужного языка со ссылкой, кроме
    группы exclude_title (зарезервирована под выпускников подготовительной,
    знающих джуз - core/prep.py _PREP_JUZ_KNOWN_TARGET_TITLE) и с местом
    (< UPGRADE_MAX_GROUP_SIZE студентов) - для перехода relaxed→pro (25.07.2026)."""
    with db() as c:
        return c.execute("""
            SELECT g.*,
                   (SELECT COUNT(*) FROM user_groups ug
                    WHERE ug.group_id=g.id AND ug.role='student' AND ug.active=1) as cnt
            FROM groups g
            WHERE g.active=1 AND g.group_type='pro' AND g.lang=? AND g.title != ?
              AND g.invite_link IS NOT NULL AND g.invite_link != ''
            GROUP BY g.id
            HAVING cnt < ?
            ORDER BY cnt
            LIMIT 1
        """, (lang, exclude_title, UPGRADE_MAX_GROUP_SIZE)).fetchone()


def create_upgrade_offer(student_id, group_id, channel="dm"):
    """channel: 'dm' - обычное предложение в личку; 'group_nudge' - студент
    ещё не жал /start, ссылка на старт ушла в группу вместо личного
    предложения (25.07.2026)."""
    with db() as c:
        cur = c.execute(
            "INSERT INTO upgrade_offers(student_id, group_id, channel) VALUES(?,?,?)",
            (student_id, group_id, channel)
        )
        return cur.lastrowid


def get_last_upgrade_offer_at(student_id, group_id):
    """Дата последнего предложения (независимо от решения) - якорь для
    30-дневного окна до следующего предложения (25.07.2026)."""
    with db() as c:
        row = c.execute(
            "SELECT offered_at FROM upgrade_offers WHERE student_id=? AND group_id=? "
            "ORDER BY offered_at DESC LIMIT 1",
            (student_id, group_id)
        ).fetchone()
    return row["offered_at"] if row else None


def get_upgrade_offer_by_id(offer_id):
    """offer_id закодирован в callback_data кнопки - конкретное предложение,
    а не 'последнее по телефону' (иначе тап по устаревшему сообщению с
    кнопками мог бы случайно закрыть текущее предложение, 25.07.2026)."""
    with db() as c:
        return c.execute("SELECT * FROM upgrade_offers WHERE id=?", (offer_id,)).fetchone()


def delete_upgrade_offer(offer_id):
    """Откат создания предложения, если реальная отправка DM не удалась -
    иначе якорь 30-дневного окна сдвинулся бы без доставки (25.07.2026)."""
    with db() as c:
        c.execute("DELETE FROM upgrade_offers WHERE id=?", (offer_id,))


def set_upgrade_decision(offer_id, decision, target_group_id=None):
    with db() as c:
        c.execute(
            "UPDATE upgrade_offers SET decision=?, decided_at=datetime('now'), target_group_id=? WHERE id=?",
            (decision, target_group_id, offer_id)
        )


def get_pending_upgrade_target(phone):
    """Подтверждённое решение 'pro', ещё физически не перенесённое (resolved=0)
    - для join-хука в bot.py, определяющего реальное вступление в pro-группу.
    Возвращает (offer_id, target_group_id) или None."""
    with db() as c:
        row = c.execute("""
            SELECT uo.id, uo.target_group_id FROM upgrade_offers uo
            JOIN users u ON u.id=uo.student_id
            WHERE u.phone=? AND uo.decision='pro' AND uo.resolved=0
            ORDER BY uo.offered_at DESC LIMIT 1
        """, (phone,)).fetchone()
    return (row["id"], row["target_group_id"]) if row and row["target_group_id"] else None


def resolve_upgrade_offer(offer_id):
    with db() as c:
        c.execute("UPDATE upgrade_offers SET resolved=1 WHERE id=?", (offer_id,))


def get_pending_group_nudge(phone):
    """Непросроченное (по decision) предложение-'подтолкнуть к /start' -
    проверяется в момент, когда студент впервые открыл личку с ботом
    (mark_dm_ok_by_phone), чтобы сразу запустить настоящее DM-предложение
    (25.07.2026)."""
    with db() as c:
        return c.execute("""
            SELECT uo.* FROM upgrade_offers uo
            JOIN users u ON u.id=uo.student_id
            WHERE u.phone=? AND uo.channel='group_nudge' AND uo.decision IS NULL
            ORDER BY uo.offered_at DESC LIMIT 1
        """, (phone,)).fetchone()


def get_return_nudge_candidates():
    """Известные боту люди (есть phone), которые сейчас НЕ активны ни в
    подготовительной, ни в pro/relaxed - независимо от того, в тадаббуре
    ли они, со штрафом (pending_prep_return) или вообще нигде. Активные
    админы/устазы исключены на уровне SQL - их роль не про возврат в
    учёбу (26.07.2026, решение пользователя: Умар устаз не должен получать
    такое напоминание)."""
    with db() as c:
        return c.execute("""
            SELECT DISTINCT u.id, u.name, u.phone
            FROM users u
            WHERE u.phone IS NOT NULL AND u.active=1
              AND NOT EXISTS (
                  SELECT 1 FROM user_groups ug
                  JOIN groups g ON g.id=ug.group_id
                  WHERE ug.user_id=u.id AND ug.role='student' AND ug.active=1
                    AND g.group_type IN ('pro','relaxed','prep')
              )
              AND NOT EXISTS (
                  SELECT 1 FROM user_groups ug2
                  WHERE ug2.user_id=u.id AND ug2.role='admin' AND ug2.active=1
              )
        """).fetchall()


def get_last_known_lang(phone):
    """Язык последней известной группы студента (любой статус, не только
    активной) - для тёплых напоминаний тем, кто сейчас нигде не активен
    (26.07.2026). 'ru' по умолчанию, если истории вообще нет."""
    with db() as c:
        row = c.execute("""
            SELECT g.lang FROM user_groups ug
            JOIN groups g ON g.id=ug.group_id
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='student'
            ORDER BY ug.joined_date DESC LIMIT 1
        """, (phone,)).fetchone()
    return (row["lang"] if row else None) or "ru"


def get_last_return_nudge_at(phone):
    with db() as c:
        row = c.execute("SELECT last_sent_at FROM return_nudges WHERE phone=?", (phone,)).fetchone()
    return row["last_sent_at"] if row else None


def mark_return_nudge_sent(phone):
    with db() as c:
        c.execute("""
            INSERT INTO return_nudges(phone, last_sent_at) VALUES(?, datetime('now'))
            ON CONFLICT(phone) DO UPDATE SET last_sent_at=datetime('now')
        """, (phone,))


def get_regular_group_sizes():
    """Постоянные учебные группы (pro/relaxed) с количеством активных
    студентов - устазу для решения, куда определить выпускника подготовительной."""
    with db() as c:
        return c.execute("""
            SELECT g.title, g.group_type,
                   (SELECT COUNT(*) FROM user_groups ug
                    WHERE ug.group_id=g.id AND ug.role='student' AND ug.active=1) as cnt
            FROM groups g
            WHERE g.active=1 AND g.group_type IN ('pro','relaxed')
            ORDER BY g.group_type, cnt
        """).fetchall()


def get_prep_group():
    rows = get_groups_by_type("prep")
    return rows[0] if rows else None


def mark_pending_prep_return(phone, from_group_id, reason):
    """Отметить: студент кикнут за пропуски, должен вернуться только через
    официальный выпуск из prep. Снимается clear_pending_prep_return()
    при подтверждённом выпуске (см. core/prep.py announce_prep_graduate_arrival)."""
    with db() as c:
        c.execute(
            "INSERT OR REPLACE INTO pending_prep_return(phone, from_group_id, reason, created_date)"
            " VALUES(?,?,?,?)",
            (phone, from_group_id, reason, get_date())
        )


def is_pending_prep_return(phone):
    with db() as c:
        row = c.execute("SELECT 1 FROM pending_prep_return WHERE phone=?", (phone,)).fetchone()
    return row is not None


def clear_pending_prep_return(phone):
    with db() as c:
        c.execute("DELETE FROM pending_prep_return WHERE phone=?", (phone,))


def prep_days_done(phone):
    """Сколько дней отчётов у студента в его активной подготовительной группе.
    0, если сейчас не активен ни в одной prep-группе. Единый критерий для
    core/transfers.py (block_return_if_pending_prep) и core/prep.py
    (announce_prep_graduate_arrival) — оба должны сверяться с одним и тем
    же числом, иначе первый может пропустить студента, которого второй
    ещё не готов признать выпускником (реальный дедлок/дыра, найдены и
    исправлены 23.07.2026 при ревью)."""
    with db() as c:
        row = c.execute("""
            SELECT u.id as uid, ug.group_id as gid, ug.joined_date
            FROM user_groups ug
            JOIN groups g ON ug.group_id=g.id
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1 AND g.group_type='prep'
            LIMIT 1
        """, (phone,)).fetchone()
    if not row:
        return 0
    return count_report_days_since(row["uid"], row["gid"], row["joined_date"])


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
            SELECT g.* FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1
              AND (g.group_type='pro' OR g.group_type='relaxed' OR g.group_type IS NULL)
        """, (phone,)).fetchone()


def is_active_prep_student(phone):
    """Уже зарегистрирован в подготовительной группе (12.08.2026, фикс: ЛС
    /start у такого студента раньше показывало 'чтобы зарегистрироваться -
    напиши в группе' - неверно, он уже зарегистрирован, просто не в
    pro/relaxed, см. handlers.py)."""
    with db() as c:
        row = c.execute("""
            SELECT 1 FROM user_groups ug
            JOIN groups g ON ug.group_id=g.id
            JOIN users u ON u.id=ug.user_id
            WHERE u.phone=? AND ug.role='student' AND ug.active=1 AND g.group_type='prep'
            LIMIT 1
        """, (phone,)).fetchone()
    return row is not None


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
        # active=1 + свежий joined_date — при (пере)входе в группу пропуски считаются заново
        c.execute(
            "UPDATE user_groups SET active=1, joined_date=? WHERE user_id=? AND group_id=? AND role='student'",
            (get_date(), uid, group_id)
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


def cancel_task(student_id, group_id, task_code):
    today = get_date()
    with db() as c:
        c.execute(
            "DELETE FROM score_events"
            " WHERE student_id=? AND group_id=? AND date=? AND category='task' AND subcategory=?",
            (student_id, group_id, today, task_code)
        )


def save_report(uid, group_id, date, tasks_done):
    with db() as c:
        for key in ("m", "r", "t", "j", "n", "h"):
            if tasks_done.get(key):
                c.execute(
                    "INSERT OR IGNORE INTO score_events"
                    "(student_id,group_id,date,category,subcategory,points)"
                    " VALUES(?,?,?,'task',?,1)",
                    (uid, group_id, date, key)
                )


def get_today_report(uid, group_id=None):
    today = get_date()
    with db() as c:
        if group_id is not None:
            rows = c.execute(
                "SELECT subcategory FROM score_events"
                " WHERE student_id=? AND group_id=? AND date=? AND category='task'",
                (uid, group_id, today)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT subcategory FROM score_events"
                " WHERE student_id=? AND date=? AND category='task'",
                (uid, today)
            ).fetchall()
    if not rows:
        return None
    result = {k: False for k in ("m", "r", "t", "j", "n", "h")}
    for r in rows:
        if r["subcategory"] in result:
            result[r["subcategory"]] = True
    result["score"] = sum(1 for v in result.values() if v)
    return result


def save_voice_submission(student_id, group_id, chat_id, message_id, date, file_id=None):
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO voice_submissions"
            "(student_id,group_id,chat_id,message_id,date,sent_at,file_id)"
            " VALUES(?,?,?,?,?,?,?)",
            (student_id, group_id, chat_id, message_id, date, get_now().isoformat(), file_id)
        )


def mark_voice_reviewed(chat_id, message_id):
    with db() as c:
        c.execute(
            "UPDATE voice_submissions SET reviewed_at=?"
            " WHERE chat_id=? AND message_id=? AND reviewed_at IS NULL",
            (get_now().isoformat(), chat_id, message_id)
        )


def save_umar_review(chat_id, message_id, review_type, review_file_id=None, review_text=None):
    """Stage 0 (R&D таджвида, 23.07.2026): сохраняем сырой реплай ИМЕННО
    Умар устаза (CURRICULUM_REVIEWER_ID) на голосовую сдачу студента - его
    коррекции доверенный ground truth (25 лет с Кораном, хафиз, образование
    по Корану в Университете Медины). Реплаи других админов не пишем -
    только его. Без автотранскрипции - просто копим сырьё."""
    with db() as c:
        c.execute(
            "UPDATE voice_submissions SET review_type=?, review_file_id=?, review_text=?"
            " WHERE chat_id=? AND message_id=? AND review_type IS NULL",
            (review_type, review_file_id, review_text, chat_id, message_id)
        )


def get_voice_review_stats(group_id, date):
    """(всего, проверено, [(имя, sent_at) без проверки]) по студентам группы за дату.

    Считаем по студенту, не по отдельной сдаче: если хотя бы одно голосовое
    студента за день проверено — весь день по нему засчитан (остальные могут
    быть пересдачей того же урока по просьбе устаза, не отдельным заданием).
    Время сдачи для непроверенных — самая ранняя сдача студента за день.
    """
    with db() as c:
        rows = c.execute(
            "SELECT vs.student_id, vs.reviewed_at, vs.sent_at, u.name FROM voice_submissions vs"
            " JOIN users u ON u.id = vs.student_id"
            " WHERE vs.group_id=? AND vs.date=?"
            " ORDER BY vs.id",
            (group_id, date)
        ).fetchall()
    by_student = {}
    for r in rows:
        sid = r["student_id"]
        had_review, name, first_sent = by_student.get(sid, (False, r["name"], r["sent_at"]))
        by_student[sid] = (had_review or bool(r["reviewed_at"]), name, first_sent)
    total = len(by_student)
    reviewed = sum(1 for has_review, _, _ in by_student.values() if has_review)
    unreviewed = [(name, sent_at) for has_review, name, sent_at in by_student.values() if not has_review]
    return total, reviewed, unreviewed


# ── Лог AI-проверок (муфрадат/таджвид/нахв) — для контроля качества ────────────

def log_verify_check(student_id, group_id, checks, submitted_text, verdict, flagged, date):
    with db() as c:
        c.execute(
            "INSERT INTO verify_log(student_id,group_id,checks,submitted_text,verdict,flagged,date)"
            " VALUES(?,?,?,?,?,?,?)",
            (student_id, group_id, ", ".join(checks), submitted_text, verdict, int(flagged), date)
        )


def get_verify_log_for_date(date):
    with db() as c:
        return c.execute(
            "SELECT vl.*, u.name as student_name, g.title as group_title FROM verify_log vl"
            " JOIN users u ON u.id = vl.student_id"
            " JOIN groups g ON g.id = vl.group_id"
            " WHERE vl.date=? ORDER BY vl.id",
            (date,)
        ).fetchall()


# ── Программа обучения (нахв/таджвид по частям, с одобрением устаза) ───────────

def save_curriculum_part(subject, chapter, topic, part_number, part_total, order_index, content):
    with db() as c:
        cur = c.execute(
            "INSERT INTO curriculum_parts"
            "(subject,chapter,topic,part_number,part_total,order_index,content)"
            " VALUES(?,?,?,?,?,?,?)",
            (subject, chapter, topic, part_number, part_total, order_index, content)
        )
        return cur.lastrowid


def get_next_part_for_review(subject):
    """Следующая часть без черновика на одобрении (ещё не отправлена устазу)."""
    with db() as c:
        return c.execute(
            "SELECT * FROM curriculum_parts WHERE subject=? AND review_message_id IS NULL"
            " ORDER BY order_index LIMIT 1",
            (subject,)
        ).fetchone()


def count_pending_curriculum_review(subject):
    """Сколько частей уже отправлено устазу и ждут одобрения (буфер)."""
    with db() as c:
        row = c.execute(
            "SELECT COUNT(*) AS n FROM curriculum_parts WHERE subject=?"
            " AND review_message_id IS NOT NULL AND approved_at IS NULL",
            (subject,)
        ).fetchone()
        return row["n"]


def get_published_curriculum_content(subject):
    """Текст всех уже ОПУБЛИКОВАННЫХ частей по предмету (n/j), по порядку — для справочника AI-проверки.

    Раньше фильтровалось по approved_at, но с 08.07.2026 публикация идёт по расписанию
    БЕЗ обязательного одобрения устаза (см. get_next_part_to_publish) — approved_at
    у большинства опубликованных частей так и остаётся NULL. Фильтр по approved_at
    молча выкидывал из справочника почти всё уже отправленное студентам. published_at —
    правильный критерий: часть либо уже видна студентам (значит должна быть в справочнике),
    либо ещё нет (и рано её туда включать)."""
    with db() as c:
        rows = c.execute(
            "SELECT content FROM curriculum_parts WHERE subject=? AND published_at IS NOT NULL"
            " ORDER BY order_index",
            (subject,)
        ).fetchall()
        return "\n\n".join(r["content"] for r in rows)


def get_curriculum_content_for_reference(subject):
    """Текст ВСЕХ частей по предмету, включая ещё НЕ опубликованные студентам —
    для справочника AI-проверки. НЕ путать с get_published_curriculum_content():
    та специально гейтится published_at, потому что рассылка урока в группы
    завязана на тот же флаг. Здесь цель другая — фактическая точность модели
    (напр. место выхода буквы), а не то, что уже официально объявлено
    студентам. Раздел написан и вычитан заранее (реальные источники, тот же
    процесс, что и для уже опубликованных частей) — ждать рассылки, чтобы
    модель начала пользоваться готовым текстом, смысла нет (27.07.2026, кейс
    id=119/154/179 — модель путалась в ك/ق без эталона, хотя текст уже был
    готов и лежал в очереди на публикацию)."""
    with db() as c:
        rows = c.execute(
            "SELECT content FROM curriculum_parts WHERE subject=? ORDER BY order_index",
            (subject,)
        ).fetchall()
        return "\n\n".join(r["content"] for r in rows)


def set_curriculum_review_message(part_id, chat_id, message_id):
    with db() as c:
        c.execute(
            "UPDATE curriculum_parts SET review_chat_id=?, review_message_id=? WHERE id=?",
            (chat_id, message_id, part_id)
        )


def mark_curriculum_approved(chat_id, message_id):
    with db() as c:
        c.execute(
            "UPDATE curriculum_parts SET approved_at=?"
            " WHERE review_chat_id=? AND review_message_id=? AND approved_at IS NULL",
            (get_now().isoformat(), chat_id, message_id)
        )


def get_pending_curriculum_review_by_chat(chat_id):
    """Часть, отправленную в этот чат на одобрение и ещё не одобренную."""
    with db() as c:
        return c.execute(
            "SELECT * FROM curriculum_parts WHERE review_chat_id=? AND review_message_id IS NOT NULL"
            " AND approved_at IS NULL ORDER BY order_index LIMIT 1",
            (str(chat_id),)
        ).fetchone()


def mark_curriculum_approved_by_chat(chat_id):
    """Устаз ответил в личке текстом/реплаем (не обязательно реакцией) — тоже одобрение.
    Одно сообщение = одна часть (самая ранняя по очереди), не всё разом."""
    with db() as c:
        c.execute(
            "UPDATE curriculum_parts SET approved_at=? WHERE id = ("
            "  SELECT id FROM curriculum_parts WHERE review_chat_id=?"
            "  AND review_message_id IS NOT NULL AND approved_at IS NULL"
            "  ORDER BY order_index LIMIT 1"
            ")",
            (get_now().isoformat(), str(chat_id))
        )


def get_next_part_to_publish(subject):
    """Следующая часть по очереди, ещё не опубликованная.

    Решение от 08.07.2026: публикация идёт по расписанию без ожидания
    👍 от устаза (для нахва/таджвида, не для Корана/хадисов/хукмов —
    риск ниже, контент строго на основе реальных книг). Устаз всё
    равно видит черновик заранее через буфер request_curriculum_review
    и может указать на ошибку до или после публикации.
    """
    with db() as c:
        return c.execute(
            "SELECT * FROM curriculum_parts WHERE subject=?"
            " AND published_at IS NULL ORDER BY order_index LIMIT 1",
            (subject,)
        ).fetchone()


def count_unpublished_parts(subject):
    """Сколько частей ещё в очереди (не опубликовано) по предмету."""
    with db() as c:
        row = c.execute(
            "SELECT COUNT(*) as n FROM curriculum_parts WHERE subject=? AND published_at IS NULL",
            (subject,)
        ).fetchone()
    return row["n"] if row else 0


def mark_curriculum_published(part_id):
    with db() as c:
        c.execute(
            "UPDATE curriculum_parts SET published_at=? WHERE id=?",
            (get_now().isoformat(), part_id)
        )


def _active_dates(uid, limit=400):
    """Множество дат когда студент имел хоть одно событие."""
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT date FROM score_events WHERE student_id=? ORDER BY date DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
    return {r["date"] for r in rows}


def _group_joined_date(uid, group_id):
    """Дата (пере)активации студента в конкретной группе — граница отсчёта пропусков."""
    with db() as c:
        row = c.execute(
            "SELECT joined_date FROM user_groups WHERE user_id=? AND group_id=? AND role='student'",
            (uid, group_id)
        ).fetchone()
    return row["joined_date"] if row else None


def get_days_since_last_report(uid, group_id=None):
    tz = pytz.timezone(TZ)
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
    dates = _active_dates(uid)
    added = user["added_date"] if user else None
    if group_id:
        joined = _group_joined_date(uid, group_id)
        if joined and (not added or joined > added):
            added = joined
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
    dates = _active_dates(uid, limit=30)
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


def get_skip_count_month_detail(uid, group_id=None):
    """Детали окна подсчёта пропусков текущего месяца: начало/конец окна,
    сколько дней сдано, сколько всего дней в окне, сколько пропущено."""
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    today = datetime.now(tz).date()
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return None
        rows = c.execute(
            "SELECT DISTINCT date FROM score_events WHERE student_id=? AND date>=?",
            (uid, month_start)
        ).fetchall()
    dates = {r["date"] for r in rows}
    added = user["added_date"]
    if group_id:
        joined = _group_joined_date(uid, group_id)
        if joined and joined > added:
            added = joined
    start = max(month_start, added)
    end = (today - timedelta(days=1)).isoformat()
    total = 0
    submitted = 0
    d = datetime.strptime(start, "%Y-%m-%d").date()
    while d < today:
        total += 1
        if d.isoformat() in dates:
            submitted += 1
        d += timedelta(days=1)
    return {"start": start, "end": end, "total": total, "submitted": submitted, "missed": total - submitted}


def get_skip_count_month(uid, group_id=None):
    detail = get_skip_count_month_detail(uid, group_id)
    return detail["missed"] if detail else 0


def get_excuse_count_month(uid, group_id):
    """Сколько раз студент уже использовал узр в текущем календарном месяце
    в этой группе (12.08.2026, решение пользователя: лимит 3/месяц, дальше
    день считается обычным пропуском - EXCUSE_MONTHLY_LIMIT в handlers.py)."""
    tz = pytz.timezone(TZ)
    month_start = datetime.now(tz).replace(day=1).date().isoformat()
    with db() as c:
        row = c.execute(
            "SELECT COUNT(*) as cnt FROM score_events"
            " WHERE student_id=? AND group_id=? AND category='excuse' AND date>=?",
            (uid, group_id, month_start)
        ).fetchone()
    return row["cnt"] if row else 0


def get_miss_count_last_30_days(uid, group_id=None):
    tz = pytz.timezone(TZ)
    today = datetime.now(tz).date()
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return 30
    dates = _active_dates(uid, limit=60)
    added = user["added_date"]
    if group_id:
        joined = _group_joined_date(uid, group_id)
        if joined and joined > added:
            added = joined
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


def _full_task_dates(uid, group_id, group_tasks, limit=400, since_date=None):
    """Даты, когда студент сдал ВСЕ обязательные задания группы (узр не
    защищает) - для строгого стрика (07.08.2026, решение пользователя:
    "страйк есть страйк, обнуляется если не сдал все 3, даже если узр").
    Отдельно от _active_dates - та по-прежнему "хоть одно событие" для
    других метрик (пропуски, get_days_since_last_report и т.д.), их
    трогать не нужно."""
    if not group_tasks:
        return set()
    placeholders = ",".join("?" * len(group_tasks))
    since_clause = " AND date>=?" if since_date else ""
    params = [uid, group_id, *group_tasks]
    if since_date:
        params.append(since_date)
    params += [len(group_tasks), limit]
    with db() as c:
        rows = c.execute(
            "SELECT date FROM score_events"
            " WHERE student_id=? AND group_id=? AND category='task' AND subcategory IN (%s)%s"
            " GROUP BY date HAVING COUNT(DISTINCT subcategory)=?"
            " ORDER BY date DESC LIMIT ?" % (placeholders, since_clause),
            params
        ).fetchall()
    return {r["date"] for r in rows}


def get_full_task_days_count(uid, group_id, group_tasks):
    """Сколько дней студент сдал ВСЕ задания группы целиком (12.08.2026,
    решение пользователя для /mystats: "Дней выполнено" = полная сдача,
    та же логика, что у стрика, а не "хоть одно задание")."""
    return len(_full_task_dates(uid, group_id, group_tasks))


def get_streak_days(uid, group_id, group_tasks, for_date=None):
    """Серия дней подряд, когда сданы ВСЕ задания группы. Без явной даты
    (for_date=None, "прямо сейчас") - грейс на сегодня: если сегодняшний
    день ещё не закрыт, не обнуляем серию, считаем от вчера (07.08.2026,
    иначе счётчик на дисплее студента ежедневно падал в 0 до его же
    сегодняшней сдачи). Явная дата (используется для завершённых прошлых
    дней - утренний Тадаббур-отчёт, лидеры стрика) грейс не получает,
    там день уже закончился по определению."""
    tz = pytz.timezone(TZ)
    dates = _full_task_dates(uid, group_id, group_tasks)
    anchor = datetime.strptime(for_date, "%Y-%m-%d").date() if for_date else datetime.now(tz).date()
    if for_date is None and anchor.isoformat() not in dates:
        anchor -= timedelta(days=1)
    streak = 0
    for i in range(400):
        day = (anchor - timedelta(days=i)).isoformat()
        if day in dates:
            streak += 1
        else:
            break
    return streak


def get_group_streaks(group_id, group_tasks, for_date=None):
    """Текущие стрики всех студентов группы ОДНИМ SQL-запросом (12.08.2026,
    решение пользователя: избежать N+1 при выводе /rating на больших группах
    вроде Тадаббура - 113 активных студентов). "Остров" последовательных
    полных дней на студента через julianday(date) - ROW_NUMBER() (стандартный
    gaps-and-islands приём); берём только остров, оканчивающийся на anchor
    (тот же грейс на сегодня, что и в get_streak_days). Отсутствие student_id
    в результате значит стрик=0 - вызывающий код должен делать .get(uid, 0)."""
    if not group_tasks:
        return {}
    tz = pytz.timezone(TZ)
    anchor = datetime.strptime(for_date, "%Y-%m-%d").date() if for_date else datetime.now(tz).date()
    yesterday = anchor - timedelta(days=1)
    placeholders = ",".join("?" * len(group_tasks))
    with db() as c:
        rows = c.execute(
            "WITH full_days AS ("
            "  SELECT student_id, date FROM score_events"
            "  WHERE group_id=? AND category='task' AND subcategory IN (%s)"
            "  GROUP BY student_id, date HAVING COUNT(DISTINCT subcategory)=?"
            "), grouped AS ("
            "  SELECT student_id, date,"
            "         julianday(date) - ROW_NUMBER() OVER (PARTITION BY student_id ORDER BY date) AS grp"
            "  FROM full_days"
            "), runs AS ("
            "  SELECT student_id, MAX(date) AS run_end, COUNT(*) AS run_len"
            "  FROM grouped GROUP BY student_id, grp"
            ")"
            " SELECT student_id, run_end, run_len FROM runs WHERE run_end IN (?, ?)"
            % placeholders,
            (group_id, *group_tasks, len(group_tasks), anchor.isoformat(), yesterday.isoformat())
        ).fetchall()
    by_student = {}
    for r in rows:
        by_student.setdefault(r["student_id"], {})[r["run_end"]] = r["run_len"]
    result = {}
    for sid, ends in by_student.items():
        if anchor.isoformat() in ends:
            result[sid] = ends[anchor.isoformat()]
        elif for_date is None and yesterday.isoformat() in ends:
            result[sid] = ends[yesterday.isoformat()]
    return result


def check_no_skip_week(uid):
    tz = pytz.timezone(TZ)
    with db() as c:
        user = c.execute("SELECT added_date FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return False
    dates = _active_dates(uid, limit=7)
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


def add_bonus(uid, group_id, date, points, category, subcategory="", note=None):
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO score_events"
            "(student_id,group_id,date,category,subcategory,points,note)"
            " VALUES(?,?,?,?,?,?,?)",
            (uid, group_id, date, category, subcategory, points, note)
        )


def get_missing_students(group_id, group_tasks, date=None):
    students = get_students(group_id)
    check_date = date or get_date()
    result = []
    with db() as c:
        for s in students:
            has_excuse = c.execute(
                "SELECT 1 FROM score_events"
                " WHERE student_id=? AND group_id=? AND date=? AND category='excuse' LIMIT 1",
                (s["id"], group_id, check_date)
            ).fetchone()
            if has_excuse:
                continue
            task_rows = c.execute(
                "SELECT subcategory FROM score_events"
                " WHERE student_id=? AND group_id=? AND date=? AND category='task'",
                (s["id"], group_id, check_date)
            ).fetchall()
            done = {r["subcategory"] for r in task_rows}
            missing = [k for k in group_tasks if k not in done]
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
    """Возвращает (user_id, chat_id, elapsed) незарегистрированных старше days дней.
    elapsed нужен вызывающему коду для разных порогов по типу группы."""
    with db() as c:
        return c.execute(
            "SELECT user_id, chat_id, julianday('now') - julianday(joined_date) AS elapsed "
            "FROM unregistered_members WHERE julianday('now') - julianday(joined_date) >= ?",
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


def get_prep_students_active():
    """Все активные студенты prep-групп (проверка идёт по каждому ежедневно)."""
    with db() as c:
        return c.execute("""
            SELECT u.id, u.name, u.phone, g.id as group_id, g.chat_id, g.title,
                   g.fallback_chat_id, ug.joined_date,
                   julianday('now','localtime') - julianday(ug.joined_date) as elapsed
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE ug.role='student' AND ug.active=1
              AND g.group_type='prep'
        """).fetchall()


def count_report_days_since(uid, group_id, since_date):
    """Количество дней начиная с даты, когда сданы ВСЕ обязательные задания
    группы (для prep-проверки). Узр не считается.

    12.08.2026, решение пользователя: раньше засчитывался день с ЛЮБЫМ
    одним заданием - лазейка, которая противоречила решению устаза от
    19.07 (все три задания обязательны с первого дня, без поблажек для
    prep). Единый строгий критерий - та же логика, что у стрика
    (_full_task_dates), просто с нижней границей по дате вступления.
    Проверено на живых данных 12.08.2026 перед деплоем: ни один активный
    студент prep не был близко к порогу 5 дней, откат уже объявленного
    перехода никому не грозил."""
    with db() as c:
        tasks_row = c.execute("SELECT tasks FROM groups WHERE id=?", (group_id,)).fetchone()
    group_tasks = tasks_row["tasks"].split(",") if tasks_row and tasks_row["tasks"] else ["m", "r", "t"]
    return len(_full_task_dates(uid, group_id, group_tasks, since_date=since_date))


# ── Formatting helpers ────────────────────────────────────────────────────────


def get_today_avg(group_id, for_date=None):
    if for_date is None:
        for_date = get_date()
    with db() as c:
        result = c.execute("""
            SELECT ROUND(AVG(daily_score), 2) as avg FROM (
                SELECT e.student_id, COUNT(*) as daily_score
                FROM score_events e
                JOIN user_groups ug ON ug.user_id=e.student_id AND ug.group_id=e.group_id
                WHERE e.group_id=? AND e.date=? AND e.category='task'
                  AND ug.role='student' AND ug.active=1
                GROUP BY e.student_id
            )
        """, (group_id, for_date)).fetchone()
    return result["avg"] if result and result["avg"] else 0


def get_daily_task_counts(group_id, group_tasks, for_date):
    """Возвращает [{id, name, done, excused}] — сколько заданий каждый студент сдал в указанную дату."""
    with db() as c:
        students = c.execute("""
            SELECT u.id, u.name FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
        """, (group_id,)).fetchall()
        task_rows = c.execute(
            "SELECT student_id, subcategory FROM score_events"
            " WHERE group_id=? AND date=? AND category='task'",
            (group_id, for_date)
        ).fetchall()
        excuse_ids = {r["student_id"] for r in c.execute(
            "SELECT student_id FROM score_events"
            " WHERE group_id=? AND date=? AND category='excuse'",
            (group_id, for_date)
        ).fetchall()}
    task_map = {}
    for r in task_rows:
        task_map.setdefault(r["student_id"], set()).add(r["subcategory"])
    return [
        {"id": s["id"], "name": s["name"],
         "done": sum(1 for k in group_tasks if k in task_map.get(s["id"], set())),
         "excused": s["id"] in excuse_ids}
        for s in students
    ]


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
    """Возвращает текущий активный урок только если он открыт сегодня, иначе None."""
    lesson_id = get_setting(_LESSON_KEY + str(group_id))
    if not lesson_id:
        return None
    with db() as c:
        lesson = c.execute(
            "SELECT * FROM online_lessons WHERE id=?", (int(lesson_id),)
        ).fetchone()
    if not lesson or lesson["date"] != get_date():
        delete_setting(_LESSON_KEY + str(group_id))
        return None
    return lesson


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


def has_attendance_this_week(uid, group_id):
    from datetime import date, timedelta
    today = date.today()
    week_start = str(today - timedelta(days=today.weekday()))
    with db() as c:
        return c.execute(
            "SELECT 1 FROM score_events"
            " WHERE student_id=? AND group_id=? AND category='attendance' AND date>=?",
            (uid, group_id, week_start)
        ).fetchone() is not None


def has_attendance_in_week_of(uid, group_id, date_str):
    """Как has_attendance_this_week, но неделя считается от конкретной даты,
    не от 'сегодня' - нужно для attendance_confirm: подтверждение может
    прийти через часы/сутки после самого дня, к тому моменту "сегодня" уже
    другое (см. core/attendance_confirm.py)."""
    d = datetime.strptime(date_str, "%Y-%m-%d").date()
    week_start = str(d - timedelta(days=d.weekday()))
    week_end = str(d + timedelta(days=6 - d.weekday()))
    with db() as c:
        return c.execute(
            "SELECT 1 FROM score_events"
            " WHERE student_id=? AND group_id=? AND category='attendance' AND date>=? AND date<=?",
            (uid, group_id, week_start, week_end)
        ).fetchone() is not None


def get_or_create_attendance_confirm(group_id, date):
    """Возвращает (id, is_new). is_new=True - только что созданная запись
    (первый студент за день), значит нужно спросить устаза; False - уже
    была, значит студент просто добавляется в список ожидающих."""
    with db() as c:
        cur = c.execute(
            "INSERT OR IGNORE INTO attendance_confirm(group_id,date) VALUES(?,?)",
            (group_id, date)
        )
        is_new = cur.rowcount == 1
        row = c.execute(
            "SELECT id FROM attendance_confirm WHERE group_id=? AND date=?",
            (group_id, date)
        ).fetchone()
        return row["id"], is_new


def add_attendance_confirm_student(confirm_id, student_id):
    with db() as c:
        c.execute(
            "INSERT OR IGNORE INTO attendance_confirm_students(confirm_id,student_id) VALUES(?,?)",
            (confirm_id, student_id)
        )


def get_attendance_confirm_by_id(confirm_id):
    with db() as c:
        return c.execute(
            "SELECT * FROM attendance_confirm WHERE id=?", (confirm_id,)
        ).fetchone()


def get_attendance_confirm_students(confirm_id):
    with db() as c:
        return c.execute("""
            SELECT u.id, u.name, u.phone FROM attendance_confirm_students acs
            JOIN users u ON u.id=acs.student_id
            WHERE acs.confirm_id=?
        """, (confirm_id,)).fetchall()


def set_attendance_confirm_decision(confirm_id, decision, reason="manual"):
    with db() as c:
        c.execute(
            "UPDATE attendance_confirm SET decision=?, decided_at=datetime('now'), decision_reason=? WHERE id=?",
            (decision, reason, confirm_id)
        )


def get_stale_attendance_confirms(minutes):
    with db() as c:
        return c.execute("""
            SELECT * FROM attendance_confirm
            WHERE decision IS NULL AND escalated_at IS NULL
              AND asked_at <= datetime('now', ?)
        """, (f"-{minutes} minutes",)).fetchall()


def get_unresolved_after_escalation(hours):
    with db() as c:
        return c.execute("""
            SELECT * FROM attendance_confirm
            WHERE decision IS NULL AND escalated_at IS NOT NULL
              AND escalated_at <= datetime('now', ?)
        """, (f"-{hours} hours",)).fetchall()


def mark_attendance_confirm_escalated(confirm_id):
    with db() as c:
        c.execute(
            "UPDATE attendance_confirm SET escalated_at=datetime('now') WHERE id=?",
            (confirm_id,)
        )


def get_dm_ok(uid):
    """Писал ли пользователь боту в личку хотя бы раз (значит, бот может ему туда писать)."""
    with db() as c:
        row = c.execute("SELECT dm_ok FROM users WHERE id=?", (uid,)).fetchone()
    return bool(row and row["dm_ok"])


def get_dm_ok_by_phone(phone):
    """То же самое, но по Telegram-id — не привязано к роли (студент/устаз/суперадмин),
    в отличие от get_dm_ok не требует, чтобы вызывающий уже был студентом с известным users.id."""
    with db() as c:
        row = c.execute("SELECT dm_ok FROM users WHERE phone=?", (phone,)).fetchone()
    return bool(row and row["dm_ok"])


def mark_dm_ok(uid):
    with db() as c:
        c.execute("UPDATE users SET dm_ok=1 WHERE id=? AND dm_ok=0", (uid,))


def mark_dm_ok_by_phone(phone):
    """Отмечает, что боту можно писать этому Telegram-id первым. Если строки в users ещё
    нет (например суперадмин или устаз, который никогда не проходил студенческую
    регистрацию) — создаёт её с пустым именем; add_student потом сам подставит
    настоящее имя в такую запись (UPDATE ... WHERE name='')."""
    with db() as c:
        c.execute(
            "INSERT INTO users(name, phone, dm_ok) VALUES('', ?, 1) "
            "ON CONFLICT(phone) DO UPDATE SET dm_ok=1",
            (phone,)
        )


# ── Анкета "откуда и сколько лет" (13.08.2026, редизайн 17.08.2026) ─────────────

def get_users_due_for_survey():
    """Активные студенты уже в постоянной группе (pro/relaxed), с момента
    перевода туда (user_groups.joined_date) прошло ≥2 дня, анкета ещё не
    начата. Триггер сменён с "30 дней после регистрации" на "2 дня после
    перевода в постоянную группу" (17.08.2026, решение пользователя - у
    старых студентов между регистрацией и реальным началом мог быть
    большой разрыв). dm_ok=0 просто не попадают сюда - если появится
    позже, подхватятся в один из следующих ежедневных прогонов.

    Устазы/админы, которые ГДЕ-ТО ТОЖЕ студенты (активная роль 'student' в
    какой-то группе), теперь ВКЛЮЧЕНЫ - общая политика с 17.08.2026
    (решение пользователя: сам такой, "я студент"). Раньше (13.08.2026) их
    исключали - тогда перехват ответа анкеты в handlers.py ничем не был
    ограничен по времени, и застрявший навсегда 'survey_stage' мог
    перехватить обычную команду устаза как ответ на анкету. Теперь это
    больше не проблема - ответ засчитывается только в 24-часовом окне
    (survey_answer_in_window), вне его сообщение не перехватывается вообще.
    Чистых админов без активной роли 'student' нигде (например Умар устаз)
    это не касается в принципе - они и так не проходят JOIN по
    role='student' ниже, фильтровать их отдельно не нужно.

    Без LIMIT - раньше был батч по 5/день из осторожности, снято прямым
    решением пользователя 17.08.2026 (разовый запуск всем подходящим
    сразу; дальше пополнение органическое, по мере перевода новых)."""
    with db() as c:
        return c.execute("""
            SELECT DISTINCT u.id, u.name, u.phone
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE ug.role='student' AND ug.active=1
              AND u.phone IS NOT NULL AND u.dm_ok=1
              AND (u.survey_stage IS NULL OR u.survey_stage='')
              AND (g.group_type='pro' OR g.group_type='relaxed' OR g.group_type IS NULL)
              AND julianday('now') - julianday(ug.joined_date) >= 2
            ORDER BY ug.joined_date ASC
        """).fetchall()


def get_users_due_for_survey_nudge(days=7):
    """Застряли на 'asked_location'/'asked_age' ≥N дней без ответа - повтор
    ТОГО ЖЕ вопроса (не с начала), еженедельно, пока не ответят
    (17.08.2026). Заодно частично лечит случаи, когда dm_ok=1 в базе
    устарел и первая отправка реально не дошла - повтор через неделю
    попробует снова. Устазов-студентов не исключает, симметрично
    get_users_due_for_survey (17.08.2026, общая политика)."""
    with db() as c:
        return c.execute("""
            SELECT DISTINCT u.id, u.name, u.phone, u.survey_stage
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            JOIN groups g ON ug.group_id=g.id
            WHERE ug.role='student' AND ug.active=1
              AND u.phone IS NOT NULL AND u.dm_ok=1
              AND (g.group_type='pro' OR g.group_type='relaxed' OR g.group_type IS NULL)
              AND u.survey_stage IN ('asked_location', 'asked_age', 'asked_age_retry')
              AND julianday('now') - julianday(u.survey_stage_at) >= ?
        """, (days,)).fetchall()


def start_survey(phone):
    with db() as c:
        c.execute(
            "UPDATE users SET survey_stage='asked_location', survey_stage_at=datetime('now') WHERE phone=?",
            (phone,)
        )


def touch_survey_stage(phone):
    """Сбрасывает таймер 'молчит N дней' после повторной отправки того же
    вопроса (nudge) - иначе следующий прогон резенднул бы снова сразу же."""
    with db() as c:
        c.execute("UPDATE users SET survey_stage_at=datetime('now') WHERE phone=?", (phone,))


def get_survey_stage(phone):
    with db() as c:
        row = c.execute("SELECT survey_stage FROM users WHERE phone=?", (phone,)).fetchone()
    return row["survey_stage"] if row else None


def save_survey_location(phone, text):
    with db() as c:
        c.execute(
            "UPDATE users SET survey_location=?, survey_stage='asked_age', "
            "survey_stage_at=datetime('now') WHERE phone=?",
            (text, phone)
        )


def _parse_birth_year(text):
    """Возраст из свободного текста ('23', 'мне 23', '23 года') -> год
    рождения. Если в тексте похоже на прямой год рождения (4 цифры,
    1925-совр.год-5) - берёт его как есть. Возраст ограничен разумными
    рамками (5-100 лет) - на бессмысленный ответ возвращает None, а не
    случайное число (17.08.2026)."""
    nums = re.findall(r"\d+", text or "")
    if not nums:
        return None
    current_year = get_now().year
    for n in nums:
        val = int(n)
        if 1925 <= val <= current_year - 5:
            return val
    for n in nums:
        age = int(n)
        if 5 <= age <= 100:
            return current_year - age
    return None


def save_survey_age(phone, text):
    """Возвращает новый survey_stage ('asked_age_retry' или 'done'), чтобы
    handlers.py знал, какое сообщение отправить в ответ. Если год рождения
    не распознан - переспрашивает один раз ('asked_age_retry'); если и
    повторный ответ не распознан - принимает как есть, не мучает дальше
    (17.08.2026)."""
    birth_year = _parse_birth_year(text)
    with db() as c:
        row = c.execute("SELECT survey_stage FROM users WHERE phone=?", (phone,)).fetchone()
        is_retry = bool(row and row["survey_stage"] == "asked_age_retry")
        if birth_year is None and not is_retry:
            c.execute(
                "UPDATE users SET survey_age=?, survey_stage='asked_age_retry', "
                "survey_stage_at=datetime('now') WHERE phone=?",
                (text, phone)
            )
            return "asked_age_retry"
        c.execute(
            "UPDATE users SET survey_age=?, survey_birth_year=?, survey_stage='done', "
            "survey_stage_at=datetime('now') WHERE phone=?",
            (text, birth_year, phone)
        )
        return "done"


def survey_answer_in_window(phone, hours=24):
    """Прошло ли меньше `hours` часов с момента как был задан текущий вопрос
    анкеты. Нужно, чтобы не перехватывать случайное сообщение, пришедшее
    спустя дни после вопроса, как будто это ответ на анкету (17.08.2026,
    пользователь: "чтобы мы поняли что это точно ответы на анкету"). Если
    окно прошло - вопрос остаётся висеть, откроется заново еженедельным
    повтором (profile_survey_nudge)."""
    with db() as c:
        row = c.execute(
            "SELECT (julianday('now') - julianday(survey_stage_at)) * 24 AS hours_passed "
            "FROM users WHERE phone=?", (phone,)
        ).fetchone()
    return bool(row and row["hours_passed"] is not None and row["hours_passed"] <= hours)


# ── Formatting ─────────────────────────────────────────────────────────────────

def format_daily_report(group_id, group_title, group_tasks, for_date=None, submitted_only=False):
    from core.content import DEFAULT_TASKS
    if for_date is None:
        for_date = get_date()
    date_str = datetime.strptime(for_date, "%Y-%m-%d").strftime("%d.%m.%Y")
    with db() as c:
        students = c.execute("""
            SELECT u.id, u.name FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            ORDER BY u.name
        """, (group_id,)).fetchall()
        task_rows = c.execute(
            "SELECT student_id, subcategory FROM score_events"
            " WHERE group_id=? AND date=? AND category='task'",
            (group_id, for_date)
        ).fetchall()
        excuse_ids = {r["student_id"] for r in c.execute(
            "SELECT student_id FROM score_events"
            " WHERE group_id=? AND date=? AND category='excuse'",
            (group_id, for_date)
        ).fetchall()}

    task_map = {}
    for r in task_rows:
        task_map.setdefault(r["student_id"], set()).add(r["subcategory"])

    total_tasks = len(group_tasks)
    legend = "  ".join(DEFAULT_TASKS[k] for k in group_tasks)
    lines = ["📋 Отчёт — " + group_title + " за " + date_str + "\n"]
    lines.append("Порядок заданий:\n" + legend + "\n")

    students_sorted = sorted(
        students,
        key=lambda s: (-sum(1 for k in group_tasks if k in task_map.get(s["id"], set())), s["name"])
    )

    done_count = 0
    for s in students_sorted:
        sid = s["id"]
        done = task_map.get(sid, set())
        cnt = sum(1 for k in group_tasks if k in done)
        if cnt > 0:
            done_count += 1
        if sid in excuse_ids and cnt == 0:
            if not submitted_only:
                lines.append(s["name"] + ": ⛔ узр")
            continue
        if submitted_only and cnt == 0:
            continue
        marks = "".join("✅" if k in done else "❌" for k in group_tasks)
        celebrate = " 🎉" if cnt == total_tasks else ""
        lines.append(s["name"] + ": " + marks + " " + str(cnt) + "/" + str(total_tasks) + celebrate)

    lines.append("\n📊 Сдали хоть что-то: " + str(done_count) + "/" + str(len(students)))
    lines.append("📈 Средний балл сегодня: " + str(get_today_avg(group_id)))
    return "\n".join(lines)


def get_period_winner(group_id, days):
    start = (datetime.now(pytz.timezone(TZ)).date() - timedelta(days=days - 1)).isoformat()
    with db() as c:
        return c.execute("""
            SELECT u.name, COALESCE(SUM(e.points),0) as points
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN score_events e ON u.id=e.student_id AND e.group_id=? AND e.date>=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            GROUP BY u.id ORDER BY points DESC LIMIT 1
        """, (group_id, start, group_id)).fetchone()


def get_period_winner_range(group_id, start, end):
    """Лидер за закрытый календарный период (квартал/полугодие/год) -
    в отличие от get_period_winner (скользящее окно "N дней назад по
    сегодня"), тут границы фиксированные с обеих сторон (07.08.2026)."""
    with db() as c:
        return c.execute("""
            SELECT u.name, COALESCE(SUM(e.points),0) as points
            FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            LEFT JOIN score_events e ON u.id=e.student_id AND e.group_id=? AND e.date>=? AND e.date<=?
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
            GROUP BY u.id ORDER BY points DESC LIMIT 1
        """, (group_id, start, end, group_id)).fetchone()


def format_period_report(group_id, group_title, group_tasks, days=None, start=None, end=None, label=None):
    """days - скользящее окно "N дней назад по сегодня" (/week, /month, /year -
    handlers.py). Либо явные календарные start/end/label (квартал/полугодие/
    год - quarterly_leaders_report, 07.08.2026) - тогда days не нужен."""
    tz = pytz.timezone(TZ)
    today = datetime.now(tz).date()
    if start is None:
        start = (today - timedelta(days=days - 1)).isoformat()
    if end is None:
        end = today.isoformat()
    if label is None:
        label = "неделю" if days == 7 else ("месяц" if days == 30 else ("год" if days == 365 else str(days) + " дн."))
    with db() as c:
        students = c.execute("""
            SELECT u.id, u.name FROM users u
            JOIN user_groups ug ON u.id=ug.user_id
            WHERE ug.group_id=? AND ug.role='student' AND ug.active=1
        """, (group_id,)).fetchall()
        task_agg = c.execute("""
            SELECT student_id,
                   COUNT(*) as task_points,
                   COUNT(DISTINCT date) as days_done
            FROM score_events
            WHERE group_id=? AND date>=? AND date<=? AND category='task'
            GROUP BY student_id
        """, (group_id, start, end)).fetchall()
        bonus_agg = c.execute("""
            SELECT student_id, COALESCE(SUM(points),0) as bonus
            FROM score_events
            WHERE group_id=? AND date>=? AND date<=? AND category != 'task'
            GROUP BY student_id
        """, (group_id, start, end)).fetchall()

    task_map  = {r["student_id"]: (r["task_points"], r["days_done"]) for r in task_agg}
    bonus_map = {r["student_id"]: r["bonus"] for r in bonus_agg}

    results = []
    for s in students:
        sid = s["id"]
        task_pts, days_done = task_map.get(sid, (0, 0))
        bonus = bonus_map.get(sid, 0)
        results.append((s["name"], task_pts + bonus, days_done, bonus))
    results.sort(key=lambda x: -x[1])

    medals = ["🥇", "🥈", "🥉"]

    def day_word(n):
        return "день" if n == 1 else ("дня" if 2 <= n <= 4 else "дней")

    lines = ["📊 Отчёт за " + label + " — " + group_title + ":\n"]
    for i, (name, total, days_done, bonus) in enumerate(results):
        medal = medals[i] if i < 3 else str(i + 1) + "."
        bonus_str = " (+{} бонус)".format(bonus) if bonus > 0 else ""
        lines.append(
            medal + " " + name + " — 💎 " + str(total) + " очков"
            + " (" + str(days_done) + " " + day_word(days_done) + ")" + bonus_str
        )
    with db() as c:
        lessons = c.execute(
            "SELECT id, date FROM online_lessons WHERE group_id=? AND date>=? AND date<=? ORDER BY date",
            (group_id, start, end)
        ).fetchall()
    if lessons:
        total_students = len(students)
        lines.append("\n📡 Онлайн уроки:")
        with db() as c:
            for l in lessons:
                names = [r["name"] for r in c.execute(
                    "SELECT u.name FROM attendance a JOIN users u ON a.sid=u.id WHERE a.lesson_id=?",
                    (l["id"],)
                ).fetchall()]
                date_str = datetime.strptime(l["date"], "%Y-%m-%d").strftime("%d.%m")
                header = "  • " + date_str + " — " + str(len(names)) + " из " + str(total_students) + " студентов"
                if names:
                    header += ": " + ", ".join(names)
                lines.append(header)

    return "\n".join(lines)
