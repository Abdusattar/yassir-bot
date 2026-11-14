# -*- coding: utf-8 -*-
"""Ночная копия баз с данными людей (14.11.2026, wiki/architecture.md, слой 1, долг Д1).

Копируются три базы: quran_male.db, quran_female.db, sources/hadiths.db - в них баллы,
сдачи, прогресс и входы; пересобрать их неоткуда. Копия снимается штатным механизмом
SQLite (backup API): боты при этом продолжают писать, копия получается целой.
Каждая копия проверяется (integrity_check), сжимается и кладётся в папку по дате;
хранится KEEP последних дней. Копия на том же диске спасает от ошибки скрипта и порчи
базы, но НЕ от потери диска - для этого нужна копия вне сервера (отдельное решение).

    python scripts/backup_db.py                 # ~/backups/db/ГГГГ-ММ-ДД/
    python scripts/backup_db.py --out путь --keep 7

Код возврата 1 и строка «ОШИБКА» - если хоть одна база не скопировалась (monitor/cron увидит).
"""
import argparse
import gzip
import shutil
import sqlite3
import sys
from contextlib import closing
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASES = ["quran_male.db", "quran_female.db", "sources/hadiths.db"]


def copy_one(src, dst_gz):
    tmp = dst_gz.with_suffix("")          # .db рядом, потом сжимаем
    # closing: «with sqlite3.connect» соединение не закрывает, а файл потом удаляется
    with closing(sqlite3.connect("file:%s?mode=ro" % src, uri=True)) as s, closing(sqlite3.connect(str(tmp))) as d:
        s.backup(d)
        ok = d.execute("PRAGMA integrity_check").fetchone()[0]
        tables = d.execute("SELECT count(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
    if ok != "ok" or not tables:
        tmp.unlink()
        raise RuntimeError("копия не прошла проверку: %s, таблиц %d" % (ok, tables))
    with open(tmp, "rb") as f, gzip.open(dst_gz, "wb", compresslevel=6) as g:
        shutil.copyfileobj(f, g)
    tmp.unlink()
    return tables, dst_gz.stat().st_size


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(Path.home() / "backups" / "db"))
    ap.add_argument("--keep", type=int, default=7)
    ap.add_argument("--root", default=str(ROOT))
    args = ap.parse_args()
    out, root = Path(args.out), Path(args.root)
    day = out / date.today().isoformat()
    day.mkdir(parents=True, exist_ok=True)
    failed = 0
    for rel in BASES:
        src = root / rel
        try:
            if not src.exists() or src.stat().st_size == 0:
                raise RuntimeError("базы нет или она пустая")
            tables, size = copy_one(src, day / (src.name + ".gz"))
            print("%s: таблиц %d, копия %.1f МБ" % (rel, tables, size / 1e6))
        except Exception as e:  # одна упавшая база не мешает скопировать остальные
            failed += 1
            print("ОШИБКА %s: %s" % (rel, e))
    if not failed:                        # старое убираем только после удачной ночи
        days = sorted(p for p in out.iterdir() if p.is_dir() and len(p.name) == 10)
        for old in days[:-args.keep]:
            shutil.rmtree(old)
            print("удалена старая копия %s" % old.name)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
