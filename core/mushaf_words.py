"""Личный список "Мои слова" - слова со страницы чтения мусхафа, отмеченные
студентом двойным тапом/кликом для повторения (29.08.2026, "встретил
забытое слово по ходу чтения, хочу вернуться к нему потом"). Простой
список арабский+перевод для чтения, БЕЗ связи с движком тренажёра
муфрадата (core/mufradat.py) - решение пользователя: отдельная функция,
клик по слову в списке никуда не ведёт, не квиз.

Идентификатор слова - (surah, ayah, position) из данных страницы чтения
(mushaf_data/page*.json, scripts/export_mushaf_page.py), НЕ progress_key
mufradat_words - та база покрывает только суры 2-10, а читают по всей
книге.
"""
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
        PRIMARY KEY (user_id, surah, ayah, position)
    )
"""


def add_starred_word(user_id, surah, ayah, position, arabic_html, translation):
    """Идемпотентно (INSERT OR IGNORE) - двойной тап на уже добавленном
    слове на странице чтения молча ничего не меняет, не убирает его. На
    странице чтения нет визуальной пометки "уже в списке" - слепой toggle
    там рисковал бы тихо удалить слово случайным повторным тапом. Убрать
    можно только явно, из самого списка "Мои слова" (см. remove_starred_word)."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            "INSERT OR IGNORE INTO mushaf_starred_words "
            "(user_id, surah, ayah, position, arabic_html, translation, added_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, surah, ayah, position, arabic_html, translation,
             datetime.now(timezone.utc).isoformat())
        )


def remove_starred_word(user_id, surah, ayah, position):
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        )


def list_starred_words(user_id):
    """Новые сверху - только что встреченное забытое слово должно быть
    первым в списке, не погребено под старыми."""
    with sqlite3.connect(HADITHS_DB) as conn:
        conn.execute(_SCHEMA)
        rows = conn.execute(
            "SELECT surah, ayah, position, arabic_html, translation FROM mushaf_starred_words "
            "WHERE user_id=? ORDER BY added_at DESC",
            (user_id,)
        ).fetchall()
    return [
        {"surah": r[0], "ayah": r[1], "position": r[2], "arabic": r[3], "translation": r[4]}
        for r in rows
    ]
