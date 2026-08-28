"""Личный список "Мои слова" - слова со страницы чтения мусхафа, отмеченные
студентом двойным тапом/кликом для повторения (29.08.2026, "встретил
забытое слово по ходу чтения, хочу вернуться к нему потом"). Простой
список арабский+перевод для чтения - клик по строке никуда не ведёт, не
квиз (решение пользователя 29.08.2026, первый заход).

Идентификатор слова - (surah, ayah, position) из данных страницы чтения
(mushaf_data/page*.json, scripts/export_mushaf_page.py), НЕ progress_key
mufradat_words - та база покрывает только суры 2-10, а читают по всей
книге.

Интеграция с тренажёром (29.08.2026, второй заход - решение пользователя
"их надо обязательно прогонять в тренажёре") - ЧАСТИЧНАЯ, ограничена тем
же покрытием сур 2-10: при добавлении слова пытаемся сразу разрешить его
progress_key (совпадение по surah/ayah/position с mufradat_words, язык
'ru' - тот же язык, каким страница чтения экспортирует переводы, см.
scripts/export_mushaf_page.py:get_ayah_words). Не нашли - progress_key
остаётся NULL, слово просто списком для чтения, как и было изначально
(суры вне 2-10 тренажёр физически не может ни задать вопросом, ни
засчитать серию верных ответов - см. память проекта
project_mufradat_local_full_quran_data про будущую отдельную
синхронизацию полной базы на прод)."""
import sqlite3
from datetime import datetime, timezone

from core.sampler import HADITHS_DB

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mushaf_starred_words(
        user_id TEXT NOT NULL,
        surah INTEGER NOT NULL,
        ayah INTEGER NOT NULL,
        position INTEGER NOT NULL,
        arabic_html TEXT NOT NULL,
        translation TEXT NOT NULL,
        added_at TEXT NOT NULL,
        progress_key INTEGER,
        PRIMARY KEY (user_id, surah, ayah, position)
    )
"""

# Тот же язык, каким страница чтения экспортирует переводы (SOURCE_LANGUAGE
# в scripts/export_mushaf_page.py) - иначе progress_key просто не найдётся
# (mufradat_words хранит несколько языков в одной таблице).
_LANGUAGE = "ru"


def _ensure_schema(conn):
    conn.execute(_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mushaf_starred_words)")}
    if "progress_key" not in cols:
        conn.execute("ALTER TABLE mushaf_starred_words ADD COLUMN progress_key INTEGER")


def _resolve_progress_key(conn, surah, ayah, position):
    row = conn.execute(
        "SELECT progress_key FROM mufradat_words WHERE surah_number=? AND ayah_number=? "
        "AND position=? AND language=?",
        (surah, ayah, position, _LANGUAGE)
    ).fetchone()
    return row[0] if row else None


def add_starred_word(user_id, surah, ayah, position, arabic_html, translation):
    """Идемпотентно (INSERT OR IGNORE) - двойной тап на уже добавленном
    слове на странице чтения молча ничего не меняет, не убирает его. На
    странице чтения нет визуальной пометки "уже в списке" - слепой toggle
    там рисковал бы тихо удалить слово случайным повторным тапом. Убрать
    можно только явно, из самого списка "Мои слова" (remove_starred_word),
    либо автоматически по достижении MASTERY_STREAK верных подряд в
    тренажёре (см. core/mufradat.py:record_answer)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        progress_key = _resolve_progress_key(conn, surah, ayah, position)
        conn.execute(
            "INSERT OR IGNORE INTO mushaf_starred_words "
            "(user_id, surah, ayah, position, arabic_html, translation, added_at, progress_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, surah, ayah, position, arabic_html, translation,
             datetime.now(timezone.utc).isoformat(), progress_key)
        )


def remove_starred_word(user_id, surah, ayah, position):
    """Двойной тап/клик по строке В САМОМ списке (см. модульный docstring)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        )


def remove_starred_by_progress_key(user_id, progress_key):
    """Авто-удаление по достижении MASTERY_STREAK в тренажёре (вызывается
    из core/mufradat.py:record_answer). По progress_key, НЕ по конкретной
    (surah,ayah,position) - одно и то же слово может быть отмечено на
    НЕСКОЛЬКИХ страницах одновременно (progress_key общий для всех
    вхождений одной пары arabic_text/перевод, см. core/sampler.py), и
    "выучено" оно тоже одно на всех - вопрос в тренажёре мог попасться по
    ЛЮБОМУ из этих вхождений, не обязательно по тому, что отмечал студент."""
    if progress_key is None:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND progress_key=?",
            (user_id, progress_key)
        )


def get_starred_progress_keys(user_id):
    """Только слова с уже разрешённым progress_key (суры 2-10) - это то,
    что тренажёр вообще способен задать вопросом. Вызывается перед КАЖДЫМ
    generate_question (core/mufradat.py) - см. get_starred_question_pool."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT DISTINCT progress_key FROM mushaf_starred_words "
            "WHERE user_id=? AND progress_key IS NOT NULL",
            (user_id,)
        ).fetchall()
    return {r[0] for r in rows}


def list_starred_words(user_id):
    """Новые сверху - только что встреченное забытое слово должно быть
    первым в списке, не погребено под старыми."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT surah, ayah, position, arabic_html, translation FROM mushaf_starred_words "
            "WHERE user_id=? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
    return [
        {"surah": r[0], "ayah": r[1], "position": r[2], "arabic": r[3], "translation": r[4]}
        for r in rows
    ]
