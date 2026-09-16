"""Выгрузка шаблонов банка насых в markdown для сверки глазами (16.09.2026).

Требование пользователя: ни один шаблон не уходит студентам, пока человек не
сверил его с Кораном и хадисами (pick() отдаёт только approved=1). Скрипт
кладёт рядом с каждым шаблоном настоящий смысловой перевод упомянутого аята
(из mushaf_data/page*.json, Кулиев) и ближайший по словам хадис из кэша
переводов (hadith_translations) - чтобы сверка была сверкой, а не чтением.

    python scripts/export_nasiha_templates_md.py templates.json sources.json out.md [--sample 16] [--seed 1]

templates.json - строки nasiha_bank (template=1), sources.json - {"ayahs":[{sura,aya,text}],
"hadiths":[{hadith_id,collection,hadith_number,text}]} с сервера.
"""
import argparse
import glob
import json
import random
import re
import sys
from collections import Counter

REF_RES = [
    re.compile(r"сур[аеы]\s*(\d{1,3})\s*,?\s*аят[аеы]?\s*(\d{1,3})", re.I),
    re.compile(r"(?<!\d)(\d{1,3}):(\d{1,3})(?!\d)"),
    re.compile(r"аят[аеы]?\s*(\d{1,3})\s*сур[аеы]\s*(\d{1,3})", re.I),
]
COLLECTION_RE = re.compile(r"(Бухари|Муслим|Тирмизи|Абу Дауд|Насаи|Ибн Мадж[аe]|Ахмад|Малик|Дарими)", re.I)
LABELS = {"bukhari": "Бухари", "muslim": "Муслим", "tirmidhi": "Тирмизи", "abudawud": "Абу Дауд",
          "nasai": "Насаи", "ibnmajah": "Ибн Маджа", "ahmad": "Ахмад", "malik": "Малик", "darimi": "Дарими"}
WORD_RE = re.compile(r"[а-яё]{4,}", re.I)
STOP = set("аллах аллаха аллаху коран корана который которые которая этого этот когда если только просто тебя тебе твой твоя твои очень есть быть будет было чтобы потому ассаляму алейкум брат сестра name days".split())


def load_meanings():
    out = {}
    for path in glob.glob("mushaf_data/page*.json"):
        if "_" in path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][4:]:
            continue
        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        for a in d.get("ayahs", []):
            m = a.get("meaning")
            if m:
                out[(int(a["surah"]), int(a["ayah"]))] = m
    return out


def refs_in(text):
    found = []
    for i, rx in enumerate(REF_RES):
        for m in rx.finditer(text):
            s, a = int(m.group(1)), int(m.group(2))
            if i == 2:
                s, a = a, s
            if 1 <= s <= 114 and 1 <= a <= 286 and (s, a) not in found:
                found.append((s, a))
    return found


def words(text):
    return {w.lower() for w in WORD_RE.findall(text)} - STOP


def best_hadith(text, hadiths):
    tw = words(text)
    best, score = None, 0
    for h in hadiths:
        hw = words(h["text"])
        if not hw:
            continue
        s = len(tw & hw) / (len(hw) ** 0.5)
        if s > score:
            best, score = h, s
    return best, score


def main():
    p = argparse.ArgumentParser()
    p.add_argument("templates")
    p.add_argument("sources")
    p.add_argument("out")
    p.add_argument("--sample", type=int, default=0)
    p.add_argument("--seed", type=int, default=None)
    a = p.parse_args()
    rows = json.load(open(a.templates, encoding="utf-8"))
    src = json.load(open(a.sources, encoding="utf-8"))
    meanings = load_meanings()
    cached = {(r["sura"], r["aya"]): r["text"] for r in src["ayahs"]}
    hadiths = src["hadiths"]
    if a.sample:
        rnd = random.Random(a.seed)
        rows = sorted(rnd.sample(rows, a.sample), key=lambda r: (r["profile"], r["kind"], str(r["bucket"]), r["id"]))
    lines = ["# Шаблоны банка насых — сверка", "",
             f"Всего в файле: {len(rows)}. Под каждым шаблоном — что удалось найти для сверки: "
             "перевод аята по ссылке (Кулиев, из мусхафа приложения) и ближайший по словам хадис "
             "из кэша переводов бота. Пометка ✅/❌ — твоя, в столбце «Вердикт».", ""]
    stats = Counter()
    for r in rows:
        t = r["text"]
        lines += [f"## #{r['id']} · {r['profile']} · {r['kind']} · {r['bucket'] or '—'}", "",
                  "**Вердикт:** ☐ ok / ☐ править / ☐ удалить", "", "```", t.strip(), "```", ""]
        refs = refs_in(t)
        for s, ay in refs:
            real = meanings.get((s, ay)) or cached.get((s, ay))
            stats["ayah_ref"] += 1
            if real:
                lines.append(f"- **Аят {s}:{ay}, перевод по мусхафу:** {real}")
            else:
                lines.append(f"- **Аят {s}:{ay}:** перевода не нашёл ❗")
                stats["ayah_missing"] += 1
        cols = COLLECTION_RE.findall(t)
        if cols or "хадис" in t.lower() or "Пророк" in t or "ﷺ" in t:
            h, sc = best_hadith(t, hadiths)
            stats["hadith_ref"] += 1
            if h and sc >= 1.2:
                lines.append(f"- **Ближайший хадис в кэше** ({LABELS.get(h['collection'], h['collection'])} "
                             f"{h.get('hadith_number') or ''}, совпадение {sc:.1f}): {h['text']}")
            else:
                lines.append("- **Хадис:** в кэше переводов близкого не нашёл — сверить по сборнику вручную ❗")
                stats["hadith_missing"] += 1
        if not refs and not cols and "хадис" not in t.lower():
            lines.append("- Ссылок на аят или хадис в тексте нет.")
        lines.append("")
    lines += ["---", f"Аятов со ссылкой: {stats['ayah_ref']}, без найденного перевода: {stats['ayah_missing']}; "
              f"хадисов: {stats['hadith_ref']}, без близкого в кэше: {stats['hadith_missing']}."]
    open(a.out, "w", encoding="utf-8").write("\n".join(lines))
    print(f"{a.out}: {len(rows)} шаблонов; {dict(stats)}")


if __name__ == "__main__":
    main()
