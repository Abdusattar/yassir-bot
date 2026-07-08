#!/usr/bin/env python3
"""
Строит таблицу motivational_chapters: какие главы каждого сборника
разрешены для мотивационных сообщений (не фикх).

Вывод: SQL INSERT + итоговые цифры.
"""
import sys, sqlite3
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path(__file__).parent.parent / "sources" / "hadiths.db"

# Ключевые слова в названии главы → включать в мотивационный пул
INCLUDE_KEYS = [
    "knowledge", "virtue", "merit", "faith", "belief", "iman",
    "qur'an", "quran", "qur", "recit", "tafsir", "commentary",
    "remembrance", "dhikr", "invoc", "supplicat", "du'a", "prayer.*night",
    "tahajjud", "riqaq", "heart tender", "heart", "patience", "patient",
    "piety", "righteous", "good manner", "adab", "tawheed", "oneness",
    "striv", "excellenc", "praise", "reward", "blessing", "holding fast",
    "i'tikaf", "night of qadr", "laylat", "zuhd", "asceticism",
    "characteristics", "softening", "affliction", "end of the world",
]

# Ключевые слова → ИСКЛЮЧАТЬ (фикх, правовые нормы)
EXCLUDE_KEYS = [
    "purification", "ablution", "wudu", "ghusl", "tayammum",
    "menstruat", "salat", "prayer.*times", "call to prayer", "adhan",
    "friday prayer", "eid", "eclipse", "shortening prayer", "fear prayer",
    "forgetfulness.*prayer", "mosque", "qiblah",
    "zakat", "fasting", "sawm", "ramadan", "tarawih",
    "hajj", "pilgrimage", "umrah", "ihram",
    "marriage", "nikaah", "wedlock", "suckling", "divorce", "li'an",
    "business", "trade", "commerce", "sales", "hire", "mortgag",
    "debt", "loan", "bankrupt", "partnership", "representat",
    "gift", "wills", "testament", "inheritance", "faraid",
    "witness", "testimony", "judgment", "judge", "peacemaking",
    "punishment", "hudood", "blood money", "diyat", "apostas", "coercion",
    "jihad", "military", "expedition", "jihaad", "fighting", "khumus",
    "jizyah", "tribute", "spoils",
    "food", "meal", "drink", "beverage", "dress", "cloth",
    "aqiqa", "sacrifice.*birth", "adahi", "slaughter", "hunting",
    "slave", "makatib", "manumission",
    "dream.*interpretation",
    "oaths", "vow", "expiation",
    "horse.*race", "shooting",
    "hot bath", "hammam", "combing", "ring", "signet",
    "purif", "water.*book",
]


def is_motivational(name: str) -> bool:
    n = name.lower()
    for kw in EXCLUDE_KEYS:
        import re
        if re.search(kw, n):
            return False
    for kw in INCLUDE_KEYS:
        import re
        if re.search(kw, n):
            return True
    return False


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Убедимся что таблица существует
    conn.execute("""
        CREATE TABLE IF NOT EXISTS motivational_chapters (
            collection TEXT NOT NULL,
            chapter_id INTEGER NOT NULL,
            name_en    TEXT,
            PRIMARY KEY (collection, chapter_id)
        )
    """)
    conn.execute("DELETE FROM motivational_chapters")

    books = conn.execute(
        "SELECT DISTINCT collection FROM hadith_chapters ORDER BY collection"
    ).fetchall()

    grand_total = 0
    for (book,) in books:
        chapters = conn.execute(
            "SELECT chapter_id, name_en FROM hadith_chapters WHERE collection=? ORDER BY chapter_id",
            (book,)
        ).fetchall()

        allowed = []
        rejected = []
        for ch in chapters:
            if is_motivational(ch["name_en"] or ""):
                allowed.append(ch)
            else:
                rejected.append(ch)

        # Подсчёт хадисов
        count = 0
        for ch in allowed:
            n = conn.execute(
                "SELECT COUNT(*) FROM hadiths WHERE collection=? AND chapter_id=?",
                (book, ch["chapter_id"])
            ).fetchone()[0]
            count += n
            conn.execute(
                "INSERT OR REPLACE INTO motivational_chapters VALUES (?,?,?)",
                (book, ch["chapter_id"], ch["name_en"])
            )

        grand_total += count
        print(f"\n[{book}]  -> разрешено {len(allowed)} глав из {len(chapters)}, ~{count} хадисов")
        for ch in allowed:
            print(f"  + {ch['chapter_id']:3d}  {ch['name_en']}")
        for ch in rejected[:3]:
            print(f"  - {ch['chapter_id']:3d}  {ch['name_en']}")
        if len(rejected) > 3:
            print(f"  ... ещё {len(rejected)-3} фикховых пропущено")

    conn.commit()

    print(f"\n{'='*60}")
    print(f"Итого мотивационных хадисов: {grand_total}")
    print(f"Таблица motivational_chapters заполнена.")
    conn.close()


if __name__ == "__main__":
    main()
