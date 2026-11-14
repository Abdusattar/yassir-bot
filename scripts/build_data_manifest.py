# -*- coding: utf-8 -*-
"""Единый список отпечатков данных мусхафа (14.11.2026, wiki/architecture.md Р1/С5).

Было: свежесть листов и смысла держалась на ручных номерах (DM_DATA_VER, MEANING_VER) -
забыли поднять, и телефон показывает старое. Стало: один файл

    mushaf_data/data_manifest.json
    {"v": 1,
     "page":    {"1": "a1b2c3d4", ...},                  # page<N>.json (Мадина)
     "dm":      {"1": "...", ...},                       # dm/page<N>.json (Дар аль-Маариф)
     "meaning": {"ru_kuliev": {"1": "...", ...}, ...},   # meaning/<перевод>/<сура>.json
     "wbw":     {"ru": {"1": "...", ...}, ...}}          # wbw/<язык>/<сура>.json

Отпечаток - первые 8 знаков sha1 содержимого файла. Приложение просит файл по адресу
`...json?h=<отпечаток>`: изменился файл - изменился адрес, старый кэш не мешает; не
изменился - телефон берёт из кэша и в сеть не ходит.

Это результат сборки: руками не править, в git не лежит (листы Мадины есть только на
сервере). Пересобирается сам: на каждой выкатке (deploy.yml), после загрузки переводов
(build_wbw_chunks.build) и после правки листов (patch_mushaf_ru.py). Языковые копии
листов (page<N>_ky.json ...) сюда не входят - они уходят (wiki/wbw_split_plan.md, шаг 3).

    python scripts/build_data_manifest.py
    python scripts/build_data_manifest.py --check    # список расходится с файлами - код 1
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DIR = ROOT / "mushaf_data"
NAME = "data_manifest.json"
_PAGE = re.compile(r"^page(\d+)\.json$")
_NUM = re.compile(r"^(\d+)\.json$")


def _h(path):
    return hashlib.sha1(path.read_bytes()).hexdigest()[:8]


def _numbered(folder, pattern):
    """{"номер": отпечаток} для файлов папки, подходящих под шаблон."""
    out = {}
    if folder.is_dir():
        for f in folder.iterdir():
            m = pattern.match(f.name)
            if m and f.is_file():
                out[m.group(1)] = _h(f)
    return dict(sorted(out.items(), key=lambda kv: int(kv[0])))


def _by_subdir(folder):
    """{"подпапка": {"номер": отпечаток}} - meaning/<перевод>/, wbw/<язык>/."""
    out = {}
    if folder.is_dir():
        for d in sorted(folder.iterdir()):
            if d.is_dir():
                files = _numbered(d, _NUM)
                if files:
                    out[d.name] = files
    return out


def collect(data_dir=DEFAULT_DIR):
    data_dir = Path(data_dir)
    return {
        "v": 1,
        "page": _numbered(data_dir, _PAGE),
        "dm": _numbered(data_dir / "dm", _PAGE),
        "meaning": _by_subdir(data_dir / "meaning"),
        "wbw": _by_subdir(data_dir / "wbw"),
    }


def _dump(man):
    return json.dumps(man, ensure_ascii=False, separators=(",", ":"))


def build(data_dir=DEFAULT_DIR):
    """Пишет data_manifest.json, если он изменился. Возвращает (список, переписан ли)."""
    data_dir = Path(data_dir)
    raw = _dump(collect(data_dir))
    path = data_dir / NAME
    if path.exists() and path.read_text(encoding="utf-8") == raw:
        return json.loads(raw), False
    tmp = path.with_name(NAME + ".tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(path)          # подмена разом: nginx не отдаст половину файла
    return json.loads(raw), True


def stale(data_dir=DEFAULT_DIR):
    """Список расходится с файлами на диске (или его нет) - True."""
    path = Path(data_dir) / NAME
    return not path.exists() or path.read_text(encoding="utf-8") != _dump(collect(data_dir))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.check:
        if stale(args.dir):
            print("data_manifest.json расходится с файлами: python scripts/build_data_manifest.py")
            sys.exit(1)
        print("data_manifest.json совпадает с файлами")
        return
    man, changed = build(args.dir)
    print("листов Мадины %d, Дар аль-Маариф %d, смысл: %s, слова: %s; %s" % (
        len(man["page"]), len(man["dm"]),
        ", ".join("%s %d" % (k, len(v)) for k, v in man["meaning"].items()) or "нет",
        ", ".join("%s %d" % (k, len(v)) for k, v in man["wbw"].items()) or "нет",
        "переписан" if changed else "без изменений"))


if __name__ == "__main__":
    main()
