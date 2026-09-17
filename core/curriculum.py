"""Лекции по группам и открытие предметов по позиции заучивания (17.09.2026).

Было: очередь лекций одна на базу. Часть считалась открытой, когда у неё
стоял `curriculum_parts.published_at`, и уходила сразу во все группы с этим
предметом. Группа, которая начинает таджвид в ноябре, получила бы двадцатую
лекцию вместо первой.

Стало: у каждой группы свой счёт. Открыто группе то, что лежит в
`group_lessons`; четверговая рассылка даёт каждой группе ЕЁ следующую часть.
`published_at` остался и значит «часть хоть раз ушла студентам» - по нему
живут справочник ИИ-проверки и вид устаза.

Правило пользователя (17.09.2026):

* 70% группы прошли полджуза заучивания - группе открывается таджвид;
  70% прошли первый джуз - нахв. Учат с Аль-Бакары (стр. 2), джуз - 20
  страниц: указатель заучивания на стр. 12 / 22 и дальше. Считаются ВСЕ
  активные студенты; без указателя - «не прошёл».
* Группу предупреждаем за неделю (важное сообщение типа task), первая лекция
  выходит в ближайший четверг после этой недели, дальше по одной в неделю.
* Задание (j / n) включается не с первой лекцией, а когда в тренажёре есть
  что сдавать: вводные лекции таджвида без букв только читают.
* Обратно ничего не выключается: пришли новички, доля упала - предмет остаётся.

Проверка готовности молчит до AUTO_OPEN_FROM: до конца волн перехода на
YassirApp (28.09.2026) у многих нет указателя заучивания, и 70% не набрать.
"""
import logging
from datetime import date, timedelta

from core.db import db, get_date, get_group_tasks, get_students, update_group_tasks

log = logging.getLogger(__name__)

