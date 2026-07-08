#!/usr/bin/env python3
"""
Шаг 1: Создаёт таблицы quran_ayahs и quran_translations в hadiths.db.
Заливает все аяты из quran-simple.txt (sura|aya|arabic).
topic_tags остаётся пустым — заполняется batch_classify_quran.py.
"""
import sys, sqlite3
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

BASE     = Path(__file__).parent.parent
DB_PATH  = BASE / "sources" / "hadiths.db"
TXT_PATH = BASE / "sources" / "quran-simple.txt"


def main():
    conn = sqlite3.connect(DB_PATH)

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS quran_ayahs (
            sura        INTEGER NOT NULL,
            aya         INTEGER NOT NULL,
            arabic      TEXT    NOT NULL,
            topic_tags  TEXT,
            used_at     TEXT,
            PRIMARY KEY (sura, aya)
        );
        CREATE TABLE IF NOT EXISTS quran_translations (
            sura        INTEGER NOT NULL,
            aya         INTEGER NOT NULL,
            lang        TEXT    NOT NULL,
            text        TEXT    NOT NULL,
            created_at  TEXT,
            PRIMARY KEY (sura, aya, lang)
        );
        CREATE INDEX IF NOT EXISTS idx_quran_tags ON quran_ayahs(topic_tags);
    """)

    lines = TXT_PATH.read_text(encoding="utf-8").splitlines()
    rows = []
    for line in lines:
        parts = line.strip().split("|", 2)
        if len(parts) != 3:
            continue
        sura, aya, arabic = parts
        if not arabic.strip():
            continue
        rows.append((int(sura.strip()), int(aya.strip()), arabic.strip()))

    conn.executemany(
        "INSERT OR IGNORE INTO quran_ayahs (sura, aya, arabic) VALUES (?,?,?)",
        rows
    )
    conn.commit()

    total = conn.execute("SELECT COUNT(*) FROM quran_ayahs").fetchone()[0]
    print(f"Загружено {len(rows)} аятов. В таблице: {total}")
    conn.close()


if __name__ == "__main__":
    main()
