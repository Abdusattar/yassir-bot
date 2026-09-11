"""Уроки в приложении (11.09.2026) — раздел «Знания».

Каждый четверг бот публикует в группы очередную часть по таджвиду и нахву
(`publish_curriculum_parts` в планировщике). Прочитать её можно было только в
Telegram, и через неделю-две она уходила вверх по чату насовсем. Здесь всё
опубликованное лежит по главам и открывается в любой момент.

Два правила, важные для понимания:

* **«Открыт» = `published_at IS NOT NULL`.** Отдельного переключателя нет и не
  нужно: урок открывается сам, когда четверговая рассылка его отправила.
  `approved_at` для этого не годится — с 08.07.2026 публикация идёт без
  обязательного одобрения устаза, и у большинства опубликованных частей он
  так и остаётся пустым (та же ловушка описана в
  `get_published_curriculum_content`).
* **Закрытый урок виден, но не читается.** В списке его название показано
  приглушённым — так видно, что впереди. Содержимое закрытого урока сервер не
  отдаёт вовсе: спрятать его только на клиенте значило бы раздать всю
  программу вперёд любому, кто откроет вкладку сети.

Базы у мужского и женского ботов разные, и очереди у них идут вразнобой (на
11.09.2026 по таджвиду открыто 9 частей из 12 у мужчин и 4 из 12 у женщин).
Каждый процесс читает свою базу, поэтому ничего сводить не нужно.
"""
import logging

from core.db import db

log = logging.getLogger(__name__)

# Предмет в `curriculum_parts.subject` — та же буква, что и у задания в
# `groups.tasks` (см. _SUBJECT_TASK_KEY в планировщике).
SUBJECTS = (
    {"id": "j", "title": "Таджвид", "sub": "Махаридж, сифаты", "mark": "📘"},
    {"id": "n", "title": "Нахв", "sub": "Слово, число, и‘раб", "mark": "📗"},
)


def subjects_overview():
    """Предметы со счётом «открыто из всего» — для блока «Уроки»."""
    try:
        with db() as c:
            rows = c.execute("""
                SELECT subject,
                       count(*) total,
                       sum(CASE WHEN published_at IS NOT NULL THEN 1 ELSE 0 END) open
                FROM curriculum_parts GROUP BY subject
            """).fetchall()
    except Exception as e:
        log.error("subjects_overview error: %s: %s", type(e).__name__, e)
        return []
    by_id = {r["subject"]: r for r in rows}
    out = []
    for s in SUBJECTS:
        r = by_id.get(s["id"])
        if not r or not r["total"]:
            continue                      # предмета в базе нет — и раздела нет
        out.append(dict(s, open=r["open"] or 0, total=r["total"]))
    return out


def lessons_of(subject):
    """Части предмета по порядку: глава, тема, открыт ли и когда открылся.

    Содержимое здесь НЕ отдаём даже для открытых — список может быть длинным,
    а весь текст программы в одном ответе не нужен ни разу."""
    try:
        with db() as c:
            rows = c.execute("""
                SELECT id, chapter, topic, part_number, part_total, published_at
                FROM curriculum_parts WHERE subject=? ORDER BY order_index
            """, (subject,)).fetchall()
    except Exception as e:
        log.error("lessons_of error: %s: %s", type(e).__name__, e)
        return []
    return [{
        "id": r["id"],
        "chapter": r["chapter"],
        "topic": r["topic"],
        "part": r["part_number"],
        "parts": r["part_total"],
        "open": bool(r["published_at"]),
        "at": (r["published_at"] or "")[:10],
    } for r in rows]


def lesson(part_id):
    """Один урок с текстом — только если он уже открыт.

    Закрытый возвращает None, а не текст с пометкой: программа вперёд не
    раздаётся, и решать это на клиенте нельзя."""
    try:
        with db() as c:
            r = c.execute("""
                SELECT id, subject, chapter, topic, part_number, part_total,
                       content, published_at
                FROM curriculum_parts WHERE id=?
            """, (int(part_id),)).fetchone()
    except Exception as e:
        log.error("lesson error: %s: %s", type(e).__name__, e)
        return None
    if not r or not r["published_at"]:
        return None
    return {
        "id": r["id"],
        "subject": r["subject"],
        "chapter": r["chapter"],
        "topic": r["topic"],
        "part": r["part_number"],
        "parts": r["part_total"],
        "content": r["content"],
        "at": (r["published_at"] or "")[:10],
    }
