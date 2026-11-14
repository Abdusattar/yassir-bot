# -*- coding: utf-8 -*-
"""Перевод джуза лежит в git - а в базу загружен? (14.11.2026, wiki/architecture.md С1)

Пословный ru живёт в i18n/wbw_ru/juz<N>.json, в базу (mufradat_words) попадает ручной
командой scripts/load_wbw_ru.py --apply: она переносит прогресс студентов, поэтому сама
на выкатке не запускается. Забытая команда = приложение показывает старые подписи, а в
git уже новые (14.11 так было час). Этот скрипт сверяет каждый файл с базой (только
чтение) и ведёт отметку `.wbw_ru_loaded.json` {имя файла: отпечаток загруженной версии}.
Наблюдение (scripts/monitor.py) по отметке напомнит, если файл не загружен дольше получаса.

Запускается сам: на каждой выкатке и в конце load_wbw_ru.py --apply.

    python scripts/check_wbw_ru_loaded.py          # сверить, обновить отметку; есть незагруженное - код 1
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sampler import HADITHS_DB  # noqa: E402

SRC = ROOT / "i18n" / "wbw_ru"
MARK = ROOT / ".wbw_ru_loaded.json"


def file_hash(path):
    return hashlib.sha1(Path(path).read_bytes()).hexdigest()[:12]


def pending(db_path, src_dir=SRC):
    """{имя файла: сколько подписей в файле отличается от базы}; -1 - файл не ложится на базу."""
    conn = sqlite3.connect("file:%s?mode=ro" % Path(db_path).as_posix(), uri=True)
    try:
        db = {(s, a, p): t for s, a, p, t in conn.execute(
            "SELECT surah_number, ayah_number, position, translation "
            "FROM mufradat_words WHERE language='ru'")}
    finally:
        conn.close()
    out = {}
    for f in sorted(Path(src_dir).glob("juz*.json")):
        n = 0
        for key, glosses in json.loads(f.read_text(encoding="utf-8")).items():
            s, a = map(int, key.split(":"))
            for p, g in enumerate(glosses, 1):
                if (s, a, p) not in db:
                    n = -1
                    break
                if g.strip() != db[(s, a, p)]:
                    n += 1
            if n < 0:
                break
        out[f.name] = n
    return out


def update_mark(db_path=HADITHS_DB, src_dir=SRC, mark=MARK):
    """Сверяет и переписывает отметку. Возвращает {имя: число расхождений}."""
    res = pending(db_path, src_dir)
    loaded = {name: file_hash(Path(src_dir) / name) for name, n in res.items() if n == 0}
    Path(mark).write_text(json.dumps(loaded, ensure_ascii=False, indent=1), encoding="utf-8")
    return res


def not_loaded(src_dir=SRC, mark=MARK, now=None, grace_s=1800):
    """Для наблюдения, без базы: файлы, чья нынешняя версия не отмечена загруженной и
    лежит дольше grace_s. Отметки нет вовсе - молчим (сверка ещё не запускалась)."""
    import time
    now = now or time.time()
    if not Path(mark).exists():
        return []
    loaded = json.loads(Path(mark).read_text(encoding="utf-8"))
    return [f.name for f in sorted(Path(src_dir).glob("juz*.json"))
            if loaded.get(f.name) != file_hash(f) and now - f.stat().st_mtime > grace_s]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    res = update_mark()
    bad = {k: v for k, v in res.items() if v}
    print("файлов джузов %d, загружено в базу %d" % (len(res), len(res) - len(bad)))
    for name, n in bad.items():
        print("  НЕ ЗАГРУЖЕН %s: %s" % (name, "не ложится на базу" if n < 0 else "%d подписей отличаются" % n))
    if bad:
        print("загрузить: venv/bin/python3 scripts/load_wbw_ru.py i18n/wbw_ru/<файл> --apply")
        sys.exit(1)


if __name__ == "__main__":
    main()
