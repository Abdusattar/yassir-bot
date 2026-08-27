"""Случайная выборка хадисов и аятов для мотивационных сообщений."""
import re
import sqlite3
from pathlib import Path
from datetime import datetime

_BASE      = Path(__file__).parent.parent
HADITHS_DB = _BASE / "sources" / "hadiths.db"

COLLECTION_LABELS = {
    "bukhari":  "Бухари",
    "muslim":   "Муслим",
    "abudawud": "Абу Дауд",
    "tirmidhi": "Тирмизи",
    "nasai":    "Насаи",
    "ibnmajah": "Ибн Маджа",
    "malik":    "Малик",
    "ahmed":    "Ахмад",
    "darimi":   "Дарими",
}

_HADITH_SCORE_MIN = 3

_HADITH_BASE_SQL = f"""
    SELECT h.id, h.collection, h.hadith_number, h.arabic, h.english_narrator, h.english_text
    FROM hadiths h
    JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
    WHERE LENGTH(h.arabic) > 80
      AND LENGTH(h.english_text) > 90
      AND LENGTH(h.english_text) < 700
      AND h.english_text NOT LIKE 'This hadith has been%'
      AND h.english_text NOT LIKE '%same chain of transmitters%'
      AND h.english_text NOT LIKE '%same as above%'
      AND (h.motiv_score IS NULL OR h.motiv_score >= {_HADITH_SCORE_MIN})
"""


def sample_hadith() -> dict | None:
    """Возвращает случайный хадис из мотивационных глав (не фикх)."""
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.row_factory = sqlite3.Row
            h = conn.execute(
                _HADITH_BASE_SQL + " AND h.used_at IS NULL ORDER BY RANDOM() LIMIT 1"
            ).fetchone()
            if not h:
                h = conn.execute(
                    _HADITH_BASE_SQL + " ORDER BY h.used_at ASC LIMIT 1"
                ).fetchone()
            if not h:
                return None
            conn.execute(
                "UPDATE hadiths SET used_at=? WHERE id=?",
                (datetime.utcnow().isoformat(), h["id"])
            )
            result = dict(h)
            if result.get("english_text"):
                result["english_text"] = " ".join(result["english_text"].split())
            result["label"] = COLLECTION_LABELS.get(result["collection"], result["collection"])
            return result
    except Exception:
        return None


_AYAH_TAGS_FILTER = (
    "topic_tags LIKE '%quran%' OR topic_tags LIKE '%knowledge%' OR "
    "topic_tags LIKE '%patience%' OR topic_tags LIKE '%striving%' OR "
    "topic_tags LIKE '%reward%' OR topic_tags LIKE '%remembrance%'"
)

_AYAH_SCORE_MIN = 3


def sample_ayah() -> dict | None:
    """Возвращает случайный аят с motiv_score >= 3 по позитивным тегам."""
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(f"""
                SELECT sura, aya, arabic, topic_tags
                FROM quran_ayahs
                WHERE ({_AYAH_TAGS_FILTER})
                  AND (motiv_score IS NULL OR motiv_score >= {_AYAH_SCORE_MIN})
                  AND used_at IS NULL
                ORDER BY RANDOM()
                LIMIT 1
            """).fetchone()
            if not row:
                row = conn.execute(f"""
                    SELECT sura, aya, arabic, topic_tags
                    FROM quran_ayahs
                    WHERE ({_AYAH_TAGS_FILTER})
                      AND (motiv_score IS NULL OR motiv_score >= {_AYAH_SCORE_MIN})
                    ORDER BY used_at ASC
                    LIMIT 1
                """).fetchone()
            if not row:
                return None
            conn.execute(
                "UPDATE quran_ayahs SET used_at=? WHERE sura=? AND aya=?",
                (datetime.utcnow().isoformat(), row["sura"], row["aya"])
            )
            return {
                "sura":       str(row["sura"]),
                "aya":        str(row["aya"]),
                "arabic":     row["arabic"],
                "topic_tags": row["topic_tags"],
                "ref":        f"{row['sura']}:{row['aya']}",
            }
    except Exception:
        return None


# ── Кеш переводов хадисов ──────────────────────────────────────────────────────

def get_cached_translation(hadith_id: int, lang: str) -> str | None:
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            row = conn.execute(
                "SELECT text FROM hadith_translations WHERE hadith_id=? AND lang=?",
                (hadith_id, lang)
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_translation(hadith_id: int, lang: str, text: str) -> None:
    if not HADITHS_DB.exists():
        return
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO hadith_translations (hadith_id, lang, text, created_at) VALUES (?,?,?,?)",
                (hadith_id, lang, text, datetime.utcnow().isoformat())
            )
    except Exception:
        pass


