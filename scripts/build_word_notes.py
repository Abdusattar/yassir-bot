# -*- coding: utf-8 -*-
"""Пояснения к словам для приложения: mushaf_data/notes/ru.json (12.11.2026).

Некоторые слова одной русской подписью не передать (ар-Рахман и ар-Рахим, такъва,
«Ра‘ина»...). В подсказке по тапу у таких слов строка «Подробнее» -> панель с
коротким пояснением по тафсиру (mushaf_data/index.html, «Пояснение к слову»).
Источник - logs/wbw_ru_juz1/explain.json: тексты сверены с тафсиром аль-Муяссар /
ас-Саади (цитата quote_ar хранится там же), одобрены пользователем 12.11.

Формат: {"2:104:6": ["пояснение", "Тафсир аль-Муяссар"]} - ключ = data-w слова.

    python scripts/build_word_notes.py logs/wbw_ru_juz1/explain.json [ещё файлы...]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "mushaf_data" / "notes" / "ru.json"
SRC_NAME = {"Муяссар": "Тафсир аль-Муяссар", "ас-Саади": "Тафсир ас-Саади"}


def main():
    out = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    for f in sys.argv[1:]:
        for e in json.loads(Path(f).read_text(encoding="utf-8")):
            out[e["key"]] = [e["note"].strip(), SRC_NAME[e["source"]]]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"{OUT}: пояснений {len(out)}")


if __name__ == "__main__":
    main()
