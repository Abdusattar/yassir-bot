# -*- coding: utf-8 -*-
"""Классификатор на каждый ВИД ошибки (14.11.2026, wiki/ai_tajweed_audio.md).

type_signal.py показал: одиночные признаки по видам дают AUC 0,61-0,72, ворота 0,75 не взяты.
Здесь - простые модели (логистическая регрессия и бустинг) на всех измеримых признаках слова.
Ничего не считает нейросетью и никуда не ходит: только готовые прогоны (hear / stage3 / stage2).

Признаки слова (семейства):
  struct - устройство слова по эталону: число звуковых групп, мадды и их длина, гунна,
           место в отрывке, последнее ли слово;
  align  - своё выравнивание распознанного с эталоном (difflib по группам): пропущено /
           заменено / вставлено, замена огласовки при той же согласной, замена согласной,
           мадд короче / длиннее (в харакатах), гунна короче, расхождение на конце слова;
  flags  - готовые флаги прогона: расхождение, правило v2, «короче»/«длиннее», delete/partial;
  conf   - уверенность модели по звукам слова;
  time   - длительность (кадры на букву, на группу, относительно медианы записи), пауза
           после слова (и относительно медианы записи).

Положительные - пометки Умар устаза данного вида (привязка как в type_signal.py);
отрицательные - непомеченные слова принятых им сдач. Два набора отрицательных:
  все       - любые чистые слова (модель может «угадывать» вид по устройству слова);
  подходящие - только слова, где такая ошибка возможна (мадд - есть мадд, гунна - есть гунна);
  те же записи - непомеченные слова ТЕХ ЖЕ сдач, где стоят пометки. Это главная проверка:
           принятые сдачи в целом чище, и на «всех чистых» модель отличает плохую запись от
           хорошей, а не слово от слова. Молчание устаза на пересдаче - не гарантия чистоты,
           поэтому цифра здесь - нижняя граница.
Оценка: GroupKFold по студенту, прогнозы вне обучения; AUC и полнота при точности >= 80%.

    python scripts/type_classifier.py [--folds 5] [--boot 300]
"""
import argparse
import collections
import difflib
import json
import re
import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import type_signal as ts  # noqa: E402

VOWELS = "َُِ"
MADD = "اۥۦ"
GHUNNA_CH = "ں۾"
TYPES = ["madd", "waqf_wasl", "ghunna", "harakat"]
_NUM = re.compile(r"ожидалось примерно (\d+).*?около (\d+)")


def gkey(g):
    """Группа без длины: повторы букв схлопнуты (мадд اا и اااا - один ключ)."""
    return re.sub(r"(.)\1+", r"\1", g)


def is_madd(g):
    return bool(g) and g[0] in MADD


def is_ghunna(g):
    return bool(g) and (g[0] in GHUNNA_CH or (g[0] in "نم" and len(g.rstrip(VOWELS)) >= 3))


def cons(g):
    return gkey(g).rstrip(VOWELS)


def align(ref, pred):
    """Для каждой группы эталона: ('eq'|'sub'|'del', индекс в pred или None); вставки - по месту."""
    rk, pk = [gkey(g) for g in ref], [gkey(g) for g in pred]
    sm = difflib.SequenceMatcher(None, rk, pk, autojunk=False)
    out = [("del", None)] * len(ref)
    ins = np.zeros(len(ref) + 1)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                out[i1 + k] = ("eq", j1 + k)
        elif tag == "replace":
            n = min(i2 - i1, j2 - j1)
            for k in range(n):
                out[i1 + k] = ("sub", j1 + k)
            if j2 - j1 > n and 0 < i1 < len(ref):
                ins[i2 - 1] += j2 - j1 - n
        elif tag == "insert" and 0 < i1 < len(ref):
            ins[i1 - 1] += j2 - j1
    return out, ins


