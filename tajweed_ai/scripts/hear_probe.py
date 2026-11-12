# -*- coding: utf-8 -*-
"""Ветка «слух» (12.11.2026): есть ли в модели сигнал «это слово Умар устаз отметил бы»?

Вход: data/hear_results.jsonl + data/hear_emb/<id>.npz (hifz_eval.py --emb).
Модель заморожена; поверх представлений слова учим простой классификатор.

Правила (wiki/ai_tajweed_audio.md, 12.11):
- положительные - слова с пометкой Умар устаза (любой вердикт);
- отрицательные - непомеченные слова ТОЛЬКО принятых сдач (на пересдаче молчание = неизвестно);
- проверка по кругу, деление по студентам (ни один студент не в обучении и проверке сразу);
- контрольная планка: классификатор, который видит только само слово и этап, без звука.
  Засчитывается прирост над ней - иначе он просто запомнит «трудные слова»;
- ворота названы до прогона: AUC >= 0.85 - дальше к фильтру; 0.75-0.85 - сравнение с
  эталонным чтецом; < 0.75 - сигнала в модели нет, вкладываться в разметку.
  Цель - 100%, ворота - только решение о пути.

    python scripts/hear_probe.py [--boot 300]
"""
import argparse
import json
import re
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.feature_extraction import FeatureHasher
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "data" / "hear_results.jsonl"
EMB = ROOT / "data" / "hear_emb"
_HARAKAT = re.compile(r"[ً-ٰٟۖ-ۭـ]")


def letters(w):
    """Арабское сравниваем по буквам, без харакатов."""
    return _HARAKAT.sub("", w)


def load():
    X, y, grp, sub, word, extra = [], [], [], [], [], []
    n_sub = 0
    for line in RES.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        f = EMB / f"{r['id']}.npz"
        if not r.get("emb") or not f.exists() or r.get("verdict_by") and "Умар" not in r["verdict_by"]:
            continue
        z = np.load(f)
        emb, span = z["emb"].astype(np.float32), z["span"]
        marks = set(r["marks"])
        accepted = r["verdict"] == "accepted"
        words = [d for d in r.get("word_texts", [])] or None
        n_sub += 1
        flags = set(r["flag_any"])
        for wi in range(len(span)):
            if span[wi, 0] < 0:
                continue
            pos = wi in marks
            if not pos and not accepted:
                continue
            X.append(emb[wi].reshape(-1))
            y.append(int(pos))
            grp.append(r.get("student_id") or r["student"])
            sub.append(r["id"])
            w = words[wi] if words else ""
            word.append(letters(w))
            extra.append([r["stage"] or 1, (span[wi, 1] - span[wi, 0]), int(wi in flags),
                          wi / max(len(span) - 1, 1)])
    return (np.array(X), np.array(y), np.array(grp), np.array(sub), word,
            np.array(extra, dtype=np.float32), n_sub)


def cv_scores(make_model, feats, y, grp, n_splits=5):
    out = np.zeros(len(y))
    for tr, te in GroupKFold(n_splits=n_splits).split(feats, y, grp):
        m = make_model()
        m.fit(feats[tr], y[tr])
        out[te] = m.predict_proba(feats[te])[:, 1]
    return out


def boot_auc(y, s, grp, n=300, seed=1):
    rng = np.random.default_rng(seed)
    gs = np.unique(grp)
    idx = {g: np.where(grp == g)[0] for g in gs}
    vals = []
    for _ in range(n):
        ii = np.concatenate([idx[g] for g in rng.choice(gs, len(gs))])
        if 0 < y[ii].sum() < len(ii):
            vals.append(roc_auc_score(y[ii], s[ii]))
    return np.percentile(vals, [5, 95])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--boot", type=int, default=300)
    args = ap.parse_args()
    X, y, grp, sub, word, extra, n_sub = load()
    L = X.shape[1] // 1024
    print(f"сдач {n_sub}, слов {len(y)}, помеченных {int(y.sum())} ({y.mean():.1%}), "
          f"студентов {len(np.unique(grp))}, слоёв {L}")

    def logit():
        return make_pipeline(StandardScaler(), PCA(128, random_state=0),
                             LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced"))

    def logit_small():
        return make_pipeline(StandardScaler(with_mean=False),
                             LogisticRegression(C=0.3, max_iter=2000, class_weight="balanced"))

    hasher = FeatureHasher(n_features=4096, input_type="string")
    Wd = hasher.transform([[w] for w in word]).toarray().astype(np.float32)
    base_feats = np.hstack([Wd, extra[:, [0, 3]]])           # слово + этап + место в куске
    rows = [("планка: только слово, этап, место (без звука)", logit_small, base_feats),
            ("планка + длительность слова и флаг расхождения", logit_small, np.hstack([base_feats, extra[:, 1:3]]))]
    for li in range(L):
        rows.append((f"звук, слой {li + 1} из сохранённых", logit, X[:, li * 1024:(li + 1) * 1024]))
    rows.append(("звук, все слои вместе", logit, X))

    res = {}
    for name, mk, feats in rows:
        s = cv_scores(mk, feats, y, grp)
        lo, hi = boot_auc(y, s, grp, args.boot)
        res[name] = s
        print(f"  {name:52s} AUC {roc_auc_score(y, s):.3f}  (90%: {lo:.2f}–{hi:.2f})")

    s = res["звук, все слои вместе"]
    print("\nзвук, все слои: порог -> поймано пометок / доля слов под флагом / точность")
    for q in (0.99, 0.97, 0.95, 0.9, 0.8, 0.7, 0.5):
        t = np.quantile(s, q)
        f = s >= t
        print(f"  верхние {1 - q:4.0%} слов: поймано {int((f & (y == 1)).sum())}/{int(y.sum())} "
              f"({(f & (y == 1)).sum() / y.sum():.0%}), точность {y[f].mean():.1%}")


if __name__ == "__main__":
    main()
