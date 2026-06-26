#!/usr/bin/env python3
"""
Классификация хадисов и аятов на уместность для мотивации студентов хифза.
Rule-based: keyword matching на английском тексте хадисов и topic_tags + паттерны для аятов.

Запуск локально:
  python scripts/classify_hifz_relevance.py
  python scripts/classify_hifz_relevance.py --hadiths
  python scripts/classify_hifz_relevance.py --ayahs
  python scripts/classify_hifz_relevance.py --resume

Затем загружаем БД на сервер:
  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db
"""
import sys, sqlite3, argparse, re
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent.parent / "sources" / "hadiths.db"

# ── Хадисы: ключевые слова для YES / NO ───────────────────────────────────────

HADITH_YES = [
    "quran", "qur'an", "koran", "recit", "memoriz", "hifz", "hafiz",
    "knowledge", "learn", "teach", "scholar", "student", "seeking knowledge",
    "patient", "patience", "persever", "steadfast", "consistent", "constant",
    "mercy", "merciful", "forgiv", "compassion", "rahm",
    "reward", "paradise", "jannah", "good deed", "righteous",
    "dhikr", "remembrance", "supplicat", "invoca",
    "character", "manner", "honest", "truthful", "sincere",
    "faith", "believe", "iman", "trust in allah", "tawakkul",
    "gratitude", "thankful", "grateful",
    "heart", "piety", "taqwa",
    "night prayer", "tahajjud", "qiyam",
    "striv", "effort", "diligence",
]

HADITH_NO = [
    # Никах и семейное право
    "marriage", "divorce", "nikah", "mahr", "dowry", "suckling", "breastfeed",
    "wedding", "bride", "groom", "husband.*wife", "wife.*husband",
    # Наследство
    "inheritance", "faraid", "bequeath", "estate of", "heir",
    # Военные походы и события
    "expedition", "battle of", "fighting", "army", "war",
    "captive", "spoil", "booty", "ghazwah", "conquest",
    # Фикх тахарата и намаза
    "wudu", "ghusl", "tayammum", "ablut", "purif.*ritual",
    # Этнические/племенные достоинства
    "tribe of", "clan of", "non-arab", "persian.*virtues", "roman", "byzantine",
    "virtue of the people", "virtue of.*arabia",
    # Наказания
    "blood money", "diyat", "whipping", "lashing", "stoning", "hadd", "execution",
    "cutting.*hand",
    # Торговля и финансы
    "business transaction", "selling", "buying", "debt", "loan", "bankrupt",
    "trade.*forbidden", "interest", "riba",
    # Хадж, закят (как ритуал, не мотивация)
    "hajj.*rites", "umrah.*rites", "ihram.*wearing",
    # Запреты
    "intoxicant", "alcohol", "wine",
    "dog.*impure", "picture.*forbidden", "image.*forbid",
    # Рабство
    "slave.*freed", "manumission", "freeing.*slave",
]

HADITH_NO_EXACT = [
    # Короткие точные фразы
    "same as above", "same chain", "narrated the same",
]


def is_hadith_relevant(text: str) -> bool:
    t = text.lower()

    # Явные исключения по точным фразам
    for phrase in HADITH_NO_EXACT:
        if phrase in t:
            return False

    yes_score = sum(1 for kw in HADITH_YES if re.search(r'\b' + re.escape(kw), t))
    no_score  = sum(1 for kw in HADITH_NO  if re.search(kw, t))

    # Хадис уместен если: есть хотя бы одно YES-слово и NO-слов меньше чем YES-слов
    return yes_score > 0 and no_score < yes_score


# ── Аяты: правила по topic_tags и Arabic text паттернам ───────────────────────

# Теги, которые всегда проходят (тема явно подходит для хифза)
AYAH_TAGS_YES = {"quran", "knowledge", "patience", "striving", "reward"}

# Теги, которые проходят, но нужна дополнительная проверка текста
# character намеренно убран: слишком широкий, захватывает отрицательные примеры (4:107 и др.)
AYAH_TAGS_MAYBE = {"remembrance", "mercy", "faith"}

