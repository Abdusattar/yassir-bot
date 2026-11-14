# -*- coding: utf-8 -*-
"""Загрузчик пословного ru не запирает рабочую базу (scripts/load_wbw_ru.py).

14.11.2026: и план, и запись держали базу запертой минутами - приложение у студентов не
открывалось 17 минут. Теперь план базу не трогает, запись запирает её на секунды.
"""
import json
import sqlite3
import sys

import scripts.load_wbw_ru as L


def _db(tmp_path):
    db = tmp_path / "h.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE mufradat_words (id INTEGER PRIMARY KEY, surah_number INT, ayah_number INT, "
              "position INT, arabic_text TEXT, translation TEXT, language TEXT, progress_key INT)")
    c.execute("CREATE TABLE mufradat_progress (user_id TEXT NOT NULL, word_id INTEGER NOT NULL, "
              "correct_streak INTEGER NOT NULL DEFAULT 0, wrong_count INTEGER NOT NULL DEFAULT 0, "
              "days_correct INTEGER NOT NULL DEFAULT 0, last_correct_date TEXT, "
              "correct_count INTEGER NOT NULL DEFAULT 0, PRIMARY KEY (user_id, word_id))")
    # слово «رب» встречается дважды с одной подписью (общий ключ 1); в 1:1 подпись меняем
    c.executemany("INSERT INTO mufradat_words VALUES (?,?,?,?,?,?,?,?)", [
        (1, 1, 1, 1, "رب", "Господь", "ru", 1),
        (2, 1, 1, 2, "العالمين", "миров", "ru", 2),
        (3, 2, 1, 1, "رب", "Господь", "ru", 1),
    ])
    c.execute("INSERT INTO mufradat_progress VALUES ('u1', 1, 2, 0, 2, '2026-11-10', 5)")
    c.commit(); c.close()
    src = tmp_path / "juz.json"
    src.write_text(json.dumps({"1:1": ["Господу", "миров"]}, ensure_ascii=False), encoding="utf-8")
    return db, src


def _dump(db):
    c = sqlite3.connect(str(db))
    try:
        return (c.execute("SELECT * FROM mufradat_words ORDER BY id").fetchall(),
                c.execute("SELECT * FROM mufradat_progress ORDER BY user_id, word_id").fetchall())
    finally:
        c.close()


def _run(monkeypatch, *args):
    monkeypatch.setattr(sys, "argv", ["load_wbw_ru.py", *map(str, args)])
    L.main()


def test_plan_does_not_touch_or_lock_db(tmp_path, monkeypatch):
    db, src = _db(tmp_path)
    before = _dump(db)
    # другой процесс держит базу запертой на запись - план всё равно обязан пройти
    other = sqlite3.connect(str(db), timeout=0.2); other.isolation_level = None
    other.execute("PRAGMA journal_mode=WAL")
    other.execute("BEGIN IMMEDIATE")
    _run(monkeypatch, src, "--db", db)
    other.execute("ROLLBACK"); other.close()
    assert _dump(db) == before


def test_apply_moves_caption_key_and_progress(tmp_path, monkeypatch):
    db, src = _db(tmp_path)
    _run(monkeypatch, src, "--apply", "--db", db)
    words, prog = _dump(db)
    by_id = {w[0]: w for w in words}
    assert by_id[1][5] == "Господу" and by_id[3][5] == "Господь"
    assert by_id[1][7] != by_id[3][7]                    # ключи разошлись: подписи теперь разные
    keys = {p[1] for p in prog if p[0] == "u1"}
    assert keys == {by_id[1][7], by_id[3][7]}            # прогресс есть на обоих ключах
    copied = [p for p in prog if p[1] != 1 or len(prog) == 1]
    assert all(p[6] in (0, 5) for p in prog)             # счётчик в копию не переносится
    assert L.check_invariant(sqlite3.connect(str(db))) == (0, 0)
    # повторный запуск ничего не меняет
    again = _dump(db)
    _run(monkeypatch, src, "--apply", "--db", db)
    assert _dump(db) == again
