# -*- coding: utf-8 -*-
"""Сигнал по ВИДАМ ошибок (14.11.2026, wiki/ai_tajweed_audio.md «Сигнал по видам ошибок»).

12.11: модель почти не отличает слова, помеченные Умар устазом, от непомеченных. Подозрение -
под одной меткой лежат разные по природе ошибки. Здесь пометке слова даётся вид из голосового
разбора Умар устаза (data/ustaz_voice_classified.jsonl, scripts/ustaz_voice_classify.py), и уже
посчитанные признаки проверяются отдельно по видам. Ничего не считает моделью и никуда не ходит.

Шаг 1 - привязка: сдача (submission_id) есть и в голосовых, и в прогоне модели; помеченное слово
ищется среди слов замечаний по буквам без харакатов (замечание может быть фразой).
  linked     - слово пометки найдено в замечании;
  single     - не найдено, но в голосовом все замечания одного вида - берём его (слабее);
  unlinked   - не найдено, видов несколько.
Шаг 2 - признаки слова из готовых прогонов (hear_results / stage3_results / stage2):
  mismatch   - любое расхождение распознанного с текстом (flag_any);
  rule       - правило v2 сработало (flag_rule), long/short - растяжка длиннее/короче (hint);
  conf       - 1 - минимальная уверенность модели по звукам слова (pred_probs);
  dur        - длительность слова в кадрах на букву (hear_emb/*.npz, span);
  pause      - пауза после слова в кадрах (разрыв между span соседних слов).
Положительные - пометки данного вида; отрицательные - непомеченные слова ПРИНЯТЫХ Умар устазом
сдач (на пересдаче молчание = неизвестно), как в hear_probe.py. Деление по студентам - в
интервале (бутстреп по студентам). Мало примеров - так и печатается (n).

    python scripts/type_signal.py [--boot 500] [--dump data/type_marks.jsonl]
"""
import argparse
import collections
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
VOICE = DATA / "ustaz_voice_classified.jsonl"
CORPUS = DATA / "umar_corpus"
EMB = DATA / "hear_emb"
SOURCES = ["hear_results.jsonl", "stage3_results.jsonl", "hifz_eval_results_stage2_dedup.jsonl"]
_HARAKAT = re.compile("[ً-ٰٟۖ-ۭـ]")
_ALEF = str.maketrans("ٱأإآى", "ااااي")
FEATS = ["mismatch", "rule", "long", "short", "conf", "dur", "pause"]


def letters(w):
    """Арабское сравниваем по буквам, без харакатов; формы алифа - одна."""
    return _HARAKAT.sub("", w or "").translate(_ALEF)


def load_model_rows():
    """{id: строка прогона}; приоритет - hear (есть слова, уверенность, кадры)."""
    rows = {}
    for f in reversed(SOURCES):
        p = DATA / f
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            r["_src"] = f
            rows[str(r["id"])] = r
    return rows


def word_feats(r):
    """Список признаков по словам сдачи."""
    n = len(r["word_groups"])
    flags, rule = set(r["flag_any"]), set(r["flag_rule"])
    det = {int(k): v for k, v in (r.get("flag_detail") or {}).items()}
    probs = r.get("pred_probs")
    span = None
    f = EMB / f"{r['id']}.npz"
    if f.exists():
        span = np.load(f)["span"]
    words = r.get("word_texts") or []
    out = []
    for wi in range(n):
        hint = (det.get(wi) or {}).get("hint") or ""
        d = {"mismatch": float(wi in flags), "rule": float(wi in rule),
             "long": float("длиннее" in hint), "short": float("короче" in hint),
             "conf": np.nan, "dur": np.nan, "pause": np.nan}
        g0, g1 = r["word_groups"][wi]
        if probs and g1 < len(probs) and g1 >= g0:
            d["conf"] = 1.0 - float(min(probs[g0:g1 + 1]))
        if span is not None and wi < len(span) and span[wi, 0] >= 0:
            nlet = max(len(letters(words[wi])) if wi < len(words) else 0, 1)
            d["dur"] = float(span[wi, 1] - span[wi, 0] + 1) / nlet
            if wi + 1 < len(span) and span[wi + 1, 0] >= 0:
                d["pause"] = float(max(span[wi + 1, 0] - span[wi, 1] - 1, 0))
        out.append(d)
    return out


def link(mark_word, items):
    """Вид пометки по замечаниям голосового: (вид, способ)."""
    mw = letters(mark_word)
    hits = []
    for i in items:
        iw = letters(i.get("word") or "")
        if iw and mw and (mw in iw.split() or mw in iw or iw in mw):
            hits.append(i["type"])
    if hits:
        return collections.Counter(hits).most_common(1)[0][0], "linked"
    types = {i["type"] for i in items if i.get("type")}
    if len(types) == 1:
        return next(iter(types)), "single"
    return None, "unlinked"


