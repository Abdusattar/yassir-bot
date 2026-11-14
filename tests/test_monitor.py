# -*- coding: utf-8 -*-
"""Наблюдение за сервером (scripts/monitor.py, wiki/architecture.md П2)."""
import os
import time

from scripts.monitor import backup_problem, diff, read_env


def _copy(d, day, n=3, age_h=1.0):
    p = d / day
    p.mkdir(parents=True)
    for i in range(n):
        f = p / ("b%d.db.gz" % i)
        f.write_bytes(b"x")
        t = time.time() - age_h * 3600
        os.utime(f, (t, t))


def test_backup_fresh_ok(tmp_path):
    _copy(tmp_path, "2026-11-14")
    assert backup_problem(tmp_path) is None


def test_backup_missing_old_incomplete_failed(tmp_path):
    assert "нет вообще" in backup_problem(tmp_path)
    _copy(tmp_path, "2026-11-10", age_h=40)
    assert "ч (" in backup_problem(tmp_path)
    _copy(tmp_path, "2026-11-14", n=2)
    assert "2 из 3" in backup_problem(tmp_path)
    _copy(tmp_path, "2026-11-15")
    (tmp_path / "backup.log").write_text("quran_male.db: ок\nОШИБКА quran_female.db: нет\n", encoding="utf-8")
    assert "ошибкой" in backup_problem(tmp_path)


def test_alert_once_and_recovery():
    assert diff({}, {"male": "мужской бот не отвечает"}) == ["⚠️ мужской бот не отвечает"]
    assert diff({"male": "x"}, {"male": "x"}) == []                 # повторно не пишем
    assert diff({"male": "мужской"}, {}) == ["✅ прошло: мужской"]


def test_env_reader(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# c\nTELEGRAM_TOKEN="abc"\nSUPER_ADMIN_IDS=1,2\n', encoding="utf-8")
    assert read_env(f) == {"TELEGRAM_TOKEN": "abc", "SUPER_ADMIN_IDS": "1,2"}


def test_db_locked(tmp_path):
    import sqlite3
    from scripts.monitor import db_locked
    db = tmp_path / "x.db"
    c = sqlite3.connect(str(db)); c.isolation_level = None
    c.execute("CREATE TABLE t (a)")
    assert db_locked(db, wait_s=0.2) is False
    c.execute("BEGIN IMMEDIATE")
    assert db_locked(db, wait_s=0.2) is True
    c.execute("ROLLBACK"); c.close()
    assert db_locked(db, wait_s=0.2) is False
    assert db_locked(tmp_path / "нет.db") is False
