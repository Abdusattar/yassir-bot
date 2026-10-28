"""Китайский перевод уроков «Знаний» (28.10.2026) -> core/lessons_zh.json.

Перевод делал Claude по решению пользователя («все переводи на китайский»).
Исходники - i18n/lessons_zh/*.txt, блоки:

    === <id части в мужской базе>
    <тема по-китайски>
    ---
    <текст урока по-китайски>

Ключ текста - sha1 русского текста (первые 16 знаков), а не id: базы у
мужского и женского ботов разные, id частей могут разойтись, а текст один.
Поправили урок по-русски - хэш не совпадёт, и приложение честно покажет
русский, пока перевод не обновят (а не устаревший китайский).

    python scripts/build_lessons_zh.py --db quran_male.db
    python scripts/build_lessons_zh.py --ru-json lessons_ru.json   # выгрузка
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "core", "lessons_zh.json")
# Главы - общие для многих частей, переводятся здесь, а не в каждом блоке.
CHAPTERS = {
    "مخارج الحروف (Места выхода букв)": "مخارج الحروف（发音部位）",
    "صفات الحروف (Свойства букв)": "صفات الحروف（字母的特性）",
}


def content_key(text):
    return hashlib.sha1((text or "").strip().encode("utf-8")).hexdigest()[:16]


def read_blocks():
    out = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "i18n", "lessons_zh", "*.txt"))):
        raw = open(f, encoding="utf-8").read()
        for block in re.split(r"^=== ", raw, flags=re.M)[1:]:
            head, _, body = block.partition("\n---\n")
            lines = head.strip().split("\n")
            out[int(lines[0])] = {"topic": lines[1].strip(), "content": body.strip()}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--ru-json")
    a = ap.parse_args()
    if a.db:
        c = sqlite3.connect("file:%s?mode=ro" % a.db, uri=True)
        c.row_factory = sqlite3.Row
        ru = [dict(r) for r in c.execute("SELECT id, chapter, topic, content FROM curriculum_parts")]
    else:
        ru = json.load(open(a.ru_json, encoding="utf-8"))
    zh = read_blocks()
    topics, contents, miss = {}, {}, []
    for r in ru:
        t = zh.get(r["id"])
        if not t:
            miss.append(r["id"])
            continue
        topics[r["topic"]] = t["topic"]
        contents[content_key(r["content"])] = t["content"]
    json.dump({"_about": "Уроки «Знаний» на китайском; см. scripts/build_lessons_zh.py",
               "chapters": CHAPTERS, "topics": topics, "content": contents},
              open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print("переведено %d из %d -> %s" % (len(contents), len(ru), OUT))
    if miss:
        print("без перевода id:", miss)


if __name__ == "__main__":
    main()