# ── Кеш переводов аятов ────────────────────────────────────────────────────────

def get_cached_ayah_translation(sura: int, aya: int, lang: str) -> str | None:
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            row = conn.execute(
                "SELECT text FROM quran_translations WHERE sura=? AND aya=? AND lang=?",
                (sura, aya, lang)
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_ayah_translation(sura: int, aya: int, lang: str, text: str) -> None:
    if not HADITHS_DB.exists():
        return
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO quran_translations (sura, aya, lang, text, created_at) VALUES (?,?,?,?,?)",
                (sura, aya, lang, text, datetime.utcnow().isoformat())
            )
    except Exception:
        pass


# ── Общий кэш дневной насыхи Тадаббур (мужской и женский боты делят один файл) ─
#
# Мужской бот генерирует текст раз в день и кладёт его сюда; женский читает
# готовый текст и подставляет своё приветствие — вместо второго LLM-вызова.

_NASIHA_CACHE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS daily_nasiha_cache(
        date TEXT PRIMARY KEY,
        text TEXT NOT NULL,
        created_at TEXT
    )
"""

# ── Пословный словарь для тренажёра муфрадата (общий файл, оба бота) ──────────
#
# Источник: официальный API Quran Academy (Digital Quran), пословный перевод,
# проверен на совпадение с ручной выборкой 17.08.2026 (см.
# project_mufradat_data_source_licensing в памяти). Языки - по одному прогону
# scripts/ingest_mufradat.py на каждый (26.08.2026: ru, uz), не в рантайме бота.
#
# language - код языка перевода этой конкретной строки (UNIQUE теперь включает
# язык - одно и то же слово на разных языках живёт как отдельные строки).
#
# progress_key - id "представителя" пары (arabic_text, нормализованный
# translation, language): если одно и то же арабское слово с одним и тем же
# переводом встречается на нескольких страницах, все его строки указывают на
# ОДИН и тот же progress_key (id самой первой встреченной строки) - прогресс
# студента (core/mufradat.py) висит на progress_key, а не на id конкретной
# строки, иначе мастерство слова не сходится в одно целое, если оно повторяется
# на разных страницах (найдено пользователем 26.08.2026, измерено на проде:
# 2990 из 16040 пар со ро 2+ повторами, у 61% активных студентов уже была эта
# проблема - core/mufradat.py:pick_question_word и compute_overall_score
# работают через progress_key, не через id).
_MUFRADAT_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mufradat_words(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        surah_number INTEGER NOT NULL,
        ayah_number INTEGER NOT NULL,
        position INTEGER NOT NULL,
        arabic_text TEXT NOT NULL,
        translation TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'ru',
        progress_key INTEGER NOT NULL,
        UNIQUE(surah_number, ayah_number, position, language)
    )
"""


def normalize_gloss(text):
    """Общая с core/mufradat.py нормализация перевода (обрезка хвостовой
    пунктуации/пробелов, lower) - здесь нужна, чтобы группировать пары для
    progress_key ТЕМ ЖЕ способом, каким core/mufradat.py потом их сравнивает
    (иначе "Путём" и "путём," считались бы разными представителями здесь,
    но одинаковыми там - расхождение молча ломало бы дедуп)."""
    return re.sub(r"[,.!;:\s]+$", "", text.strip().lower())


