# -*- coding: utf-8 -*-
"""Компактный вид опор для перевода пачкой (12.11.2026): python scripts/wbw_ru_view.py 2:1 2:20 [--muyassar]"""
import json, sys
from pathlib import Path
REFS = Path(__file__).resolve().parent.parent / "sources" / "wbw_ru_refs"
a, b = sys.argv[1], sys.argv[2]
s, lo = map(int, a.split(":")); hi = int(b.split(":")[1])
for ay in range(lo, hi + 1):
    d = json.loads((REFS / f"{s}_{ay}.json").read_text(encoding="utf-8"))
    print(f"\n## {s}:{ay}\nК: {d['translations']['kuliev']}\nS: {d['translations']['saheeh']}")
    if "--muyassar" in sys.argv:
        print("M:", d["tafsir"]["muyassar_ar"])
    print(" ; ".join(f"{w['pos']} {w['ar']}={w['ru_now']}" for w in d["words"]))