def auc(pos, neg):
    """AUC по рангам (ничьи пополам); nan-ы выброшены."""
    pos, neg = pos[~np.isnan(pos)], neg[~np.isnan(neg)]
    if not len(pos) or not len(neg):
        return np.nan
    allv = np.concatenate([pos, neg])
    order = allv.argsort(kind="mergesort")
    ranks = np.empty(len(allv))
    sv = allv[order]
    i = 0
    while i < len(sv):
        j = i
        while j + 1 < len(sv) and sv[j + 1] == sv[i]:
            j += 1
        ranks[order[i:j + 1]] = (i + j) / 2 + 1
        i = j + 1
    return (ranks[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def boot(pos, pos_g, neg, neg_g, n, seed=1):
    rng = np.random.default_rng(seed)
    gs = np.unique(np.concatenate([pos_g, neg_g]))
    pi = {g: np.where(pos_g == g)[0] for g in gs}
    ni = {g: np.where(neg_g == g)[0] for g in gs}
    vals = []
    for _ in range(n):
        pick = rng.choice(gs, len(gs))
        p = np.concatenate([pos[pi[g]] for g in pick])
        q = np.concatenate([neg[ni[g]] for g in pick])
        a = auc(p, q)
        if not np.isnan(a):
            vals.append(a)
    return np.percentile(vals, [5, 95]) if vals else (np.nan, np.nan)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--dump")
    args = ap.parse_args()

    model = load_model_rows()
    voices = [json.loads(l) for l in VOICE.read_text(encoding="utf-8").splitlines()]
    st = collections.Counter()
    marks = []                       # пометки с видом
    for v in voices:
        st["голосовых"] += 1
        items = v.get("items") or []
        st["замечаний"] += len(items)
        st["замечаний без слова"] += sum(1 for i in items if not i.get("word"))
        meta = json.loads((CORPUS / str(v["id"]) / "meta.json").read_text(encoding="utf-8"))
        if meta.get("hifz_page") is None:
            st["голосовых: сдача не из приложения (нет страницы и пометок слов)"] += 1
            continue
        ew = meta.get("error_words") or []
        if not ew:
            st["голосовых: сдача из приложения без пометок слов"] += 1
        r = model.get(str(v["id"]))
        if r is None:
            st["голосовых: сдача вне прогонов модели"] += 1
            st["пометок вне прогонов модели"] += len(ew)
            continue
        st["голосовых: сдача в прогоне модели"] += 1
        st["пометок за пределами разобранного куска"] += len(r.get("marks_outside") or [])
        feats = word_feats(r)
        for wi, w in zip(r["marks"], r["marks_words"]):
            t, how = link(w, items)
            st["пометок в прогоне модели"] += 1
            st["  " + how] += 1
            marks.append({"id": v["id"], "student": str(r.get("student_id") or r["student"]), "wi": wi,
                          "word": w, "type": t, "how": how, **(feats[wi] if wi < len(feats) else {})})
    print("== Шаг 1. Привязка")
    for k, n in st.items():
        print(f"  {k}: {n}")
    by = collections.Counter((m["type"] or "-", m["how"]) for m in marks)
    print("  пометки по видам (вид, способ):", dict(sorted(by.items(), key=lambda x: -x[1])))
    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            for m in marks:
                f.write(json.dumps(m, ensure_ascii=False) + "\n")

    # отрицательные: непомеченные слова принятых Умар устазом сдач
    neg, neg_g, all_pos, all_pos_g = [], [], [], []
    for sid, r in model.items():
        by_name = r.get("verdict_by") or ""
        if by_name and "Умар" not in by_name:
            continue
        feats = word_feats(r)
        g = str(r.get("student_id") or r["student"])
        ms = set(r["marks"])
        for wi, d in enumerate(feats):
            if wi in ms:
                all_pos.append(d)
                all_pos_g.append(g)
            elif r["verdict"] == "accepted":
                neg.append(d)
                neg_g.append(g)
    neg_g = np.array(neg_g)
    N = {f: np.array([d[f] for d in neg], dtype=float) for f in FEATS}
    print(f"\n== Шаг 2. Признаки по видам (чистых слов {len(neg)}, студентов {len(set(neg_g))})")
    print("   0/1-признаки: доля сработавших у пометок / у чистых слов; AUC (90% интервал)")

    def report(name, rows, groups):
        groups = np.array([str(g) for g in groups])
        print(f"\n  {name}: пометок n={len(rows)}, студентов {len(set(groups))}"
              + ("  << МАЛО для вывода" if len(rows) < 30 else ""))
        for f in FEATS:
            p = np.array([d.get(f, np.nan) for d in rows], dtype=float)
            a = auc(p, N[f])
            lo, hi = boot(p, groups, N[f], neg_g, args.boot) if len(rows) >= 8 else (np.nan, np.nan)
            pv, nv = p[~np.isnan(p)], N[f][~np.isnan(N[f])]
            if not len(pv):
                desc = "- (нет данных)"
            elif f in ("mismatch", "rule", "long", "short"):
                desc = f"{pv.mean():.0%} / {nv.mean():.1%}"
            else:
                desc = f"медиана {np.median(pv):.2f} / {np.median(nv):.2f} (n={len(pv)})"
            print(f"    {f:9s} {desc:36s} AUC {a:.2f} ({lo:.2f}–{hi:.2f})")

    report("ВСЕ пометки Умар устаза (без вида, для сравнения)", all_pos, all_pos_g)
    types = collections.Counter(m["type"] for m in marks if m["type"])
    for t, _ in types.most_common():
        rows = [m for m in marks if m["type"] == t]
        report(f"вид {t}", rows, [m["student"] for m in rows])
        strict = [m for m in rows if m["how"] == "linked"]
        if 0 < len(strict) < len(rows):
            report(f"вид {t}, только привязанные по слову", strict, [m["student"] for m in strict])


if __name__ == "__main__":
    main()
