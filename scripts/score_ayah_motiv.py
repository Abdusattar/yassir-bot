#!/usr/bin/env python3
"""
Оценка аятов по мотивационной ценности для студентов хифза.
Вопрос: «насколько прямой смысл этого аята побуждает студента к изучению Корана?»
Оценка 1–5. Без API-вызовов — чистые правила по тегам и Arabic-тексту.

Запуск:
  python scripts/score_ayah_motiv.py

Затем:
  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db
"""
import sys, sqlite3, re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent.parent / "sources" / "hadiths.db"

_AYAH_TAGS_FILTER = (
    "topic_tags LIKE '%quran%' OR topic_tags LIKE '%knowledge%' OR "
    "topic_tags LIKE '%patience%' OR topic_tags LIKE '%striving%' OR "
    "topic_tags LIKE '%reward%' OR topic_tags LIKE '%remembrance%'"
)

# ── Арабские паттерны напрямую связанные с Кораном и знанием ──────────────────

# Score +3: прямой призыв читать/учить Коран или искать знание
ARABIC_QURAN_DIRECT = [
    r'ٱقْرَأْ|اقْرَأْ|اقرأ',              # Iqra — читай (96:1)
    r'الْقُرْآن|ٱلْقُرْءَان|القرآن',      # сам Коран в тексте
    r'يَتْلُو|تَتْلُو|يَتْلُون',          # читать/рецитировать
    r'تَدَبَّر|يَتَدَبَّرُون',             # размышлять над Кораном
    r'حَفِظ|يَحْفَظ',                      # хранить/заучивать
    r'طَلَب.*الْعِلْم|طَلَبِ الْعِلْم',   # поиск знания
]

# Score +2: призыв к знанию, терпению, усердию — прямая опора
ARABIC_KNOWLEDGE_STRONG = [
    r'الْعِلْم|ٱلْعِلْم',                 # знание (как главная тема)
    r'يَرْفَعِ اللَّه|يَرْفَعُ اللَّه',   # Аллах возвышает (58:11)
    r'يَعْلَمُون|لَا يَعْلَمُون',         # знающие / не знающие (39:9)
    r'عَلَّم|يُعَلِّم',                    # обучал / обучает
    r'أُوتُوا الْعِلْم|أُوتِيَ الْعِلْم', # наделённые знанием
    r'فَاصْبِرْ|وَاصْبِرْ|اصْبِرُوا',    # команда: терпи!
    r'وَجَاهِدُوا|جَاهِدْ|جِهَاد',        # усердствуй
    r'سَارِعُوا|سَابِقُوا',               # спешите / соревнуйтесь (в благом)
    r'أَطِيعُوا اللَّه.*وَأَطِيعُوا الرَّسُول', # слушайтесь Аллаха и Посланника
]

# Score +1: зикр, упоминание Аллаха, награда — полезный фон
ARABIC_DHIKR_REWARD = [
    r'ذِكْرِ اللَّه|اذْكُرُوا اللَّه',    # зикр Аллаха
    r'أَجْر|أَجْرًا|أُجُورَهُم',          # награда
    r'الصَّابِرِين|الصَّابِرُون',          # терпеливые (похвала)
    r'الصَّالِحَات|الصَّالِحِين',          # праведные дела
    r'يُحِبُّ اللَّه',                     # Аллах любит (тех кто...)
    r'تَوَكَّل|يَتَوَكَّل',               # упование на Аллаха
    r'فَضْل|فَضْلًا',                      # милость / превосходство
    r'رَحْمَة|رَحِيم',                     # милость Аллаха
]


def arabic_score(arabic: str) -> int:
    score = 0
    for pat in ARABIC_QURAN_DIRECT:
        if re.search(pat, arabic):
            score += 3
            break
    for pat in ARABIC_KNOWLEDGE_STRONG:
        if re.search(pat, arabic):
            score += 2
            break
    for pat in ARABIC_DHIKR_REWARD:
        if re.search(pat, arabic):
            score += 1
            break
    return score


# ── Оценка по тегам ────────────────────────────────────────────────────────────

TAG_WEIGHTS = {
    "quran":       3,
    "knowledge":   2,
    "striving":    2,
    "patience":    2,
    "reward":      1,
    "remembrance": 1,
}


def tag_score(topic_tags: str) -> int:
    tags = {t.strip() for t in (topic_tags or "").split(",")}
    score = 0
    for tag, weight in TAG_WEIGHTS.items():
        if tag in tags:
            score += weight
    # бонус за сочетание: знание + усердие/терпение → +1
    if "knowledge" in tags and ("striving" in tags or "patience" in tags):
        score += 1
    return score


# ── Итоговая оценка ────────────────────────────────────────────────────────────

def score_ayah(sura: int, aya: int, arabic: str, topic_tags: str) -> int:
    ts = tag_score(topic_tags)
    ar = arabic_score(arabic or "")
    total = ts + ar

    # Нормализация → 1–5
    if total >= 7:
        return 5
    if total >= 5:
        return 4
    if total >= 3:
        return 3
    if total >= 2:
        return 2
    return 1


# ── Запуск ─────────────────────────────────────────────────────────────────────

def migrate(conn):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(quran_ayahs)")}
    if "motiv_score" not in cols:
        conn.execute("ALTER TABLE quran_ayahs ADD COLUMN motiv_score INTEGER")
        conn.commit()
        print("  + quran_ayahs.motiv_score добавлена")


def main():
    conn = sqlite3.connect(DB_PATH)
    migrate(conn)

    rows = conn.execute(
        f"SELECT sura, aya, arabic, topic_tags FROM quran_ayahs WHERE ({_AYAH_TAGS_FILTER}) ORDER BY sura, aya"
    ).fetchall()
    total = len(rows)
    print(f"Аятов к оценке: {total}")

    for sura, aya, arabic, tags in rows:
        s = score_ayah(sura, aya, arabic or "", tags or "")
        conn.execute(
            "UPDATE quran_ayahs SET motiv_score=? WHERE sura=? AND aya=?",
            (s, sura, aya)
        )
    conn.commit()

    print("\n=== Распределение оценок ===")
    for score in range(5, 0, -1):
        n = conn.execute(
            "SELECT COUNT(*) FROM quran_ayahs WHERE motiv_score=?", (score,)
        ).fetchone()[0]
        bar = "█" * (n // 15)
        print(f"  {score}: {n:4d}  {bar}")

    # Примеры топ аятов
    print("\n=== Топ аятов (score=5) — первые 10 ===")
    top = conn.execute(
        "SELECT sura, aya, topic_tags FROM quran_ayahs WHERE motiv_score=5 ORDER BY sura, aya LIMIT 10"
    ).fetchall()
    for r in top:
        print(f"  {r[0]}:{r[1]}  [{r[2]}]")

    conn.close()
    print(f"\nГотово. Следующий шаг:")
    print(f"  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db")


if __name__ == "__main__":
    main()
