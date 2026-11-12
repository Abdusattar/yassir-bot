# -*- coding: utf-8 -*-
"""
Этап 3, проверка потолка ДО фильтра (12.11.2026). Без инференса.

Вопрос: отличается ли уверенность модели (pred_probs) на словах, которые пометил
Умар устаз, от непомеченных? Особенно там, где расхождения с эталоном НЕТ: фильтр,
который только отсеивает готовые флаги, не поднимет А выше доли пометок с
расхождением (этап 2: 74%). Выше - только если сомнение модели само несёт сигнал.

Число - AUC: вероятность, что у случайного помеченного слова уверенность ниже,
чем у случайного непомеченного. 0.5 = сигнала нет.

    HIFZ_RESULTS=data/stage3_results.jsonl python scripts/stage3_ceiling.py
"""
import json
import os
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_PATH = Path(os.environ.get("HIFZ_RESULTS") or ROOT / "data" / "stage3_results.jsonl")


def word_conf(r, dmp, fuzz):
    """-> {word_idx: [вероятности символов услышанного, выровненных на слово]}."""
    ref_groups, word_groups = r["ref_groups"], r["word_groups"]
    ref = "".join(ref_groups)
    pred = r["pred_phonemes"].replace("[PAD]", "")
    probs = r["pred_probs"]
    assert len(pred) == len(probs)
    lo_p, hi_p = 0, len(pred)
    if len(pred) > len(ref) * 1.15:  # запись длиннее единицы - как в rules_offline
        al = fuzz.partial_ratio_alignment(ref, pred)
        if al is not None and al.dest_end > al.dest_start:
            lo_p, hi_p = al.dest_start, al.dest_end
    # символ эталона -> слово
    g_start, off = [], 0
    for g in ref_groups:
        g_start.append(off)
        off += len(g)
    g_start.append(off)
    char_word = [None] * len(ref)
    for wi, (lo, hi) in enumerate(word_groups):
        if lo is None:
            continue
        for c in range(g_start[lo], g_start[hi + 1]):
            char_word[c] = wi
    out = defaultdict(list)
    i, j, last = 0, lo_p, None
    for op, txt in dmp.diff_match_patch().diff_main(ref, pred[lo_p:hi_p]):
        n = len(txt)
        if op == 0:
            for k in range(n):
                w = char_word[i + k]
                if w is not None:
                    out[w].append(probs[j + k]); last = w
            i += n; j += n
        elif op == -1:  # в эталоне есть, не услышано
            for k in range(n):
                if char_word[i + k] is not None:
                    last = char_word[i + k]
            i += n
        else:  # услышано лишнее - относим к последнему слову
            if last is not None:
                out[last].extend(probs[j:j + n])
            j += n
    return out


def auc(pos, neg):
    """Доля пар (помеченное, непомеченное), где у помеченного значение НИЖЕ."""
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    # ранги с усреднением по совпадениям
    rank_sum, i = 0.0, 0
    while i < len(allv):
        k = i
        while k < len(allv) and allv[k][0] == allv[i][0]:
            k += 1
        avg = (i + 1 + k) / 2
        rank_sum += avg * sum(1 for t in allv[i:k] if t[1] == 1)
        i = k
    u = rank_sum - len(pos) * (len(pos) + 1) / 2  # сколько раз помеченное ВЫШЕ
    return 1 - u / (len(pos) * len(neg))


def main():
    import diff_match_patch as dmp
    from rapidfuzz import fuzz

    rows = [json.loads(l) for l in RESULTS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("verdict_by") == "Умар" and r.get("pred_probs")
            and r["audio_sec"] / max(1, r["n_words"]) >= 0.3]
    recs = []  # (student, stage, marked, deviation, min_p, mean_p)
    for r in rows:
        conf = word_conf(r, dmp, fuzz)
        marks, dev = set(r["marks"]), set(r["flag_any"])
        for wi, (lo, _) in enumerate(r["word_groups"]):
            if lo is None:
                continue
            ps = conf.get(wi)
            mn = min(ps) if ps else 0.0  # слово не услышано вовсе - уверенности нет
            mean = sum(ps) / len(ps) if ps else 0.0
            recs.append((r["student"], r["stage"], wi in marks, wi in dev, mn, mean))
    n_mark = sum(1 for x in recs if x[2])
    print(f"сдач {len(rows)}, слов {len(recs)}, помеченных {n_mark} ({n_mark / max(1, len(recs)):.1%})")
    md = sum(1 for x in recs if x[2] and x[3])
    print(f"пометок с расхождением у модели: {md}/{n_mark} ({md / max(1, n_mark):.0%}) - потолок А для фильтра по готовым флагам")

    def line(label, sel, col):
        pos = [x[col] for x in sel if x[2]]
        neg = [x[col] for x in sel if not x[2]]
        a = auc(pos, neg)
        # разброс: пересборка по студентам
        studs = sorted({x[0] for x in sel})
        by = defaultdict(list)
        for x in sel:
            by[x[0]].append(x)
        rnd, bs = random.Random(1112), []
        for _ in range(200):
            samp = [x for s in rnd.choices(studs, k=len(studs)) for x in by[s]]
            v = auc([x[col] for x in samp if x[2]], [x[col] for x in samp if not x[2]])
            if v == v:
                bs.append(v)
        bs.sort()
        ci = f"{bs[int(len(bs) * .05)]:.2f}–{bs[int(len(bs) * .95) - 1]:.2f}" if len(bs) > 20 else "—"
        print(f"  {label:<46} помеч. {len(pos):>4} / непомеч. {len(neg):>6}  AUC {a:.3f}  (90%: {ci})")

    for col, name in ((4, "самая низкая уверенность в слове"), (5, "средняя уверенность в слове")):
        print(f"\n{name}:")
        line("все слова", recs, col)
        line("слова БЕЗ расхождения (главный вопрос)", [x for x in recs if not x[3]], col)
        line("слова С расхождением", [x for x in recs if x[3]], col)
        line("  этап 1 (строка), все слова", [x for x in recs if x[1] == 1], col)
        line("  этапы 2–3, все слова", [x for x in recs if x[1] != 1], col)

    # наглядно: если на слове без расхождения поднять флаг при низкой уверенности
    clean = [x for x in recs if not x[3]]
    print("\nслова без расхождения: порог по самой низкой уверенности → пометок поймано / флагов всего / точность")
    for thr in (0.5, 0.6, 0.7, 0.8, 0.9):
        f = [x for x in clean if x[4] < thr]
        tp = sum(1 for x in f if x[2])
        tot = sum(1 for x in clean if x[2])
        print(f"  < {thr}: {tp}/{tot}, флагов {len(f)} ({len(f) / max(1, len(clean)):.1%} слов), точность {tp / max(1, len(f)):.1%}")


if __name__ == "__main__":
    main()
