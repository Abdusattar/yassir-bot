# -*- coding: utf-8 -*-
"""Сборка пословных переводов по сурам (scripts/build_wbw_chunks.py, wiki/wbw_split_plan.md)."""
import hashlib
import json
import sqlite3

from scripts.build_wbw_chunks import build


def _db(tmp_path, rows):
    path = tmp_path / "w.db"
    with sqlite3.connect(str(path)) as c:
        c.execute("CREATE TABLE mufradat_words (id INTEGER PRIMARY KEY, surah_number INT, "
                  "ayah_number INT, position INT, arabic_text TEXT, translation TEXT, "
                  "language TEXT, progress_key TEXT)")
        c.executemany("INSERT INTO mufradat_words (surah_number, ayah_number, position, "
                      "translation, language) VALUES (?,?,?,?,?)", rows)
    return path


ROWS = [
    (2, 1, 1, "Алиф Лам Мим", "ru"),
    (2, 2, 2, "Писание –", "ru"),        # хвостовое тире срезается, как в экспорте страниц
    (2, 2, 3, "*", "ru"),                # склейка - в файл не идёт
    (2, 10, 1, "в", "ru"),
    (1, 1, 1, "С именем", "ru"),
    (1, 1, 1, "Аты менен", "ky"),
]


def test_files_and_manifest(tmp_path):
    out = tmp_path / "wbw"
    man, written = build(_db(tmp_path, ROWS), out)
    assert written == 3
    d = json.loads((out / "ru" / "2.json").read_text(encoding="utf-8"))
    assert d == {"s": 2, "w": {"1:1": "Алиф Лам Мим", "2:2": "Писание", "10:1": "в"}}
    assert list(d["w"]) == ["1:1", "2:2", "10:1"]      # порядок по аяту, не по строке
    assert set(man) == {"ru", "ky"} and set(man["ky"]) == {"1"}
    raw = (out / "ru" / "2.json").read_bytes()
    assert man["ru"]["2"] == hashlib.sha1(raw).hexdigest()[:8]
    assert json.loads((out / "manifest.json").read_text(encoding="utf-8")) == man


def test_rebuild_is_stable_and_drops_gone(tmp_path):
    out = tmp_path / "wbw"
    db = _db(tmp_path, ROWS)
    man1, _ = build(db, out)
    man2, written = build(db, out)
    assert man1 == man2 and written == 0
    with sqlite3.connect(str(db)) as c:
        c.execute("DELETE FROM mufradat_words WHERE surah_number=1 AND language='ru'")
        c.execute("UPDATE mufradat_words SET translation='Писание' WHERE ayah_number=2 AND position=2")
    man3, written = build(db, out)
    assert not (out / "ru" / "1.json").exists() and "1" not in man3["ru"]
    assert man3["ru"]["2"] == man1["ru"]["2"]   # «Писание –» и «Писание» - одна подпись
    assert written == 1


def test_only_requested_languages(tmp_path):
    out = tmp_path / "wbw"
    man, _ = build(_db(tmp_path, ROWS), out, {"ky"})
    assert set(man) == {"ky"} and not (out / "ru").exists()
