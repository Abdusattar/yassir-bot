# -*- coding: utf-8 -*-
"""Сверка: файлы wbw/<язык>/<сура>.json против подписей, вшитых в страницы (14.11.2026).

До чистки страниц (wiki/wbw_split_plan.md, шаг 3) приложение должно показывать из wbw/ то же,
что показывало из page{N}[_lang].json. Правило приложения: подпись = своя на языке, иначе ru.
Печатает расхождения по языкам и раскладкам; код возврата 1, если они есть.

    python scripts/check_wbw_chunks.py [--wbw папка] [--pages папка mushaf_data] [язык ...]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_lang(wbw, lang):
    out = {}
    d = wbw / lang
    if d.exists():
        for f in d.glob("*.json"):
            j = json.loads(f.read_text(encoding="utf-8"))
            for k, v in j["w"].items():
                out["%d:%s" % (j["s"], k)] = v
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("languages", nargs="*")
    ap.add_argument("--wbw", default=str(ROOT / "mushaf_data" / "wbw"))
    ap.add_argument("--pages", default=str(ROOT / "mushaf_data"))
    ap.add_argument("--show", type=int, default=5)
    args = ap.parse_args()
    wbw, pages = Path(args.wbw), Path(args.pages)
    langs = args.languages or sorted(p.name for p in wbw.iterdir() if p.is_dir())
    ru = load_lang(wbw, "ru")
    bad_total = 0
    for lang in langs:
        loc = ru if lang == "ru" else load_lang(wbw, lang)
        suffix = "" if lang == "ru" else "_" + lang
        for lay, d in (("madina", pages), ("dm", pages / "dm")):
            files = words = bad = 0
            shown = []
            for n in range(1, 605):
                f = d / ("page%d%s.json" % (n, suffix))
                if not f.exists():
                    continue
                files += 1
                for a in json.loads(f.read_text(encoding="utf-8")).get("ayahs", []):
                    for t in a.get("tokens", []):
                        if t.get("type") != "word":
                            continue
                        k = "%d:%d:%d" % (a["surah"], a["ayah"], t["position"])
                        want = loc.get(k) or ru.get(k) or ""
                        words += 1
                        if (t.get("translation") or "") != want:
                            bad += 1
                            if len(shown) < args.show:
                                shown.append("    стр.%d %s: в странице «%s», в wbw «%s»"
                                             % (n, k, t.get("translation"), want))
            print("%s %s: страниц %d, слов %d, расхождений %d" % (lang, lay, files, words, bad))
            for s in shown:
                print(s)
            bad_total += bad
    sys.exit(1 if bad_total else 0)


if __name__ == "__main__":
    main()
