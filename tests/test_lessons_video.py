"""Видеоуроки таджвида (10.11.2026): id ролика — по номеру урока в предмете."""
import core.db as db
from core import lessons


def _part(subject, topic, order, published="2026-07-01"):
    with db.db() as c:
        return c.execute(
            "INSERT INTO curriculum_parts(subject, chapter, topic, part_number, part_total,"
            " order_index, content, published_at) VALUES(?,'Глава',?,1,1,?,?,?)",
            (subject, topic, order, "текст " + topic, published)).lastrowid


def test_video_by_lesson_rank(test_db):
    ids = [_part("j", "Урок %d" % n, order=n * 10) for n in range(1, 13)]
    nahw = _part("n", "Исм", order=1)
    items = lessons.lessons_of("j")
    assert [it["video"] for it in items] == [True] * 10 + [False, False]
    first = lessons.lesson(ids[0])
    assert first["video"] == lessons.LESSON_VIDEOS["j"][0]
    tenth = lessons.lesson(ids[9])
    assert tenth["video"] == lessons.LESSON_VIDEOS["j"][9]
    assert lessons.lesson(ids[10])["video"] is None
    assert lessons.lesson(nahw)["video"] is None


def test_closed_lesson_gives_nothing(test_db):
    pid = _part("j", "Закрытый", order=1, published=None)
    assert lessons.lesson(pid) is None