def word_rows(r):
    """Признаки по каждому слову сдачи."""
    base = ts.word_feats(r)
    ref = r["ref_groups"]
    pg = r["pred_groups"]
    pred = [g["g"] for g in pg]
    win = r.get("window")
    off = 0
    if win:                                    # hear: эталон лежит в окне распознанного
        off = int(win[0])
        pred = pred[off:int(win[1]) + 1]
    al, ins = align(ref, pred)
    probs = r.get("pred_probs") or []
    det = {int(k): v for k, v in (r.get("flag_detail") or {}).items()}
    n = len(r["word_groups"])
    durs = np.array([b["dur"] for b in base], dtype=float)
    pauses = np.array([b["pause"] for b in base], dtype=float)
    med_d = np.nanmedian(durs) if np.isfinite(durs).any() else np.nan
    mean_p = np.nanmean(pauses) if np.isfinite(pauses).any() else np.nan
    rows = []
    for wi in range(n):
        g0, g1 = r["word_groups"][wi]
        gs = ref[g0:g1 + 1]
        a = al[g0:g1 + 1]
        d = dict(base[wi])
        ng = max(len(gs), 1)
        madds = [len(g) for g in gs if is_madd(g)]
        # struct
        d["s_ngroups"] = len(gs)
        d["s_nmadd"] = len(madds)
        d["s_maxmadd"] = max(madds) if madds else 0
        d["s_nghunna"] = sum(is_ghunna(g) for g in gs)
        d["s_last"] = float(wi == n - 1)
        d["s_pos"] = wi / max(n - 1, 1)
        d["s_endmadd"] = float(bool(gs) and is_madd(gs[-1]))
        d["s_endvowel"] = float(bool(gs) and gs[-1][-1] in VOWELS)
        # align
        n_del = n_sub = n_hsub = n_csub = 0
        m_short = m_long = 0.0
        m_del = 0
        gh_short = 0.0
        gh_lab = 0
        pp, nps = [], []
        for g, (tag, j) in zip(gs, a):
            if tag == "del":
                n_del += 1
                if is_madd(g):
                    m_del += 1
                    m_short = max(m_short, len(g))
                if is_ghunna(g):
                    gh_short = max(gh_short, len(cons(g)) and len(g.rstrip(VOWELS)))
                continue
            p = pred[j]
            if off + j < len(probs):
                pp.append(probs[off + j])
            meta = pg[off + j]
            if meta.get("np") is not None and meta.get("n") not in (None, "[PAD]"):
                nps.append(meta["np"])
            if tag == "sub":
                n_sub += 1
                if cons(g) == cons(p):
                    n_hsub += 1
                else:
                    n_csub += 1
            else:
                if is_madd(g):
                    m_short = max(m_short, len(g) - len(p))
                    m_long = max(m_long, len(p) - len(g))
                if is_ghunna(g):
                    gh_short = max(gh_short, len(g.rstrip(VOWELS)) - len(p.rstrip(VOWELS)))
                    if meta.get("n") == "not_maghnoon":
                        gh_lab += 1
        d["a_del"] = n_del / ng
        d["a_sub"] = n_sub / ng
        d["a_hsub"] = n_hsub
        d["a_csub"] = n_csub
        d["a_ins"] = float(ins[g0:g1 + 1].sum())
        d["a_bad"] = (n_del + n_sub) / ng
        d["a_mshort"] = m_short
        d["a_mlong"] = m_long
        d["a_mdel"] = m_del
        d["a_ghshort"] = gh_short
        d["a_ghlab"] = gh_lab
        d["a_endbad"] = float(bool(a) and a[-1][0] != "eq")
        d["a_enddel"] = float(bool(a) and a[-1][0] == "del")
        d["a_startbad"] = float(bool(a) and a[0][0] != "eq")
        # flags
        fd = det.get(wi) or {}
        tags = fd.get("tags") or []
        d["f_delete"] = float("delete" in tags)
        d["f_partial"] = float("partial" in tags)
        mm = _NUM.search(fd.get("hint") or "")
        d["f_hintdiff"] = float(int(mm.group(1)) - int(mm.group(2))) if mm else 0.0
        # conf
        d["c_min"] = 1 - min(pp) if pp else np.nan
        d["c_mean"] = 1 - float(np.mean(pp)) if pp else np.nan
        d["c_npmin"] = 1 - min(nps) if nps else np.nan
        # time
        nlet = max(len(ts.letters((r.get("word_texts") or [""] * n)[wi])), 1)
        d["t_durg"] = d["dur"] * nlet / ng if np.isfinite(d["dur"]) else np.nan
        d["t_durrel"] = d["dur"] / med_d if np.isfinite(d["dur"]) and med_d else np.nan
        d["t_pauserel"] = d["pause"] / (mean_p + 1) if np.isfinite(d["pause"]) else np.nan
        d["t_haspause"] = float(d["pause"] >= 3) if np.isfinite(d["pause"]) else np.nan
        rows.append(d)
    return rows