# Арабские паттерны аятов, не подходящих для мотивации студентов в данном контексте
AYAH_EXCLUDE_PATTERNS = [
    r'يَسْتَعْجِلُونَ',              # «торопят» (наказание)
    r'لَقُضِيَ الْأَمْرُ',            # «дело было бы решено» (угроза)
    r'أَيُّهَا الْكَافِرُونَ',        # «О неверующие»
    r'لِلْكَافِرِينَ.*عَذَاب',        # «неверующим — мучение»
    r'عَذَاب.*الْكَافِرِينَ',
    r'الْمُشْرِكِينَ.*فَاقْتُلُوا',   # «многобожников — убивайте»
    r'غَضَبُ اللَّهِ',               # «гнев Аллаха» (без контекста раскаяния)
    r'لَعَنَهُمُ اللَّهُ',            # «проклял их Аллах»
    r'إِنَّ اللَّهَ لَا يَهْدِي',    # «Аллах не ведёт» (кяфиров)
    r'لَا يُحِبُّ',                  # «Аллах не любит X» — назидание, не мотивация
]

# Дополнительно: известные диапазоны аятов с высоким риском неуместности.
# Формат: (сура, от_аята, до_аята включительно)
AYAH_EXCLUDE_RANGES = [
    (6, 57, 65),    # Аль-Анъам: аяты об ускорении наказания (включая 6:58)
    (9, 1, 16),     # Тауба: начало суры о многобожниках (нет басмала, ультиматум)
    (111, 1, 5),    # Аль-Масад: целиком о Абу Ляхабе
    (66, 10, 10),   # Ат-Тахрим: жёны Нуха и Лута как отрицательный пример
]


def is_ayah_relevant(sura: int, aya: int, arabic: str, topic_tags: str) -> bool:
    tags = {t.strip() for t in (topic_tags or "").split(",")}

    # Известные исключения по диапазону
    for (s, a_from, a_to) in AYAH_EXCLUDE_RANGES:
        if sura == s and a_from <= aya <= a_to:
            return False

    # Проверка Arabic text на паттерны угрозы неверующим
    for pattern in AYAH_DISBELIEVER_PATTERNS:
        if re.search(pattern, arabic):
            return False

    # Если тег явно подходящий — YES
    if tags & AYAH_TAGS_YES:
        return True

    # Если тег «может быть» — YES (паттерны исключения уже прошли выше)
    if tags & AYAH_TAGS_MAYBE:
        return True

    return False


# ── Миграция схемы ─────────────────────────────────────────────────────────────

def migrate(conn: sqlite3.Connection):
    cols_h = {r[1] for r in conn.execute("PRAGMA table_info(hadiths)")}
    cols_a = {r[1] for r in conn.execute("PRAGMA table_info(quran_ayahs)")}
    if "hifz_relevant" not in cols_h:
        conn.execute("ALTER TABLE hadiths ADD COLUMN hifz_relevant INTEGER")
        print("  + hadiths.hifz_relevant добавлена")
    if "hifz_relevant" not in cols_a:
        conn.execute("ALTER TABLE quran_ayahs ADD COLUMN hifz_relevant INTEGER")
        print("  + quran_ayahs.hifz_relevant добавлена")
    conn.commit()


# ── Классификация хадисов ──────────────────────────────────────────────────────

HADITH_SQL = """
    SELECT h.id, h.english_text
    FROM hadiths h
    JOIN motivational_chapters mc ON mc.collection = h.collection AND mc.chapter_id = h.chapter_id
    WHERE LENGTH(h.english_text) > 90
      AND LENGTH(h.english_text) < 700
      AND h.english_text NOT LIKE 'This hadith has been%'
      AND h.english_text NOT LIKE '%same chain of transmitters%'
      AND h.english_text NOT LIKE '%same as above%'
"""


