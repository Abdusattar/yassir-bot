"""Личный список "Мои слова" - слова со страницы чтения мусхафа, отмеченные
студентом двойным тапом/кликом для повторения (29.08.2026, "встретил
забытое слово по ходу чтения, хочу вернуться к нему потом"), а с того же
дня (второй заход) - ТАКЖЕ слова, отвеченные неверно в тренажёре
(add_starred_word_by_progress_key, см. core/mufradat.py:record_answer) -
список растёт без предела, ограничений на размер намеренно нет (решение
пользователя: два канала слива - ручное удаление и 5 верных подряд -
достаточны). Простой список арабский+перевод для чтения - клик по строке
никуда не ведёт, не квиз (решение пользователя 29.08.2026, первый заход).
Арабский текст всегда БЕЗ цветной таджвид-разметки (даже если добавлено
со страницы чтения, где разметка есть) - решение пользователя, список
для повторения, не для чтения с таджвидом.

Идентификатор слова - (surah, ayah, position) из данных страницы чтения
(mushaf_data/page*.json, scripts/export_mushaf_page.py), НЕ progress_key
mufradat_words напрямую - резолвится отдельным JOIN при добавлении (см.
ниже), т.к. это разные системы идентификации одного и того же слова.

Интеграция с тренажёром (29.08.2026, второй заход - решение пользователя
"их надо обязательно прогонять в тренажёре"): при добавлении слова сразу
пытаемся разрешить его progress_key (совпадение по surah/ayah/position с
mufradat_words, язык 'ru' - тот же язык, каким страница чтения
экспортирует переводы, см. scripts/export_mushaf_page.py:get_ayah_words).
mufradat_words покрывает весь Коран (1-114, синк на прод 29.08.2026 - см.
память project_mufradat_local_full_quran_data), так что резолвится
практически всегда; не нашли - progress_key остаётся NULL, слово просто
списком для чтения, как и было изначально."""
import re
import sqlite3
from datetime import datetime, timezone

from core.sampler import HADITHS_DB

# Со страницы чтения арабский текст приходит с цветной таджвид-разметкой
# (<tajweed class=...>...</tajweed>, см. scripts/export_mushaf_page.py) -
# "Мои слова" её не показывает (решение пользователя 29.08.2026, список для
# повторения, не для чтения с таджвидом) - снимаем теги, оставляя только
# буквы. Слова, приходящие из тренажёра (add_starred_word_by_progress_key),
# и так без тегов (arabic_text из mufradat_words - обычный текст).
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tajweed_tags(html):
    return _TAG_RE.sub("", html)

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
            (user_id, surah, ayah, position, _strip_tajweed_tags(arabic_html), translation,
             datetime.now(timezone.utc).isoformat(), progress_key)
        )


def add_starred_word_by_progress_key(user_id, progress_key, language=_LANGUAGE):
    """Авто-добавление при неверном ответе в тренажёре (core/mufradat.py:
    record_answer, 29.08.2026, решение пользователя "должно уходить в мои
    слова"). В отличие от add_starred_word (тап на странице чтения, есть
    surah/ayah/position/arabic/translation готовыми), тут есть только
    progress_key - берём представительную строку из mufradat_words (тот же
    подход, что get_words_by_progress_keys в core/mufradat.py: arabic_text/
    translation одинаковы у всех вхождений одного progress_key по
    построению, конкретные surah/ayah/position роли не играют, просто нужен
    один реальный идентификатор для PRIMARY KEY таблицы). Идемпотентно, как
    и add_starred_word - если это же вхождение уже в списке, ничего не
    меняет."""
    if progress_key is None:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT surah_number, ayah_number, position, arabic_text, translation "
            "FROM mufradat_words WHERE progress_key=? AND language=? LIMIT 1",
            (progress_key, language)
        ).fetchone()
        if row is None:
            return
        surah, ayah, position, arabic_text, translation = row
        conn.execute(
            "INSERT OR IGNORE INTO mushaf_starred_words "
            "(user_id, surah, ayah, position, arabic_html, translation, added_at, progress_key) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (user_id, surah, ayah, position, arabic_text, translation,
             datetime.now(timezone.utc).isoformat(), progress_key)
        )


def _reset_progress_streak(conn, user_id, progress_key):
    """Слово покинуло "Мои слова" (любым путём - вручную или 5 верных
    подряд) - обнуляет correct_streak в mufradat_progress (core/mufradat.py),
    чтобы путь к MASTERY_STREAK начинался заново, "как у обычного слова",
    а не мгновенно засчитывался на уже накопленном streak=5 (решение
    пользователя 29.08.2026 - без сброса выход из "Мои слова" совпадал бы
    с уходом слова на 60-дневный отдых, минуя повторное подтверждение).
    Не трогает wrong_count/correct_count/last_correct_date - только текущую
    серию. Нет строки прогресса (слово ни разу не отвечали в тренажёре) -
    UPDATE просто не находит строк, безопасный no-op."""
    if progress_key is None:
        return
    conn.execute(
        "UPDATE mufradat_progress SET correct_streak=0 WHERE user_id=? AND word_id=?",
        (user_id, progress_key)
    )


def remove_starred_word(user_id, surah, ayah, position):
    """Двойной тап/клик по строке В САМОМ списке (см. модульный docstring).
    Сбрасывает correct_streak (см. _reset_progress_streak) - решение
    пользователя 29.08.2026: ручное удаление тоже "как все", не льгота."""
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT progress_key FROM mushaf_starred_words "
            "WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        ).fetchone()
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND surah=? AND ayah=? AND position=?",
            (user_id, surah, ayah, position)
        )
        if row is not None:
            _reset_progress_streak(conn, user_id, row[0])


def remove_starred_by_progress_key(user_id, progress_key):
    """Авто-удаление по достижении MASTERY_STREAK в тренажёре (вызывается
    из core/mufradat.py:record_answer). По progress_key, НЕ по конкретной
    (surah,ayah,position) - одно и то же слово может быть отмечено на
    НЕСКОЛЬКИХ страницах одновременно (progress_key общий для всех
    вхождений одной пары arabic_text/перевод, см. core/sampler.py), и
    "выучено" оно тоже одно на всех - вопрос в тренажёре мог попасться по
    ЛЮБОМУ из этих вхождений, не обязательно по тому, что отмечал студент.
    Сбрасывает correct_streak (см. _reset_progress_streak) - это и есть
    развязка "вышло из Моих слов" от "ушло на 60-дневный отдых": вызывающий
    код (record_answer) уже записал streak=5 ДО этого вызова, тут же
    перезаписываем его в 0, чтобы is_mastered() перестал быть true и слово
    вернулось в обычный пул вопросов."""
    if progress_key is None:
        return
    with sqlite3.connect(HADITHS_DB) as conn:
        _ensure_schema(conn)
        conn.execute(
            "DELETE FROM mushaf_starred_words WHERE user_id=? AND progress_key=?",
            (user_id, progress_key)
        )
        _reset_progress_streak(conn, user_id, progress_key)


def get_starred_progress_keys(user_id):
    """Только слова с уже разрешённым progress_key - это то, что тренажёр
    вообще способен задать вопросом. Вызывается перед КАЖДЫМ
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
