# -*- coding: utf-8 -*-
"""Перевод джуза в git загружен в базу? (scripts/check_wbw_ru_loaded.py, architecture.md С1)"""
import json
import os
import sqlite3
import time

from scripts.check_wbw_ru_loaded import not_loaded, update_mark


def _setup(tmp_path):
    db = tmp_path / "h.db"
    c = sqlite3.connect(str(db))
    c.execute("CREATE TABLE mufradat_words (surah_number INT, ayah_number INT, position INT, "
              "translation TEXT, language TEXT)")
    c.executemany("INSERT INTO mufradat_words VALUES (?,?,?,?,?)", [
        (1, 1, 1, "С именем", "ru"), (1, 1, 2, "Аллаха", "ru"),
        (2, 1, 1, "Алиф Лам Мим", "ru"), (2, 1, 1, "другое", "ky")])
    c.commit(); c.close()
    src = tmp_path / "wbw_ru"; src.mkdir()
    (src / "juz1.json").write_text(json.dumps({"1:1": ["С именем", "Аллаха"]}, ensure_ascii=False), encoding="utf-8")
    (src / "juz2.json").write_text(json.dumps({"2:1": ["Алиф. Лам. Мим."]}, ensure_ascii=False), encoding="utf-8")
    return db, src, tmp_path / "mark.json"


def test_mark_and_reminder(tmp_path):
    db, src, mark = _setup(tmp_path)
    assert not_loaded(src, mark) == []                      # отметки нет - молчим
    assert update_mark(db, src, mark) == {"juz1.json": 0, "juz2.json": 1}
    assert set(json.loads(mark.read_text(encoding="utf-8"))) == {"juz1.json"}
    assert not_loaded(src, mark) == []                      # juz2 свежий - полчаса отсрочки
    old = time.time() - 3600
    os.utime(str(src / "juz2.json"), (old, old))
    assert not_loaded(src, mark) == ["juz2.json"]
    # загрузили в базу - напоминание уходит
    c = sqlite3.connect(str(db))
    c.execute("UPDATE mufradat_words SET translation='Алиф. Лам. Мим.' WHERE surah_number=2 AND language='ru'")
    c.commit(); c.close()
    assert update_mark(db, src, mark)["juz2.json"] == 0
    assert not_loaded(src, mark) == []
    # файл поправили после загрузки - снова напомнит
    (src / "juz1.json").write_text(json.dumps({"1:1": ["Во имя", "Аллаха"]}, ensure_ascii=False), encoding="utf-8")
    os.utime(str(src / "juz1.json"), (old, old))
    assert not_loaded(src, mark) == ["juz1.json"]