def classify_hadiths(conn: sqlite3.Connection, resume: bool):
    sql = HADITH_SQL
    if resume:
        sql += " AND h.hifz_relevant IS NULL"
    rows = conn.execute(sql).fetchall()
    total = len(rows)
    print(f"\n[ХАДИСЫ] К классификации: {total}")

    yes_count = no_count = 0
    for i, (hid, text) in enumerate(rows, 1):
        relevant = is_hadith_relevant(text or "")
        conn.execute(
            "UPDATE hadiths SET hifz_relevant=? WHERE id=?",
            (1 if relevant else 0, hid)
        )
        if relevant:
            yes_count += 1
        else:
            no_count += 1
        if i % 500 == 0 or i == total:
            conn.commit()
            pct = round(i / total * 100)
            print(f"  [{i:5d}/{total}]  {pct:3d}%  ✅ {yes_count}  ❌ {no_count}", end="\r")

    conn.commit()
    print(f"\n  Готово. Уместных: {yes_count}, неуместных: {no_count}")


# ── Классификация аятов ────────────────────────────────────────────────────────

def classify_ayahs(conn: sqlite3.Connection, resume: bool):
    sql = """
        SELECT sura, aya, arabic, topic_tags
        FROM quran_ayahs
        WHERE topic_tags IS NOT NULL AND topic_tags != 'other'
    """
    if resume:
        sql += " AND hifz_relevant IS NULL"
    sql += " ORDER BY sura, aya"
    rows = conn.execute(sql).fetchall()
    total = len(rows)
    print(f"\n[АЯТЫ] К классификации: {total}")

    yes_count = no_count = 0
    for i, (sura, aya, arabic, tags) in enumerate(rows, 1):
        relevant = is_ayah_relevant(sura, aya, arabic or "", tags or "")
        conn.execute(
            "UPDATE quran_ayahs SET hifz_relevant=? WHERE sura=? AND aya=?",
            (1 if relevant else 0, sura, aya)
        )
        if relevant:
            yes_count += 1
        else:
            no_count += 1
        if i % 500 == 0 or i == total:
            conn.commit()
            pct = round(i / total * 100)
            print(f"  [{i:5d}/{total}]  {pct:3d}%  ✅ {yes_count}  ❌ {no_count}", end="\r")

    conn.commit()
    print(f"\n  Готово. Уместных: {yes_count}, неуместных: {no_count}")


# ── Статистика и финал ─────────────────────────────────────────────────────────

def print_stats(conn: sqlite3.Connection):
    print("\n=== Итог ===")
    for table in ("hadiths", "quran_ayahs"):
        yes  = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant = 1").fetchone()[0]
        no   = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant = 0").fetchone()[0]
        null = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE hifz_relevant IS NULL").fetchone()[0]
        print(f"  {table:15s}  ✅ {yes}  ❌ {no}  ? {null}")

    # Проверка: 6:58 должен быть исключён
    row = conn.execute(
        "SELECT hifz_relevant FROM quran_ayahs WHERE sura=6 AND aya=58"
    ).fetchone()
    flag = "✅ исключён" if row and row[0] == 0 else "⚠️  НЕ исключён"
    print(f"\n  Проверка аят 6:58: {flag}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hadiths", action="store_true")
    parser.add_argument("--ayahs",   action="store_true")
    parser.add_argument("--resume",  action="store_true", help="Пропустить уже размеченные")
    args = parser.parse_args()

    do_hadiths = args.hadiths or (not args.hadiths and not args.ayahs)
    do_ayahs   = args.ayahs   or (not args.hadiths and not args.ayahs)

    if not DB_PATH.exists():
        print(f"БД не найдена: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    print("Миграция схемы...")
    migrate(conn)

    if do_hadiths:
        classify_hadiths(conn, args.resume)
    if do_ayahs:
        classify_ayahs(conn, args.resume)

    print_stats(conn)
    conn.close()

    print(f"\nСледующий шаг — загружаем БД на сервер:")
    print(f"  scp sources/hadiths.db stursunkul@34.51.213.67:/home/stursunkul/yassir-bot/sources/hadiths.db")


if __name__ == "__main__":
    main()