FAMILY = {"struct": "s_", "align": "a_", "flags": ("mismatch", "rule", "long", "short", "f_"),
          "conf": ("conf", "c_"), "time": ("dur", "pause", "t_")}
ELIGIBLE = {"madd": lambda d: d["s_nmadd"] > 0, "ghunna": lambda d: d["s_nghunna"] > 0}


def fam_of(name):
    for fam, pre in FAMILY.items():
        if name.startswith(pre):
            return fam
    return "?"


def collect():
    model = ts.load_model_rows()
    cache = {}

    def rows_of(sid):
        if sid not in cache:
            cache[sid] = word_rows(model[sid])
        return cache[sid]

    pos = collections.defaultdict(list)       # вид -> [(признаки, студент)]
    same = []                                 # непомеченные слова сдач, где есть пометки с видом
    voices = [json.loads(l) for l in ts.VOICE.read_text(encoding="utf-8").splitlines()]
    for v in voices:
        sid = str(v["id"])
        r = model.get(sid)
        if r is None:
            continue
        meta = json.loads((ts.CORPUS / sid / "meta.json").read_text(encoding="utf-8"))
        if meta.get("hifz_page") is None:
            continue
        rows = rows_of(sid)
        g = str(r.get("student_id") or r["student"])
        for wi, w in zip(r["marks"], r["marks_words"]):
            t, _how = ts.link(w, v.get("items") or [])
            if t and wi < len(rows):
                pos[t].append((rows[wi], g))
        if r["marks"]:
            ms = set(r["marks"])
            same += [(d, g) for wi, d in enumerate(rows) if wi not in ms]
    neg = []
    for sid, r in model.items():
        by = r.get("verdict_by") or ""
        if (by and "Умар" not in by) or r["verdict"] != "accepted":
            continue
        g = str(r.get("student_id") or r["student"])
        ms = set(r["marks"])
        for wi, d in enumerate(rows_of(sid)):
            if wi not in ms:
                neg.append((d, g))
    return pos, neg, same


def recall_at_precision(y, s, prec=0.8):
    from sklearn.metrics import precision_recall_curve
    p, rc, _ = precision_recall_curve(y, s)
    ok = rc[:-1][p[:-1] >= prec]
    return float(ok.max()) if len(ok) else 0.0


