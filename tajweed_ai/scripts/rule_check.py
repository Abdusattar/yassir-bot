# -*- coding: utf-8 -*-
"""Сверка модели с правилами Умар устаза - эмпирический путь (14.11.2026).

Решение пользователя 14.11: золотой стандарт - методика устаза (wiki/tajweed_ustaz_method.md),
к ней идём по данным: модель -> сверка с его разборами -> где расходимся, правим. Здесь три сверки,
всё локально, на готовых прогонах (как type_classifier.py), никуда не ходит:

1. Мадд в две стороны (правило 3): «недотянул» («нужно потянуть») и «перетянул короткую»
   («не тянем») - это разные ошибки; классификатор на каждое направление отдельно.
2. Мера «его слова в первых трёх модели» (правило 1): устаз называет 1-3 главные ошибки на сдачу,
   поэтому «непомеченное = чистое» неверно. Для каждой сдачи слова ранжируются по оценке модели
   (прогнозы вне обучения, деление по студентам) - попало ли названное им слово в первые k.
   Случайный уровень считается точно (гипергеометрически), а не перестановками: это их предел.
3. Правило 10 (пересдача / зачёт): простое правило из методики против его решения.

    python scripts/rule_check.py [--folds 5]
"""
import argparse
import collections
import json
import math
import re
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import type_signal as ts  # noqa: E402
import type_classifier as tc  # noqa: E402

OVER = re.compile(r"не\s+тян|не\s+надо\s+тян|не\s+нужно\s+тян|не\s+растяг|не\s+удлин|без\s+мадд|"
                  r"коротк|потянул|растянул|затянул|лишн", re.I)
UNDER = re.compile(r"потян|тянем|тянуть|тянется|харакат|мадд|удлин|долг", re.I)
KINDS = ["madd_under", "madd_over", "waqf_wasl", "harakat", "ghunna"]
NAMES = {"madd": "мадд (оба направления)", "madd_under": "мадд: недотянул",
         "madd_over": "мадд: перетянул короткую", "waqf_wasl": "остановка и переход",
         "harakat": "харакаты и шадда", "ghunna": "гунна"}


def madd_dir(quotes):
    """Направление по словам устаза: 'over' (не тянем) / 'under' (потянуть) / None."""
    votes = set()
    for q in quotes:
        q = q or ""
        if OVER.search(q):
            votes.add("over")          # «потянули… не тянем» - перетяжка
        elif UNDER.search(q):
            votes.add("under")
    return votes.pop() if len(votes) == 1 else None


def link_items(mark_word, items):
    """Как ts.link, но возвращает ещё и цитаты замечаний выбранного вида."""
    mw = ts.letters(mark_word)
    hits = []
    for i in items:
        iw = ts.letters(i.get("word") or "")
        if iw and mw and (mw in iw.split() or mw in iw or iw in mw):
            hits.append(i)
    if hits:
        t = collections.Counter(i["type"] for i in hits).most_common(1)[0][0]
        return t, "linked", [i.get("quote") for i in hits if i["type"] == t]
    types = {i["type"] for i in items if i.get("type")}
    if len(types) == 1:
        return next(iter(types)), "single", [i.get("quote") for i in items]
    return None, "unlinked", []


def collect():
    """Все слова: сдач с разбором устаза и принятых им сдач. Одна строка - одно слово."""
    model = ts.load_model_rows()
    voices = {str(json.loads(l)["id"]): json.loads(l)
              for l in ts.VOICE.read_text(encoding="utf-8").splitlines()}
    words = []
    for sid, r in model.items():
        v = voices.get(sid)
        by = r.get("verdict_by") or ""
        umar_accepted = r["verdict"] == "accepted" and not (by and "Умар" not in by)
        has_voice = False
        if v is not None:
            meta = json.loads((ts.CORPUS / sid / "meta.json").read_text(encoding="utf-8"))
            has_voice = meta.get("hifz_page") is not None
        if not (has_voice or umar_accepted):
            continue
        rows = tc.word_rows(r)
        g = str(r.get("student_id") or r["student"])
        kind = {}
        if has_voice:
            for wi, w in zip(r["marks"], r["marks_words"]):
                t, how, quotes = link_items(w, v.get("items") or [])
                k = t or "?"
                if t == "madd":
                    d = madd_dir(quotes)
                    k = "madd_" + d if d else "madd_?"
                kind[wi] = k
        else:
            for wi in r["marks"]:
                kind[wi] = "?"             # пометка без разбора: вид неизвестен
        for wi, d in enumerate(rows):
            words.append({"sid": sid, "wi": wi, "g": g, "feat": d, "kind": kind.get(wi),
                          "voice": has_voice, "accepted": umar_accepted})
    return words


