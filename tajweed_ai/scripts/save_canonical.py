"""Достаёт канонический текст Аль-Бакара 106-112 (стр.17) из Qrum и
сохраняет локально, чтобы не зависеть от соседнего проекта при анализе."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QRUM_PAGES = Path("D:/dev/qrum/assets/quran/pages.json")

pages = json.load(open(QRUM_PAGES, encoding="utf-8"))
page17 = next(p for p in pages if p["page"] == 17)

out = {
    "page": 17,
    "surah": page17["surah"],
    "ayah_range": page17["ayah"],
    "lines": page17["firstHalf"] + page17["secondHalf"],
}

with open(ROOT / "data" / "canonical_106_112.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)

print("saved", len(out["lines"]), "lines")
