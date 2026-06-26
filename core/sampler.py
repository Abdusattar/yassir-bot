"""Случайная выборка хадисов и аятов для мотивационных сообщений."""
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

_HADITH_BASE_SQL = """
    SELECT h.id, h.collection, h.hadith_number, h.arabic, h.english_narrator, h.english_text
    FROM hadiths h
    JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
    WHERE LENGTH(h.arabic) > 80
      AND LENGTH(h.english_text) > 90
      AND LENGTH(h.english_text) < 700
      AND h.english_text NOT LIKE 'This hadith has been%'
      AND h.english_text NOT LIKE '%same chain of transmitters%'
      AND h.english_text NOT LIKE '%same as above%'
      AND (h.hifz_relevant IS NULL OR h.hifz_relevant = 1)
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


def sample_ayah() -> dict | None:
    """Возвращает случайный мотивационный аят из quran_ayahs (по тегам Хайку)."""
    if not HADITHS_DB.exists():
        return None
    try:
        with sqlite3.connect(HADITHS_DB) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("""
                SELECT sura, aya, arabic, topic_tags
                FROM quran_ayahs
                WHERE topic_tags IS NOT NULL
                  AND topic_tags != 'other'
                  AND (hifz_relevant IS NULL OR hifz_relevant = 1)
                  AND used_at IS NULL
                ORDER BY RANDOM()
                LIMIT 1
            """).fetchone()
            if not row:
                row = conn.execute("""
                    SELECT sura, aya, arabic, topic_tags
                    FROM quran_ayahs
                    WHERE topic_tags IS NOT NULL
                      AND topic_tags != 'other'
                      AND (hifz_relevant IS NULL OR hifz_relevant = 1)
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