def fit_oof(X, groups, y, train_ok, kind, folds):
    """Оценка каждого слова моделью, не видевшей его студента. train_ok - кого брать в обучение."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    s = np.full(len(y), np.nan)
    for tr, te in StratifiedGroupKFold(folds, shuffle=True, random_state=1).split(X, y, groups):
        tr = tr[train_ok[tr]]
        if kind == "lr":
            m = make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                              LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000))
        else:
            m = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                               l2_regularization=1.0, class_weight="balanced",
                                               random_state=1)
        m.fit(X[tr], y[tr])
        s[te] = m.predict_proba(X[te])[:, 1]
    return s


def p_any_topk(n, m, k):
    """Случайный порядок: вероятность, что из m названных слов хоть одно в первых k из n."""
    k = min(k, n)
    if m <= 0:
        return 0.0
    if n - m < k:
        return 1.0
    return 1.0 - math.comb(n - m, k) / math.comb(n, k)


def topk_report(title, subs, score, marked, ks=(1, 3, 5)):
    """subs: {sid: индексы слов}; score: оценка слова; marked: булев массив «названо устазом»."""
    hit = {k: [] for k in ks}
    rnd = {k: [] for k in ks}
    frac3, rfrac3, lens = [], [], []
    for idx in subs.values():
        idx = np.asarray(idx)
        m = int(marked[idx].sum())
        if m == 0:
            continue
        n = len(idx)
        lens.append(n)
        order = idx[np.argsort(-score[idx], kind="mergesort")]
        for k in ks:
            hit[k].append(float(marked[order[:k]].any()))
            rnd[k].append(p_any_topk(n, m, k))
        frac3.append(marked[order[:3]].sum() / m)
        rfrac3.append(min(3, n) / n)
    if not lens:
        print(f"  {title}: нет сдач")
        return None
    res = {"n": len(lens), "len": float(np.median(lens)),
           **{f"hit{k}": float(np.mean(hit[k])) for k in ks},
           **{f"rnd{k}": float(np.mean(rnd[k])) for k in ks},
           "frac3": float(np.mean(frac3)), "rfrac3": float(np.mean(rfrac3))}
    print(f"  {title}: сдач {res['n']}, слов в сдаче (медиана) {res['len']:.0f} | "
          + " | ".join(f"топ-{k}: {res[f'hit{k}']:.0%} (случайно {res[f'rnd{k}']:.0%})" for k in ks)
          + f" | доля названных слов в топ-3: {res['frac3']:.0%} (случайно {res['rfrac3']:.0%})")
    return res


# ── правило 10 ───────────────────────────────────────────────────────────────
HEAVY = {"harakat", "hifz", "makhraj", "other"}        # меняет слово/текст или порядок сдачи
LIGHT = {"madd", "waqf_wasl", "ghunna", "tempo", "qalqala", "sifat"}
NOT_FIXED = re.compile(r"не\s+исправ|опять|снова|ещё раз та же|та же ошибк", re.I)


def rule10(v, variant):
    types = [i.get("type") for i in v.get("items") or []]
    heavy = [t for t in types if t in HEAVY or (variant.get("sifat_heavy") and t == "sifat")]
    if heavy:
        return "retake"
    if variant.get("not_fixed") and NOT_FIXED.search(v.get("transcript") or ""):
        return "retake"
    if variant.get("many") and len(types) >= variant["many"]:
        return "retake"
    return "accepted"


def part3():
    voices = [json.loads(l) for l in ts.VOICE.read_text(encoding="utf-8").splitlines()]
    vs = [v for v in voices if v.get("verdict") in ("accepted", "retake") and v.get("items")]
    y = np.array([v["verdict"] for v in vs])
    print(f"\n== 3. Правило 10: разборов с решением {len(vs)} "
          f"(пересдача {np.mean(y == 'retake'):.0%}; «всегда зачёт» угадывает {np.mean(y == 'accepted'):.0%})")
    variants = [
        ("тяжёлый вид -> пересдача, иначе зачёт", {}),
        ("+ «не исправил» -> пересдача", {"not_fixed": True}),
        ("+ 3 и больше замечаний -> пересдача", {"not_fixed": True, "many": 3}),
        ("+ 4 и больше замечаний -> пересдача", {"not_fixed": True, "many": 4}),
        ("+ качества букв как тяжёлые", {"not_fixed": True, "many": 4, "sifat_heavy": True}),
    ]
    best = None
    for name, var in variants:
        p = np.array([rule10(v, var) for v in vs])
        acc = float(np.mean(p == y))
        rr = float(np.mean(p[y == "retake"] == "retake"))      # пересдач поймано
        ra = float(np.mean(p[y == "accepted"] == "accepted"))  # зачётов поймано
        print(f"  {name}: совпадение {acc:.0%} (пересдач распознано {rr:.0%}, зачётов {ra:.0%})")
        if best is None or acc > best[0]:
            best = (acc, name, var, p)
    acc, name, var, p = best
    print(f"  лучший вариант: {name}")
    miss_r = [v for v, pp in zip(vs, p) if v["verdict"] == "retake" and pp == "accepted"]
    miss_a = [v for v, pp in zip(vs, p) if v["verdict"] == "accepted" and pp == "retake"]
    print(f"  расхождения: устаз - пересдача, правило - зачёт: {len(miss_r)}; "
          f"устаз - зачёт, правило - пересдача: {len(miss_a)}")
    by = collections.Counter(tuple(sorted(set(i["type"] for i in v["items"]))) for v in miss_r)
    print("    пересдача при «лёгких» замечаниях, какие виды:", by.most_common(6))
    by = collections.Counter(t for v in miss_a for t in set(i["type"] for i in v["items"]) if t in HEAVY)
    print("    зачёт при «тяжёлом» замечании, какой вид:", by.most_common())
    for title, lst in (("пересдача при лёгких", miss_r), ("зачёт при тяжёлом", miss_a)):
        print(f"    примеры ({title}):")
        for v in lst[:4]:
            q = "; ".join(f"[{i['type']}] {(i.get('quote') or '')[:70]}" for i in v["items"][:3])
            print(f"      id {v['id']}: {q}")
    return acc


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    words = collect()
    names = sorted(words[0]["feat"])
    X = np.array([[w["feat"][k] for k in names] for w in words], dtype=float)
    G = np.array([w["g"] for w in words])
    kind = np.array([w["kind"] or "" for w in words])
    voice = np.array([w["voice"] for w in words])
    accepted = np.array([w["accepted"] for w in words])
    unmarked = kind == ""
    print(f"слов {len(words)}, сдач {len({w['sid'] for w in words})}, признаков {len(names)}")
    print("пометки по видам:", dict(collections.Counter(k for k in kind if k).most_common()))

    # ── 1. мадд в две стороны ────────────────────────────────────────────────
    print("\n== 1. Мадд в две стороны (деление по студентам, прогнозы вне обучения)")
    scores = {}
    for t in ["madd"] + KINDS:
        pos = np.isin(kind, ["madd_under", "madd_over", "madd_?"]) if t == "madd" else kind == t
        if pos.sum() < 15:
            print(f"  {NAMES[t]}: пометок {int(pos.sum())} - мало")
            continue
        y = pos.astype(int)
        out = {}
        for negname, negmask in (("все чистые", unmarked & accepted), ("те же записи", unmarked & voice)):
            use = pos | negmask
            for m in ("lr", "gb"):
                s = fit_oof(X, G, y, use, m, args.folds)
                out[(negname, m)] = (ts.auc(s[pos], s[negmask]), s)
        line = "; ".join(f"{n}: регрессия {out[(n, 'lr')][0]:.2f}, бустинг {out[(n, 'gb')][0]:.2f}"
                         for n in ("все чистые", "те же записи"))
        print(f"  {NAMES[t]}: пометок {int(pos.sum())}, студентов {len(set(G[pos]))} | {line}")
        # для ранжирования - модель, обученная на «тех же записях» (слово против слова той же сдачи)
        best = max(("lr", "gb"), key=lambda m: out[("те же записи", m)][0])
        scores[t] = out[("те же записи", best)][1]
        # что несёт сигнал: лучшие одиночные признаки на «тех же записях»
        neg = unmarked & voice
        single = []
        for j, k in enumerate(names):
            a = ts.auc(X[pos, j], X[neg, j])
            if not np.isnan(a):
                single.append((abs(a - 0.5), a, k))
        single.sort(reverse=True)
        print("      одиночные признаки: " + ", ".join(f"{k} {a:.2f}" for _, a, k in single[:6]))

    # ── 2. слова устаза в первых трёх модели ─────────────────────────────────
    print("\n== 2. Слова устаза в первых k по оценке модели (сдачи с его разбором)")
    subs = collections.defaultdict(list)
    for i, w in enumerate(words):
        if w["voice"]:
            subs[w["sid"]].append(i)
    clean = unmarked & accepted
    pct = {}
    for t in KINDS:
        if t in scores:                        # оценку вида -> доля чистых слов с оценкой ниже
            ref = np.sort(scores[t][clean])
            pct[t] = np.searchsorted(ref, scores[t]) / len(ref)
    marked_any = kind != ""
    res2 = {}
    if pct:
        P = np.vstack([pct[t] for t in pct])
        res2["max"] = topk_report("все пометки, оценка = максимум по видам", subs, P.max(0), marked_any)
        res2["sum"] = topk_report("все пометки, оценка = сумма по видам", subs, P.sum(0), marked_any)
    for t in KINDS:
        if t in pct:
            res2[t] = topk_report(f"{NAMES[t]}, оценка своего вида", subs, pct[t], kind == t)
    if "madd" in scores:
        res2["madd"] = topk_report("мадд (оба), общий классификатор мадда", subs, scores["madd"],
                                   np.isin(kind, ["madd_under", "madd_over", "madd_?"]))
    # старый способ для сравнения: одно правило прогона (расхождение с текстом)
    j = names.index("mismatch")
    topk_report("для сравнения: только флаг «расхождение с текстом»", subs,
                X[:, j] + 0.001 * np.nan_to_num(X[:, names.index("conf")]), marked_any)

    part3()


if __name__ == "__main__":
    main()