def ensure_mufradat_schema(conn):
    """Без подчёркивания (26.08.2026) - вызывается не только из save_mufradat_word
    (путь записи), но и из core/mufradat.py:get_words_in_range (путь чтения) -
    без этого первое ЧТЕНИЕ после деплоя (студент открыл тренажёр раньше, чем
    отработал любой write-путь) падало на "no such column: progress_key" на
    ещё немигрированной таблице (поймано тестом перед деплоем).

    CREATE TABLE (см. _MUFRADAT_SCHEMA) + разовая миграция со старой формы
    (без language/progress_key, UNIQUE без языка) - таблица уже существует на
    проде с 27609+ строками прогресса, завязанными на id (26.08.2026).
    Переносим id ЯВНО (без него AUTOINCREMENT раздал бы новые id, и ВЕСЬ
    прогресс всех студентов осиротел бы разом - см. предупреждение advisor) -
    старые строки помечаются language='ru' (единственный язык на тот момент),
    progress_key считается так же, как для новых строк в save_mufradat_word
    (первая встреченная строка с данной парой (arabic_text, normalize_gloss(
    translation)) - id по возрастанию совпадает с порядком (surah, ayah,
    position), т.к. исходная загрузка шла именно в этом порядке, проверено на
    проде перед миграцией)."""
    conn.execute(_MUFRADAT_SCHEMA)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(mufradat_words)")}
    if "language" in cols:
        return

    conn.execute("ALTER TABLE mufradat_words RENAME TO mufradat_words_old")
    conn.execute(_MUFRADAT_SCHEMA)
    rows = conn.execute(
        "SELECT id, surah_number, ayah_number, position, arabic_text, translation "
        "FROM mufradat_words_old ORDER BY id"
    ).fetchall()

    representative = {}
    for r in rows:
        key = (r[4], normalize_gloss(r[5]))
        representative.setdefault(key, r[0])

    conn.executemany(
        "INSERT INTO mufradat_words "
        "(id, surah_number, ayah_number, position, arabic_text, translation, language, progress_key) "
        "VALUES (?,?,?,?,?,?, 'ru', ?)",
        [
            (r[0], r[1], r[2], r[3], r[4], r[5], representative[(r[4], normalize_gloss(r[5]))])
            for r in rows
        ]
    )
    conn.execute("DROP TABLE mufradat_words_old")


def save_mufradat_word(surah_number, ayah_number, position, arabic_text, translation, language="ru"):
    """UPDATE на месте для уже существующей строки (surah, ayah, position,
    language) - id и progress_key НЕ трогаются, иначе повторный прогон
    ingest_mufradat.py (идемпотентный по задумке) рвал бы прогресс студентов
    на каждый перезапуск (было так раньше через INSERT OR REPLACE - id не
    входил в список колонок INSERT, AUTOINCREMENT раздавал новый на каждый
    конфликт - живая мина, поймана 26.08.2026 при проектировании progress_key,
    ни разу не сработавшая на проде только потому что скрипт ни разу не
    перезапускался после первой полной загрузки, проверено по непрерывности
    id и порядку на проде).

    Для НОВОЙ строки progress_key ищем по (arabic_text, language) среди уже
    существующих строк - если находим совпадение по normalize_gloss(translation)
    (та же нормализация, что и в ensure_mufradat_schema и core/mufradat.py),
    наследуем их progress_key (первая версия этого слова остаётся
    представителем навсегда, даже если у неё саму потом сменят перевод через
    UPDATE выше) - иначе новая строка становится представителем сама себе."""
    with sqlite3.connect(HADITHS_DB) as conn:
        ensure_mufradat_schema(conn)

        existing = conn.execute(
            "SELECT id FROM mufradat_words WHERE surah_number=? AND ayah_number=? "
            "AND position=? AND language=?",
            (surah_number, ayah_number, position, language)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE mufradat_words SET arabic_text=?, translation=? WHERE id=?",
                (arabic_text, translation, existing[0])
            )
            return

        norm = normalize_gloss(translation)
        rep_id = None
        for cid, ctranslation, cprogress_key in conn.execute(
            "SELECT id, translation, progress_key FROM mufradat_words WHERE arabic_text=? AND language=?",
            (arabic_text, language)
        ):
            if normalize_gloss(ctranslation) == norm:
                rep_id = cprogress_key
                break

        cur = conn.execute(
            "INSERT INTO mufradat_words "
            "(surah_number, ayah_number, position, arabic_text, translation, language, progress_key) "
            "VALUES (?,?,?,?,?,?,?)",
            (surah_number, ayah_number, position, arabic_text, translation, language, rep_id or 0)
        )
        if rep_id is None:
            conn.execute("UPDATE mufradat_words SET progress_key=id WHERE id=?", (cur.lastrowid,))


def get_cached_nasiha(date: str) -> str | None:
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.execute(_NASIHA_CACHE_SCHEMA)
            row = conn.execute(
                "SELECT text FROM daily_nasiha_cache WHERE date=?", (date,)
            ).fetchone()
            return row[0] if row else None
    except Exception:
        return None


def save_cached_nasiha(date: str, text: str) -> None:
    if not HADITHS_DB.exists():
        return
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.execute(_NASIHA_CACHE_SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO daily_nasiha_cache (date, text, created_at) VALUES (?,?,?)",
                (date, text, datetime.utcnow().isoformat())
            )
    except Exception:
        pass
