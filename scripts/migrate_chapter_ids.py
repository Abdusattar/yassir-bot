#!/usr/bin/env python3
"""
Миграция hadiths.db: добавляет chapter_id для каждого хадиса.

Что делает:
1. Добавляет колонку chapter_id в таблицу hadiths
2. Создаёт таблицу hadith_chapters(collection, chapter_id, name_en)
3. Скачивает JSON каждого сборника → проставляет chapter_id по ключу (collection, hadith_number)
"""
import sys, json, sqlite3, urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE     = Path(__file__).parent.parent
DB_PATH  = BASE / "sources" / "hadiths.db"
RAW_URL  = "https://raw.githubusercontent.com/AhmedBaset/hadith-json/main/db/by_book/the_9_books/{book}.json"

BOOKS = [
    "bukhari", "muslim", "abudawud", "tirmidhi",
    "nasai", "ibnmajah", "malik", "ahmed", "darimi",
]


def migrate(conn: sqlite3.Connection):
    cur = conn.cursor()
    cols = [r[1] for r in cur.execute("PRAGMA table_info(hadiths)").fetchall()]
    if "chapter_id" not in cols:
        cur.execute("ALTER TABLE hadiths ADD COLUMN chapter_id INTEGER")
        print("  + колонка chapter_id добавлена")
    else:
        print("  = колонка chapter_id уже есть")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS hadith_chapters (
            collection TEXT NOT NULL,
            chapter_id INTEGER NOT NULL,
            name_en    TEXT,
            name_ar    TEXT,
            PRIMARY KEY (collection, chapter_id)
        )
    """)
    conn.commit()


def process_book(conn: sqlite3.Connection, book: str):
    url = RAW_URL.format(book=book)
    print(f"  Скачиваю {url} ...", end=" ", flush=True)
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(f"ОШИБКА: {e}")
        return 0

    chapters = data.get("chapters", [])
    hadiths  = data.get("hadiths", [])
    print(f"{len(chapters)} глав, {len(hadiths)} хадисов")

    cur = conn.cursor()

    # Сохраняем главы
    for ch in chapters:
        cur.execute(
            "INSERT OR REPLACE INTO hadith_chapters VALUES (?,?,?,?)",
            (book, ch["id"], ch.get("english", ""), ch.get("arabic", ""))
        )

    # Обновляем chapter_id для каждого хадиса
    updated = 0
    for h in hadiths:
        id_in_book = h.get("idInBook") or h.get("id")
        chapter_id = h.get("chapterId")
        if id_in_book is None or chapter_id is None:
            continue
        cur.execute(
            "UPDATE hadiths SET chapter_id=? WHERE collection=? AND hadith_number=?",
            (chapter_id, book, id_in_book)
        )
        updated += cur.rowcount

    conn.commit()
    print(f"    -> обновлено {updated} хадисов")
    return updated


def show_summary(conn: sqlite3.Connection):
    print("\n=== Итог: главы по сборникам (топ по количеству) ===")
    cur = conn.cursor()
    for book in BOOKS:
        rows = cur.execute("""
            SELECT h.chapter_id, hc.name_en, COUNT(*) as n
            FROM hadiths h
            JOIN hadith_chapters hc ON hc.collection=h.collection AND hc.chapter_id=h.chapter_id
            WHERE h.collection=?
            GROUP BY h.chapter_id
            ORDER BY n DESC
            LIMIT 5
        """, (book,)).fetchall()
        total_null = cur.execute(
            "SELECT COUNT(*) FROM hadiths WHERE collection=? AND chapter_id IS NULL", (book,)
        ).fetchone()[0]
        print(f"\n[{book}]  (chapter_id IS NULL: {total_null})")
        for r in rows:
            print(f"  id={r[0]:3d}  {r[2]:5d}  {r[1]}")


def main():
    print(f"БД: {DB_PATH}\n")
    conn = sqlite3.connect(DB_PATH)

    print("Шаг 1: миграция схемы")
    migrate(conn)

    print("\nШаг 2: заполнение chapter_id из JSON")
    total = 0
    for book in BOOKS:
        print(f"\n[{book}]")
        total += process_book(conn, book)

    print(f"\nВсего обновлено: {total} хадисов")
    show_summary(conn)
    conn.close()
    print("\nГотово.")


if __name__ == "__main__":
    main()
