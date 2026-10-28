"""Перевод «Сорока хадисов» ан-Навави с HadeethEnc (28.10.2026, китайский).

HadeethEnc (hadeethenc.com, Энциклопедия переведённых хадисов) - реальный
источник смыслового перевода. Скрипт находит каждый из 42 хадисов
core/arbain.json.gz среди записей HadeethEnc по арабскому тексту (буквы без
огласовок) и сохраняет перевод: цепочку (intro), текст, источник.

    python scripts/fetch_arbain_hadeethenc.py --lang zh [--from 66500 --to 66600]

Результат - i18n/arbain_hadeethenc_<lang>.json: {n: {id, intro, text,
attribution, score}}. Пословные подписи сюда не входят: их на HadeethEnc нет.
"""
import argparse
import gzip
import json
import os
import re
import sys
import subprocess
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API = "https://hadeethenc.com/api/v1/hadeeths/one/?language=%s&id=%d"
_NOT_LETTER = re.compile("[^ء-ي ]")
_HARAKAT = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")


def letters(s):
    s = _HARAKAT.sub("", s or "").replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    return " ".join(_NOT_LETTER.sub(" ", s).split())


def get(lang, i, cache):
    key = "%s:%d" % (lang, i)
    if key not in cache:
        # Через curl: на запросы urllib сайт отвечает 403. Ошибки не кэшируем.
        r = subprocess.run(["curl", "-s", "-f", API % (lang, i)], capture_output=True)
        try:
            cache[key] = json.loads(r.stdout.decode("utf-8"))
        except ValueError:
            print("id %d: curl %d" % (i, r.returncode), file=sys.stderr)
            return {}
        time.sleep(0.2)
    return cache[key]


def overlap(a, b):
    """Доля слов хадиса из нашей базы, найденных в записи HadeethEnc."""
    wa, wb = a.split(), set(b.split())
    return sum(w in wb for w in wa) / max(len(wa), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--from", dest="lo", type=int, default=66500)
    ap.add_argument("--to", dest="hi", type=int, default=66560)
    ap.add_argument("--ids", default="", help="доп. id через запятую")
    a = ap.parse_args()
    cache_path = os.path.join(ROOT, "cache", "hadeethenc.json")
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    cache = json.load(open(cache_path, encoding="utf-8")) if os.path.exists(cache_path) else {}
    ids = list(range(a.lo, a.hi + 1)) + [int(x) for x in a.ids.split(",") if x]
    cand = {}
    for i in ids:
        rec = get(a.lang, i, cache)
        if rec.get("hadeeth_ar"):
            cand[i] = letters(rec["hadeeth_ar"])
    json.dump(cache, open(cache_path, "w", encoding="utf-8"), ensure_ascii=False)

    arbain = json.load(gzip.open(os.path.join(ROOT, "core", "arbain.json.gz")))
    out, miss = {}, []
    for h in arbain:
        # Только текст хадиса: фразы с учимыми словами (без строки источника).
        phs = [w["ph"] for w in h["words"] if w.get("ph") is not None]
        mine = letters(" ".join(p["ar"] for p in h["phrases"][h.get("matn_from", 0):max(phs) + 1]))
        best = max(cand.items(), key=lambda kv: overlap(mine, kv[1]), default=None)
        score = overlap(mine, best[1]) if best else 0
        if score < 0.6:
            miss.append((h["n"], round(score, 2), best and best[0]))
            continue
        rec = get(a.lang, best[0], cache)
        out[h["n"]] = {"id": best[0], "intro": rec.get("hadeeth_intro", ""),
                       "text": rec.get("hadeeth", ""), "attribution": rec.get("attribution", ""),
                       "score": round(score, 2)}
    dst = os.path.join(ROOT, "i18n", "arbain_hadeethenc_%s.json" % a.lang)
    json.dump(out, open(dst, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("найдено %d из %d -> %s" % (len(out), len(arbain), dst))
    for m in miss:
        print("нет:", m, file=sys.stderr)


if __name__ == "__main__":
    main()
