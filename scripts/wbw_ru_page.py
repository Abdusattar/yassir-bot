# -*- coding: utf-8 -*-
"""Страница-таблица «другие слова в подписи» пословного ru (12.11.2026).

Берёт подписи Claude (<папка>/wbw_ru_new.json) и нынешние (sources/wbw_ru_refs),
оставляет только подписи, где слова стали другими (не знак, не только снятые
скобки/«досл.»/«однозначно»), и пишет HTML для публикации ссылкой (Artifact).

    python scripts/wbw_ru_page.py <out.html> [--from 1] [--to 17] [--dir logs/wbw_ru_juz1]
    python scripts/wbw_ru_page.py mushaf_data/wbw/index.html --to 21 --standalone   # yassirilm.com/wbw/
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.quran_pages import page_for_ayah  # noqa: E402

REFS = ROOT / "sources" / "wbw_ru_refs"


def _norm(x):
    return re.sub(r"[^\wё]", "", x.lower())


def _strip_marks(o):
    o = re.sub(r"\(досл\.?[^)]*\)|\[[^\]]*\]|\([^)]*\)", "", o)
    return re.sub(r"однозначно,?", "", o)


def collect(d, p_from, p_to):
    new = json.loads((d / "wbw_ru_new.json").read_text(encoding="utf-8"))
    notes = json.loads((d / "notes.json").read_text(encoding="utf-8")) if (d / "notes.json").exists() else {}
    rows, total = [], 0
    for key, glosses in new.items():
        s, a = map(int, key.split(":"))
        ref = json.loads((REFS / f"{s}_{a}.json").read_text(encoding="utf-8"))
        for w, g in zip(ref["words"], glosses):
            o, g = w["ru_now"].strip(), g.strip()
            if o == "*" or o == g or _norm(o) == _norm(g) or (o and _norm(_strip_marks(o)) == _norm(g)):
                continue
            total += 1
            p = page_for_ayah(s, a)
            if p_from <= p <= p_to:
                rows.append({"p": p, "k": key, "n": w["pos"], "ar": w["ar"], "o": o or "—", "g": g,
                             "why": notes.get(f"{key}:{w['pos']}", "")})
    return rows, total


TEMPLATE = Path(__file__).with_name("wbw_ru_page.html")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--from", dest="p_from", type=int, default=1)
    ap.add_argument("--to", dest="p_to", type=int, default=17)
    ap.add_argument("--dir", default=str(ROOT / "logs" / "wbw_ru_juz1"))
    ap.add_argument("--standalone", action="store_true",
                    help="своя страница на yassirilm.com (mushaf_data/wbw/), а не Artifact: с doctype")
    a = ap.parse_args()
    rows, total = collect(Path(a.dir), a.p_from, a.p_to)
    tpl = TEMPLATE.read_text(encoding="utf-8")
    data = json.dumps(rows, ensure_ascii=False).replace("</", "<\\/")
    out = (tpl.replace("__DATA__", data)
              .replace("__RANGE__", html.escape(f"{a.p_from}–{a.p_to}"))
              .replace("__COUNT__", str(len(rows)))
              .replace("__TOTAL__", str(total)))
    if a.standalone:
        out = '<!doctype html>\n<html lang="ru">\n' + out.replace(
            '<meta name="claude:viewport-fit-sides" content="cover">\n', "")
    Path(a.out).write_text(out, encoding="utf-8")
    print(f"{a.out}: строк {len(rows)} (страницы {a.p_from}–{a.p_to}), всего по папке {total}")


if __name__ == "__main__":
    main()
