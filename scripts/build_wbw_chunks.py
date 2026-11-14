# -*- coding: utf-8 -*-
"""Пословные переводы мусхафа отдельными файлами по сурам (14.11.2026, wiki/wbw_split_plan.md).

Единственный источник - база (mufradat_words). Файлы - результат сборки, руками не правятся:

    mushaf_data/wbw/<язык>/<сура>.json   {"s": 2, "w": {"1:1": "Алиф Лам Мим", ...}}
    mushaf_data/wbw/manifest.json        {"ru": {"1": "a1b2c3d4", ...}, "ky": {...}}

Ключ слова - "аят:позиция" внутри суры: от раскладки не зависит, один файл служит обеим
раскладкам и тренажёру. Подпись - та же, что вшивал экспорт страниц
(scripts/export_mushaf_page.py): _clean_translation, «мусор» (_is_junk: «*», без букв) не кладём.
Нет слова на языке - приложение берёт ru (решение пользователя 30.08.2026), поэтому в
файлах ky/uz/zh только то, что реально переведено.

Хэш в манифесте - первые 8 знаков sha1 содержимого: приложение просит
wbw/<язык>/<сура>.json?h=<хэш>, исправили подпись - новый адрес, старый кэш не мешает.
Одинаковая база - одинаковые байты; неизменный файл не перезаписывается.
Запускать на сервере после загрузки переводов в базу (там база с ky/uz/zh).

    python scripts/build_wbw_chunks.py            # все языки из базы
    python scripts/build_wbw_chunks.py ru zh      # только эти
    python scripts/build_wbw_chunks.py --db путь --out путь
"""
import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.mufradat import _clean_translation, _is_junk  # noqa: E402

DEFAULT_DB = ROOT / "sources" / "hadiths.db"
DEFAULT_OUT = ROOT / "mushaf_data" / "wbw"


def collect(db_path, languages=None):
    """{язык: {сура: {"аят:позиция": подпись}}}"""
    with sqlite3.connect(str(db_path)) as conn:
        rows = conn.execute(
            "SELECT language, surah_number, ayah_number, position, translation "
            "FROM mufradat_words").fetchall()
    out = {}
    for lang, s, a, p, t in rows:
        if languages and lang not in languages:
            continue
        if t is None or _is_junk(t):
            continue
        t = _clean_translation(t)
        if not t:
            continue
        out.setdefault(lang, {}).setdefault(int(s), {})["%d:%d" % (a, p)] = t
    return out


def _sort_key(k):
    a, p = k.split(":")
    return int(a), int(p)


def chunk_bytes(surah, words):
    body = {"s": surah, "w": {k: words[k] for k in sorted(words, key=_sort_key)}}
    return json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def build(db_path=DEFAULT_DB, out_dir=DEFAULT_OUT, languages=None):
    """Пишет файлы и манифест. Возвращает (манифест, сколько файлов переписано)."""
    out_dir = Path(out_dir)
    data = collect(db_path, languages)
    man_path = out_dir / "manifest.json"
    manifest = json.loads(man_path.read_text(encoding="utf-8")) if man_path.exists() else {}
    written = 0
    for lang in sorted(data):
        lang_dir = out_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        hashes = {}
        for surah in sorted(data[lang]):
            raw = chunk_bytes(surah, data[lang][surah])
            hashes[str(surah)] = hashlib.sha1(raw).hexdigest()[:8]
            f = lang_dir / ("%d.json" % surah)
            if not f.exists() or f.read_bytes() != raw:
                f.write_bytes(raw)
                written += 1
        # суры, которых больше нет на языке, - убрать и из папки
        for f in lang_dir.glob("*.json"):
            if f.stem not in hashes:
                f.unlink()
                written += 1
        manifest[lang] = hashes
    raw = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if not man_path.exists() or man_path.read_text(encoding="utf-8") != raw:
        man_path.write_text(raw, encoding="utf-8")
    return manifest, written


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("languages", nargs="*")
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    manifest, written = build(args.db, args.out, set(args.languages) or None)
    for lang in sorted(manifest):
        print("%s: сур %d" % (lang, len(manifest[lang])))
    print("переписано файлов: %d" % written)


if __name__ == "__main__":
    main()
