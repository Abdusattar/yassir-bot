#!/usr/bin/env python3
"""
Оценка хадисов по мотивационной ценности для студентов хифза.
Вопрос: «насколько прямой смысл этого хадиса побуждает студента к изучению Корана?»
Оценка 1–5. Без API-вызовов — правила по английскому тексту.

Запуск:
  python scripts/score_hadith_motiv.py

Затем:
  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db
"""
import sys, sqlite3, re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent.parent / "sources" / "hadiths.db"

_HADITH_BASE_SQL = """
    SELECT h.id, h.english_text
    FROM hadiths h
    JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
    WHERE LENGTH(h.arabic) > 80
      AND LENGTH(h.english_text) > 90
      AND LENGTH(h.english_text) < 700
      AND h.english_text NOT LIKE 'This hadith has been%'
      AND h.english_text NOT LIKE '%same chain of transmitters%'
      AND h.english_text NOT LIKE '%same as above%'
"""

# ── Score +3: прямо про Коран и знание ────────────────────────────────────────
PATTERNS_5 = [
    r"qur['\"]?an|koran",
    r"memoriz|hifz|hafiz",
    r"recit.*quran|quran.*recit",
    r"teach.*quran|quran.*teach|learn.*quran|quran.*learn",
    r"seek.*knowledge|seeking knowledge|pursuit.*knowledge",
    r"best.*learn.*quran|best.*quran",
    r"tilawah|recitation of the quran",
]

# ── Score +2: знание, усердие, постоянство ────────────────────────────────────
PATTERNS_4 = [
    r"\bknowledge\b",
    r"patient|patience|persever|steadfast|consistent|constant",
    r"\bstrive\b|striving|effort|diligen",
    r"night prayer|tahajjud|qiyam",
    r"best among you|best of you",
    r"scholar|student of knowledge|talib",
    r"supplicat|invoca|dua",
]

# ── Score +1: награда, вера, милость — полезный фон ──────────────────────────
PATTERNS_3 = [
    r"reward|paradise|jannah|good deed",
    r"merciful|forgiv|compassion|rahm",
    r"\bfaith\b|iman|righteous|pious|taqwa",
    r"grateful|thankful|gratitude",
    r"dhikr|remembrance of allah",
    r"sincere|sincerity|ikhlas",
    r"heart.*light|light.*heart|soften.*heart",
]


def score_hadith(text: str) -> int:
    t = text.lower()
    score = 0

    for pat in PATTERNS_5:
        if re.search(pat, t):
            score += 3
            break

    for pat in PATTERNS_4:
        if re.search(pat, t):
            score += 2
            break

    for pat in PATTERNS_3:
        if re.search(pat, t):
            score += 1
            break

    if score >= 5:
        return 5
    if score >= 4:
        return 4
    if score >= 3:
        return 3
    if score >= 2:
        return 2
    return 1


# ── Запуск ────────────────────────────────────────────────────────────────────

def migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(hadiths)")}
    if "motiv_score" not in cols:
        conn.execute("ALTER TABLE hadiths ADD COLUMN motiv_score INTEGER")
        conn.commit()
        print("  + hadiths.motiv_score добавлена")


def main():
    conn = sqlite3.connect(DB_PATH)
    migrate(conn)

    rows = conn.execute(_HADITH_BASE_SQL).fetchall()
    total = len(rows)
    print(f"Хадисов к оценке: {total}")

    for hid, text in rows:
        s = score_hadith(text or "")
        conn.execute("UPDATE hadiths SET motiv_score=? WHERE id=?", (s, hid))
    conn.commit()

    print("\n=== Распределение оценок ===")
    for score in range(5, 0, -1):
        n = conn.execute(
            "SELECT COUNT(*) FROM hadiths WHERE motiv_score=?", (score,)
        ).fetchone()[0]
        bar = "█" * (n // 5)
        print(f"  {score}: {n:4d}  {bar}")

    # Примеры топ хадисов
    print("\n=== Примеры score=5 (первые 5) ===")
    top = conn.execute("""
        SELECT h.collection, h.hadith_number, h.english_text
        FROM hadiths h
        WHERE h.motiv_score = 5
        ORDER BY RANDOM() LIMIT 5
    """).fetchall()
    for r in top:
        print(f"  [{r[0]} #{r[1]}] {r[2][:120]}...")

    print("\n=== Примеры score=1 (первые 5) ===")
    low = conn.execute("""
        SELECT h.collection, h.hadith_number, h.english_text
        FROM hadiths h
        JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
        WHERE h.motiv_score = 1
        ORDER BY RANDOM() LIMIT 5
    """).fetchall()
    for r in low:
        print(f"  [{r[0]} #{r[1]}] {r[2][:120]}...")

    conn.close()
    print(f"\nГотово. Следующий шаг:")
    print(f"  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db")


if __name__ == "__main__":
    main()
