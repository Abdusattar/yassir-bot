# -*- coding: utf-8 -*-
"""
Слой правил v2 поверх сохранённых групп Muaalem (hifz_eval_results.jsonl,
поля pred_groups/ref_groups/word_groups) - пересчёт БЕЗ инференса.

Что изменилось против июльского rule_hint (check_voices.py), по разбору
страницы 5074 (14.09.2026):
- "лишняя растяжка" - самое частое замечание Умар устаза («та не тянем»)
  - у модели это ВСТАВКА группы из символов мадда (ۥۥ/اا) сразу после
  слова; старый слой вставки молча пропускал (ref_idx None).
- гунна/ихфа (ں) считалась растяжкой - теперь отдельная категория.
- длину мунфасиля можно задать (2 или 4) - эталон пересобирается.

Категории флага на слово: madd_short, madd_long, madd_extra, ghunna_len.
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import os
# HIFZ_RESULTS (11.11.2026): прогон на арендованном GPU пишет/читает свой файл,
# чтобы не смешивать с домашним CPU-прогоном.
RESULTS_PATH = Path(os.environ["HIFZ_RESULTS"]) if os.environ.get("HIFZ_RESULTS") else ROOT / "data" / "hifz_eval_results.jsonl"

MADD = set("اۦۥ")
GHUNNA = "ں"


def load_rows():
    rows = [json.loads(l) for l in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if "pred_groups" in r]
    return rows


def word_flags(r, ref_groups, word_groups, qm_explain, dmp, fuzz, min_extra=2):
    """-> {word_idx: set(categories)}, детали для отладки."""
    ref = "".join(ref_groups)
    pred_groups = [g["g"] for g in r["pred_groups"]]
    pred = "".join(pred_groups)
    if len(pred) > len(ref) * 1.15:
        al = fuzz.partial_ratio_alignment(ref, pred)
        if al is not None and al.dest_end > al.dest_start:
            starts, off = [], 0
            for g in pred_groups:
                starts.append(off)
                off += len(g)
            pred_groups = [g for g, st in zip(pred_groups, starts)
                           if st + len(g) > al.dest_start and st < al.dest_end]
            pred = "".join(pred_groups)
    diffs = dmp.diff_match_patch().diff_main(ref, pred)
    groups = qm_explain.segment_groups(ref_groups, pred_groups, diffs)

    def word_of(ref_idx):
        for i, (lo, hi) in enumerate(word_groups):
            if lo is not None and lo <= ref_idx <= hi:
                return i
        return None

    flags = defaultdict(set)
    detail = []
    last_word = None
    for g in groups:
        tag = g.get_tag()
        if g.ref_idx is not None:
            w = word_of(g.ref_idx)
            if w is not None:
                last_word = w
            if tag == "exact" or w is None:
                continue
            rs = set(g.ref)
            if len(rs) == 1 and g.ref[0] in MADD:
                out_len = len(g.out or "")
                if out_len < len(g.ref):
                    flags[w].add("madd_short"); detail.append((w, "madd_short", g.ref, g.out))
                elif out_len > len(g.ref):
                    flags[w].add("madd_long"); detail.append((w, "madd_long", g.ref, g.out))
            elif len(rs) == 1 and g.ref[0] == GHUNNA:
                if len(g.out or "") != len(g.ref):
                    flags[w].add("ghunna_len"); detail.append((w, "ghunna_len", g.ref, g.out))
        else:  # вставка: студент произнёс то, чего в эталоне нет
            out = g.out or ""
            if last_word is not None and len(out) >= min_extra and set(out) <= MADD:
                flags[last_word].add("madd_extra"); detail.append((last_word, "madd_extra", "", out))
    return flags, detail


def rebuild_ref(r, monfasel, qt, build_reference, unit_words):
    meta = json.loads((ROOT / "data" / "umar_corpus" / str(r["id"]) / "meta.json").read_text(encoding="utf-8"))
    words = unit_words(meta["hifz_page"], meta["hifz_line"] or 0, meta["hifz_stage"] or 1)
    moshaf = qt.MoshafAttributes(rewaya="hafs", recitation_speed="murattal",
                                 madd_monfasel_len=monfasel, madd_mottasel_len=4, madd_mottasel_waqf=4,
                                 madd_aared_len=4, madd_alleen_len=4, madd_yaa_alayn_alharfy=6)
    _, ref, wg = build_reference(words, qt, moshaf)
    return [s.phonemes for s in ref.sifat], wg


def report(rows, cats, label):
    acc = [r for r in rows if r["verdict"] == "accepted" and not r["marks"]]
    mk = [r for r in rows if r["marks"]]
    tw = sum(r["n_words"] for r in acc)
    fw = sum(1 for r in acc for w, c in r["_flags"].items() if c & cats)
    clean = sum(1 for r in acc if not any(c & cats for c in r["_flags"].values()))
    tp = fp = fn = 0
    hit = 0
    for r in mk:
        f = {w for w, c in r["_flags"].items() if c & cats}
        m = set(r["marks"])
        tp += len(m & f); fp += len(f - m); fn += len(m - f); hit += bool(m & f)
    print(f"  {label:<34} принятые: {fw}/{tw} слов ({fw / max(1, tw):.1%}), чистых сдач {clean}/{len(acc)} | "
          f"помеченные: поймано {tp}/{tp + fn}, лишних {fp}, сдач с попаданием {hit}/{len(mk)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--monfasel", type=int, default=4)
    ap.add_argument("--ustaz", default="Умар")
    ap.add_argument("--stage", type=int)
    ap.add_argument("--show", help="id - показать пословно")
    args = ap.parse_args()

    from quran_muaalem import explain as qm_explain
    import diff_match_patch as dmp
    from rapidfuzz import fuzz
    import quran_transcript as qt
    from hifz_eval import build_reference, unit_words

    rows = load_rows()
    if args.ustaz:
        rows = [r for r in rows if r.get("verdict_by") == args.ustaz]
    if args.stage:
        rows = [r for r in rows if r["stage"] == args.stage]
    rows = [r for r in rows if r["audio_sec"] / max(1, r["n_words"]) >= 0.3]

    for r in rows:
        if args.monfasel == 4:
            ref_groups, wg = r["ref_groups"], r["word_groups"]
        else:
            ref_groups, wg = rebuild_ref(r, args.monfasel, qt, build_reference, unit_words)
        r["_flags"], r["_detail"] = word_flags(r, ref_groups, wg, qm_explain, dmp, fuzz)

    if args.show:
        r = next(x for x in rows if str(x["id"]) == args.show)
        words = [v["word"] for v in r["flag_detail"].values()]
        print(f"id {r['id']} {r['student']} стр.{r['page']} эт.{r['stage']} {r['verdict']}; пометки {r['marks']} {r['marks_words']}")
        for w in sorted(set(list(r["_flags"]) + r["marks"])):
            print(f"  {w:>3} {r['flag_detail'].get(str(w), {}).get('word', '?'):<16} "
                  f"{sorted(r['_flags'].get(w, []))} {'◀ ПОМЕТКА' if w in r['marks'] else ''}")
        return

    print(f"\nУстаз: {args.ustaz or 'все'}, мунфасиль {args.monfasel}, сдач {len(rows)} "
          f"(принятых без пометок {sum(1 for r in rows if r['verdict'] == 'accepted' and not r['marks'])}, "
          f"с пометками {sum(1 for r in rows if r['marks'])})")
    report(rows, {"madd_short", "madd_long", "madd_extra"}, "мадд (все три)")
    report(rows, {"madd_short"}, "  растяжка короче")
    report(rows, {"madd_long"}, "  растяжка длиннее (на месте мадда)")
    report(rows, {"madd_extra"}, "  лишняя растяжка (вставка)")
    report(rows, {"ghunna_len"}, "гунна/ихфа длина")
    report(rows, {"madd_short", "madd_long", "madd_extra", "ghunna_len"}, "всё вместе")

    kinds = Counter()
    for r in rows:
        if r["verdict"] == "accepted" and not r["marks"]:
            for (_, cat, ref, out) in r["_detail"]:
                kinds[(cat, ref[:1] or out[:1], len(ref), len(out or ""))] += 1
    print("\n  на принятых, виды (категория, символ, ожидалось, услышано):", kinds.most_common(10))


if __name__ == "__main__":
    main()