def oof(X, y, groups, kind, folds):
    """Прогнозы вне обучения, деление по студентам."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedGroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    s = np.zeros(len(y))
    for tr, te in StratifiedGroupKFold(folds, shuffle=True, random_state=1).split(X, y, groups):
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


def boot_auc(y, s, groups, n, seed=1):
    rng = np.random.default_rng(seed)
    gs = np.unique(groups)
    idx = {g: np.where(groups == g)[0] for g in gs}
    vals = []
    for _ in range(n):
        ii = np.concatenate([idx[g] for g in rng.choice(gs, len(gs))])
        if 0 < y[ii].sum() < len(ii):
            vals.append(ts.auc(s[ii][y[ii] == 1], s[ii][y[ii] == 0]))
    return np.percentile(vals, [5, 95])


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    warnings.filterwarnings("ignore")
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--boot", type=int, default=300)
    args = ap.parse_args()
    pos, neg, same = collect()
    names = sorted(k for k in neg[0][0])
    print(f"чистых слов {len(neg)}, признаков {len(names)}; виды:",
          {t: len(v) for t, v in sorted(pos.items(), key=lambda x: -len(x[1]))})

    def mat(items):
        return (np.array([[d[k] for k in names] for d, _ in items], dtype=float),
                np.array([g for _, g in items]))

    for t in TYPES:
        P = pos.get(t) or []
        if len(P) < 20:
            print(f"\n== {t}: пометок {len(P)} - мало")
            continue
        for label, N in (("все чистые", neg), ("те же записи", same),
                         ("подходящие", [x for x in neg if ELIGIBLE[t](x[0])] if t in ELIGIBLE else None)):
            if N is None:
                continue
            Pp = [x for x in P if ELIGIBLE[t](x[0])] if (label == "подходящие") else P
            Xp, gp = mat(Pp)
            Xn, gn = mat(N)
            X = np.vstack([Xp, Xn])
            y = np.r_[np.ones(len(Xp)), np.zeros(len(Xn))].astype(int)
            g = np.r_[gp, gn]
            print(f"\n== {t} / отрицательные: {label}. пометок {len(Xp)} (из {len(P)}), "
                  f"чистых {len(Xn)}, студентов с пометками {len(set(gp))}")
            single = []
            for j, k in enumerate(names):
                a = ts.auc(X[y == 1, j], X[y == 0, j])
                if not np.isnan(a):
                    single.append((max(a, 1 - a), a, k))
            single.sort(reverse=True)
            print("   лучшие одиночные признаки: " +
                  ", ".join(f"{k} {a:.2f}" for _, a, k in single[:6]))
            res = {}
            for kind in ("lr", "gb"):
                s = oof(X, y, g, kind, args.folds)
                a = ts.auc(s[y == 1], s[y == 0])
                lo, hi = boot_auc(y, s, g, args.boot)
                res[kind] = a
                # полнота при точности 80% - на исходной доле и на уравненной 1:1
                rc = recall_at_precision(y, s)
                w = np.r_[np.ones(len(Xp)), np.full(len(Xn), len(Xp) / len(Xn))]
                from sklearn.metrics import precision_recall_curve
                p_b, r_b, _ = precision_recall_curve(y, s, sample_weight=w)
                okb = r_b[:-1][p_b[:-1] >= 0.8]
                print(f"   {kind}: AUC {a:.3f} ({lo:.2f}–{hi:.2f}); полнота при точности>=80%: "
                      f"{rc:.0%} (как есть), {float(okb.max()) if len(okb) else 0:.0%} (если бы поровну)")
            best = "lr" if res["lr"] >= res["gb"] else "gb"
            # вклад семейств: модель без семейства и только на нём
            line = []
            for fam in FAMILY:
                keep = [j for j, k in enumerate(names) if fam_of(k) != fam]
                only = [j for j, k in enumerate(names) if fam_of(k) == fam]
                s1 = oof(X[:, keep], y, g, best, args.folds)
                s2 = oof(X[:, only], y, g, best, args.folds)
                line.append(f"{fam}: только {ts.auc(s2[y == 1], s2[y == 0]):.2f}, "
                            f"без {ts.auc(s1[y == 1], s1[y == 0]):.2f}")
            print(f"   семейства ({best}): " + "; ".join(line))
            keep = [j for j, k in enumerate(names) if fam_of(k) != "struct"]
            s3 = oof(X[:, keep], y, g, best, args.folds)
            print(f"   без устройства слова (только услышанное): AUC {ts.auc(s3[y == 1], s3[y == 0]):.3f}")


if __name__ == "__main__":
    main()
