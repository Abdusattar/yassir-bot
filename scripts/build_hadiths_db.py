#!/usr/bin/env python3
"""
ETL: скачивает 9 книг хадисов из AhmedBaset/hadith-json (sunnah.com),
     заливает в sources/hadiths.db

Запуск: python scripts/build_hadiths_db.py
"""
import json
import sqlite3
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent
DB_PATH = BASE / "sources" / "hadiths.db"

BOOKS = [
    ("bukhari",  "صحيح البخاري",    "Sahih al-Bukhari"),
    ("muslim",   "صحيح مسلم",       "Sahih Muslim"),
    ("abudawud", "سنن أبي داود",    "Sunan Abi Dawud"),
    ("tirmidhi", "جامع الترمذي",    "Jami at-Tirmidhi"),
    ("nasai",    "السنن الصغرى",    "Sunan an-Nasai"),
    ("ibnmajah", "سنن ابن ماجه",   "Sunan Ibn Majah"),
    ("malik",    "موطأ مالك",       "Muwatta Malik"),
    ("ahmed",    "مسند أحمد",       "Musnad Ahmad"),
    ("darimi",   "سنن الدارمي",     "Sunan ad-Darimi"),
]

RAW_URL = (
    "https://raw.githubusercontent.com/AhmedBaset/hadith-json"
    "/main/db/by_book/the_9_books/{book}.json"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS hadiths (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    collection      TEXT    NOT NULL,
    book_id         INTEGER,
    hadith_number   INTEGER,
    arabic          TEXT    NOT NULL,
    english_narrator TEXT,
    english_text    TEXT,
    used_at         TEXT
);
CREATE INDEX IF NOT EXISTS idx_collection ON hadiths(collection);
CREATE INDEX IF NOT EXISTS idx_used_at    ON hadiths(used_at);

CREATE TABLE IF NOT EXISTS hadith_translations (
    hadith_id  INTEGER NOT NULL,
    lang       TEXT    NOT NULL,
    text       TEXT    NOT NULL,
    created_at TEXT,
    PRIMARY KEY (hadith_id, lang)
);
"""


def create_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
        print(f"Удалена старая БД: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def download_book(book_slug: str) -> list:
    url = RAW_URL.format(book=book_slug)
    print(f"  Скачиваю {url} ...", end=" ", flush=True)
    with urllib.request.urlopen(url, timeout=60) as r:
        data = json.loads(r.read().decode("utf-8"))
    hadiths = data.get("hadiths", [])
    print(f"{len(hadiths)} хадисов")
    return hadiths


def insert_book(conn: sqlite3.Connection, book_slug: str, hadiths: list):
    rows = []
    for h in hadiths:
        arabic = (h.get("arabic") or "").strip()
        if not arabic:
            continue
        eng = h.get("english") or {}
        narrator = (eng.get("narrator") or "").strip() if isinstance(eng, dict) else ""
        text = (eng.get("text") or "").strip() if isinstance(eng, dict) else str(eng).strip()
        rows.append((
            book_slug,
            h.get("bookId"),
            h.get("idInBook") or h.get("id"),
            arabic,
            narrator or None,
            text or None,
        ))
    conn.executemany(
        "INSERT INTO hadiths (collection, book_id, hadith_number, arabic, english_narrator, english_text) "
        "VALUES (?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    print(f"    -> загружено {len(rows)} записей")


def main():
    print(f"Создаю БД: {DB_PATH}\n")
    conn = create_db()

    total = 0
    for slug, ar_title, en_title in BOOKS:
        print(f"[{slug}] {en_title}")
        try:
            hadiths = download_book(slug)
            insert_book(conn, slug, hadiths)
            total += conn.execute(
                "SELECT COUNT(*) FROM hadiths WHERE collection=?", (slug,)
            ).fetchone()[0]
        except Exception as e:
            print(f"  ОШИБКА: {e}")

    print(f"\nИтого в БД: {total} хадисов")
    print(f"Файл: {DB_PATH} ({DB_PATH.stat().st_size // 1024} KB)")
    conn.close()


if __name__ == "__main__":
    main()
