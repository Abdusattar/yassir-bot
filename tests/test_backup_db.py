# -*- coding: utf-8 -*-
"""Ночная копия баз (scripts/backup_db.py, wiki/architecture.md Д1)."""
import gzip
import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "backup_db.py"


def _mk(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as c:
        c.execute("CREATE TABLE t (x)")
        c.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(rows)])


def _run(root, out, keep=7):
    return subprocess.run([sys.executable, str(SCRIPT), "--root", str(root), "--out", str(out),
                           "--keep", str(keep)], capture_output=True, text=True, encoding="utf-8")


def test_copies_are_readable_and_old_rotated(tmp_path):
    root, out = tmp_path / "r", tmp_path / "b"
    _mk(root / "quran_male.db", 5); _mk(root / "quran_female.db", 6); _mk(root / "sources" / "hadiths.db", 7)
    for d in ("2026-01-01", "2026-01-02", "2026-01-03"):
        (out / d).mkdir(parents=True)
    r = _run(root, out, keep=2)
    assert r.returncode == 0, r.stdout + r.stderr
    days = sorted(p.name for p in out.iterdir())
    assert len(days) == 2 and days[0] == "2026-01-03"          # вчерашняя + сегодняшняя
    today = out / days[-1]
    raw = gzip.open(today / "hadiths.db.gz").read()
    restored = tmp_path / "x.db"; restored.write_bytes(raw)
    assert sqlite3.connect(str(restored)).execute("SELECT count(*) FROM t").fetchone()[0] == 7


def test_missing_base_fails_loudly_and_keeps_old(tmp_path):
    root, out = tmp_path / "r", tmp_path / "b"
    _mk(root / "quran_male.db", 5); _mk(root / "sources" / "hadiths.db", 7)   # женской нет
    (out / "2026-01-01").mkdir(parents=True)
    r = _run(root, out, keep=1)
    assert r.returncode == 1 and "ОШИБКА quran_female.db" in r.stdout
    assert (out / "2026-01-01").exists()                         # при сбое старое не трогаем
