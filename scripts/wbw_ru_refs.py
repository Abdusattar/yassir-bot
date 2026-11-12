# -*- coding: utf-8 -*-
"""Опоры для пословного русского перевода (12.11.2026).

Пользователь: нынешний ru-пословный (Quran Academy = нарезанный Абу Адель)
плохо передаёт смысл аята. Делаем свой - Claude переводит, Gemini проверяет.
Чтобы перевод не был «из головы», на каждый аят собираются признанные опоры:

- разбивка и нынешняя подпись - mufradat_words (language='ru'), позиции НЕ меняем;
- разбор слова - Quranic Arabic Corpus (sources/quranic_corpus, корень/лемма/форма);
- английский пословный quran.com (позиции совпадают с нашими - проверено 2:106);
- смысловые: Кулиев (45), Абу Адель (79), Минвакф Египта (78), Saheeh
  International (20), Абдель Халим (85);
- тафсиры: аль-Муяссар (16, ар.) - арбитр по смыслу; ас-Саади (170, рус.).

Кэш - sources/wbw_ru_refs/<сура>_<аят>.json (повторный запуск в сеть не ходит).

    python scripts/wbw_ru_refs.py 2:2 2:7 3:7
"""
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.sampler import HADITHS_DB  # noqa: E402

OUT = ROOT / "sources" / "wbw_ru_refs"
QAC = ROOT / "sources" / "quranic_corpus" / "quran-morphology.txt"
API = "https://api.quran.com/api/v4"
TRANSLATIONS = {20: "saheeh", 85: "abdel_haleem", 45: "kuliev", 79: "abu_adel", 78: "awqaf_ru"}
TAFSIRS = {16: "muyassar_ar", 170: "saadi_ru"}
_TAG = re.compile(r"<[^>]+>")


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "wbw-refs/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception:  # noqa: BLE001 - сеть: повторить, потом упасть
            if attempt == 2:
                raise
            time.sleep(2)


def _clean(t):
    t = _TAG.sub("", t or "")
    return re.sub(r"\s+", " ", t).strip()


def qac_words(s, a):
    """{позиция: 'форма (POS ROOT:… LEM:…) + …'} по сегментам слова."""
    out = {}
    prefix = f"{s}:{a}:"
    with open(QAC, encoding="utf-8") as f:
        for line in f:
            if not line.startswith(prefix):
                continue
            loc, form, pos, feats = line.rstrip("\n").split("\t")
            w = int(loc.split(":")[2])
            keep = [x for x in feats.split("|") if x.startswith(("ROOT:", "LEM:"))
                    or x in ("PERF", "IMPF", "IMPV", "PASS", "ACT_PCPL", "PASS_PCPL", "VN",
                             "COND", "INTG", "NEG", "EMPH", "PRP", "RES", "EXP", "CERT")]
            out.setdefault(w, []).append(f"{form} {pos} {' '.join(keep)}".strip())
    return {w: " + ".join(v) for w, v in out.items()}


def fetch(s, a):
    path = OUT / f"{s}_{a}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    key = f"{s}:{a}"
    v = _get(f"{API}/verses/by_key/{key}?words=true&word_fields=text_uthmani&language=en"
             f"&translations={','.join(map(str, TRANSLATIONS))}")["verse"]
    en_words = [w["translation"]["text"] for w in v["words"] if w.get("char_type_name") == "word"]
    tr = {TRANSLATIONS[t["resource_id"]]: _clean(t["text"]) for t in v["translations"]}
    taf = {name: _clean(_get(f"{API}/tafsirs/{tid}/by_ayah/{key}")["tafsir"]["text"])
           for tid, name in TAFSIRS.items()}
    with sqlite3.connect(HADITHS_DB) as c:
        rows = c.execute("SELECT position, arabic_text, translation FROM mufradat_words "
                         "WHERE language='ru' AND surah_number=? AND ayah_number=? ORDER BY position",
                         (s, a)).fetchall()
    if len(rows) != len(en_words):
        raise SystemExit(f"{key}: у нас слов {len(rows)}, у quran.com {len(en_words)} - позиции не сходятся")
    qac = qac_words(s, a)
    data = {
        "key": key,
        "words": [{"pos": p, "ar": ar, "ru_now": ru, "en_wbw": en, "qac": qac.get(p, "")}
                  for (p, ar, ru), en in zip(rows, en_words)],
        "translations": tr,
        "tafsir": taf,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return data


def main():
    keys = sys.argv[1:]
    if not keys:
        raise SystemExit(__doc__)
    for k in keys:
        s, a = map(int, k.split(":"))
        d = fetch(s, a)
        print(f"{k}: слов {len(d['words'])}, переводов {len(d['translations'])}, "
              f"тафсиров {sum(1 for v in d['tafsir'].values() if v)}")


if __name__ == "__main__":
    main()