AUTO_OPEN_FROM = "2026-09-29"
READY_SHARE = 0.7
NOTICE_DAYS = 7
LESSON_WEEKDAY = 3                      # четверг, как publish_curriculum_parts
# Предмет -> с какой страницы указателя заучивания студент «прошёл» порог.
READY_PAGE = {"j": 12, "n": 22}
SUBJECT_LABEL = {"j": "Таджвид", "n": "Нахв"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS group_lessons(
    group_id INTEGER NOT NULL,
    part_id INTEGER NOT NULL,
    opened_at TEXT NOT NULL,
    PRIMARY KEY(group_id, part_id)
);
CREATE TABLE IF NOT EXISTS group_subject_start(
    group_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    announced_at TEXT NOT NULL,
    start_date TEXT NOT NULL,
    PRIMARY KEY(group_id, subject)
);
"""


def init():
    """Таблицы и разовый перенос: группам, у которых предмет уже в заданиях,
    открыто всё опубликованное - для них ничего не меняется."""
    with db() as c:
        c.executescript(_SCHEMA)
        done = c.execute("SELECT 1 FROM bot_settings WHERE key='group_lessons_backfilled'").fetchone()
    if not done:
        backfill()
        with db() as c:
            c.execute("INSERT OR REPLACE INTO bot_settings(key, value) VALUES('group_lessons_backfilled','1')")


def backfill():
    """Всё опубликованное - группам, у которых предмет в заданиях. Повторный
    запуск ничего не портит (INSERT OR IGNORE)."""
    with db() as c:
        groups = c.execute("SELECT id, tasks FROM groups").fetchall()
        parts = c.execute("SELECT id, subject, published_at FROM curriculum_parts"
                          " WHERE published_at IS NOT NULL").fetchall()
        for g in groups:
            tasks = [t.strip() for t in (g["tasks"] or "").split(",")]
            for p in parts:
                if p["subject"] in tasks:
                    c.execute("INSERT OR IGNORE INTO group_lessons(group_id, part_id, opened_at)"
                              " VALUES(?,?,?)", (g["id"], p["id"], p["published_at"]))


# ── что открыто группе ──────────────────────────────────────────────────────

def opened_parts(group_id, subject):
    """{part_id: opened_at} - открытое этой группе по предмету."""
    with db() as c:
        rows = c.execute(
            "SELECT gl.part_id, gl.opened_at FROM group_lessons gl"
            " JOIN curriculum_parts p ON p.id=gl.part_id WHERE gl.group_id=? AND p.subject=?",
            (group_id, subject)).fetchall()
    return {r["part_id"]: r["opened_at"] for r in rows}


def opened_subjects(group_id):
    with db() as c:
        rows = c.execute(
            "SELECT DISTINCT p.subject FROM group_lessons gl"
            " JOIN curriculum_parts p ON p.id=gl.part_id WHERE gl.group_id=?", (group_id,)).fetchall()
    return {r["subject"] for r in rows}


def topics(subject, group_id=None):
    """Темы открытых частей. group_id=None - всё опубликованное в базе
    (устаз, супер-админ: они ведут разные группы)."""
    with db() as c:
        if group_id is None:
            rows = c.execute("SELECT topic FROM curriculum_parts"
                             " WHERE subject=? AND published_at IS NOT NULL", (subject,)).fetchall()
        else:
            rows = c.execute(
                "SELECT p.topic FROM group_lessons gl JOIN curriculum_parts p ON p.id=gl.part_id"
                " WHERE gl.group_id=? AND p.subject=?", (group_id, subject)).fetchall()
    return [r["topic"] or "" for r in rows]


def user_group_id(user_id):
    """Группа, по счёту которой человеку открыты лекции. None - устаз,
    супер-админ или человек без учебной группы: им всё опубликованное."""
    from config import SUPER_ADMIN_IDS
    from core.db import get_admin_groups, get_learning_group
    uid = str(user_id)
    if uid in SUPER_ADMIN_IDS or get_admin_groups(uid):
        return None
    group = get_learning_group(uid, include_prep=True)
    return group["id"] if group else None


def next_part(group_id, subject):
    """Следующая по порядку часть, ещё не открытая группе."""
    with db() as c:
        return c.execute(
            "SELECT * FROM curriculum_parts p WHERE p.subject=? AND NOT EXISTS("
            "  SELECT 1 FROM group_lessons gl WHERE gl.group_id=? AND gl.part_id=p.id)"
            " ORDER BY p.order_index LIMIT 1", (subject, group_id)).fetchone()


def open_part(group_id, part_id):
    with db() as c:
        c.execute("INSERT OR IGNORE INTO group_lessons(group_id, part_id, opened_at) VALUES(?,?,?)",
                  (group_id, part_id, get_date()))


# ── начало предмета у группы ────────────────────────────────────────────────

def subject_start(group_id, subject):
    with db() as c:
        return c.execute("SELECT * FROM group_subject_start WHERE group_id=? AND subject=?",
                         (group_id, subject)).fetchone()


def lessons_go(group, subject, today=None):
    """Шлёт ли четверговая рассылка этот предмет группе: предмет уже в
    заданиях, либо группа предупреждена и день начала наступил."""
    if subject in get_group_tasks(group):
        return True
    row = subject_start(group["id"], subject)
    return bool(row) and row["start_date"] <= (today or get_date())


def trainer_has_content(subject, group_id):
    """Есть ли группе что сдавать в тренажёре - тогда и включается задание."""
    got = topics(subject, group_id)
    if subject == "j":
        from core.tajweed_trainer import CARDS
        return any(t.startswith(card["lesson"]) for card in CARDS for t in got)
    if subject == "n":
        from core.nahw_trainer import SKILLS
        first = SKILLS[0]["lesson"]
        return bool(first) and any(t.startswith(first) for t in got)
    return False


def enable_task_if_ready(group, subject):
    """True - задание включено сейчас."""
    tasks = get_group_tasks(group)
    if subject in tasks or not trainer_has_content(subject, group["id"]):
        return False
    update_group_tasks(group["chat_id"], ",".join(tasks + [subject]))
    log.info("curriculum: группе %s включено задание %s", group["title"], subject)
    return True


# ── готовность по позиции заучивания ────────────────────────────────────────

def readiness(group_id):
    """{"total", "with_pointer", "j": n, "n": n} - сколько студентов прошли
    порог каждого предмета."""
    from core.mushaf_words import get_hifz_pointer
    students = get_students(group_id)
    pages = []
    for s in students:
        ptr = get_hifz_pointer(s["phone"]) if s["phone"] else None
        if ptr and ptr.get("page"):
            pages.append(int(ptr["page"]))
    out = {"total": len(students), "with_pointer": len(pages)}
    for subject, page in READY_PAGE.items():
        out[subject] = sum(1 for p in pages if p >= page)
    return out


def is_ready(stats, subject):
    return stats["total"] > 0 and stats[subject] / stats["total"] >= READY_SHARE


def first_lesson_date(today):
    """Ближайший четверг не раньше чем через NOTICE_DAYS."""
    d = date.fromisoformat(today) + timedelta(days=NOTICE_DAYS)
    while d.weekday() != LESSON_WEEKDAY:
        d += timedelta(days=1)
    return d.isoformat()


def announce_start(group_id, subject, today=None):
    """Записать, что группа предупреждена. Возвращает дату первой лекции."""
    today = today or get_date()
    start = first_lesson_date(today)
    with db() as c:
        c.execute("INSERT OR IGNORE INTO group_subject_start(group_id, subject, announced_at, start_date)"
                  " VALUES(?,?,?,?)", (group_id, subject, today, start))
    return start
