# -*- coding: utf-8 -*-
"""Ветка «слух», быстрая прикидка шага «разница с эталоном» (12.11.2026, вечер).

Настоящая проверка - прогнать через модель эталонного чтеца (Хусари) и учить классификатор
на разнице «студент минус эталон». Это часы расчёта. Здесь - дешёвая замена на готовых
данных: эталоном для слова служит СРЕДНЕЕ представление того же слова у других студентов
в принятых сдачах без пометки («типичное чтение»). Идея та же: убрать из представления
само слово и оставить отклонение.

Честность проверки:
- деление по студентам (как в hear_probe): центр слова считается только по обучающей части,
  ни один студент не участвует и в центре, и в проверке;
- слова, у которых в обучающей части меньше MIN_REF чистых повторов, в проверку не идут -
  печатается покрытие; обычный «звук» и планка считаются на ТЕХ ЖЕ словах, чтобы сравнение
  было один к одному.

    python scripts/hear_probe_center.py
"""
import collections

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

import hear_probe as hp

MIN_REF = 3


def logit():
    return make_pipeline(StandardScaler(), PCA(64, random_state=0),
                         LogisticRegression(C=0.1, max_iter=2000, class_weight="balanced"))


def main():
    X, y, grp, sub, word, extra, n_sub = hp.load()
    word = np.array(word)
    L = X.shape[1] // 1024
    print(f"сдач {n_sub}, слов {len(y)}, помеченных {int(y.sum())}, студентов {len(np.unique(grp))}")
    s_dist = np.full(len(y), np.nan)      # расстояние до центра, без обучения
    s_diff = np.full(len(y), np.nan)      # классификатор на разнице
    s_raw = np.full(len(y), np.nan)       # классификатор на самом представлении (те же слова)
    for tr, te in GroupKFold(n_splits=5).split(X, y, grp):
        clean = tr[y[tr] == 0]
        by = collections.defaultdict(list)
        for i in clean:
            by[word[i]].append(i)
        cen = {w: X[ii].mean(axis=0) for w, ii in by.items() if len(ii) >= MIN_REF and w}
        tr_ok = np.array([i for i in tr if word[i] in cen])
        te_ok = np.array([i for i in te if word[i] in cen])
        if not len(te_ok) or y[tr_ok].sum() < 5:
            continue
        # В обучении чистое слово входит в собственный центр - вычитаем его вклад (иначе
        # разница у обучающих чистых слов была бы занижена, а у проверочных - нет).
        def diff(idx, own):
            out = np.empty((len(idx), X.shape[1]), dtype=np.float32)
            for k, i in enumerate(idx):
                c = cen[word[i]]
                if own and y[i] == 0:
                    n = len(by[word[i]])
                    c = (c * n - X[i]) / (n - 1)
                out[k] = X[i] - c
            return out
        d_tr, d_te = diff(tr_ok, True), diff(te_ok, False)
        # расстояние: средняя по слоям косинусная «непохожесть» на центр
        dist = np.zeros(len(te_ok))
        for li in range(L):
            a = X[te_ok, li * 1024:(li + 1) * 1024]
            c = np.stack([cen[word[i]][li * 1024:(li + 1) * 1024] for i in te_ok])
            dist += 1 - (a * c).sum(1) / (np.linalg.norm(a, axis=1) * np.linalg.norm(c, axis=1) + 1e-9)
        s_dist[te_ok] = dist / L
        m = logit().fit(d_tr, y[tr_ok])
        s_diff[te_ok] = m.predict_proba(d_te)[:, 1]
        m = logit().fit(X[tr_ok], y[tr_ok])
        s_raw[te_ok] = m.predict_proba(X[te_ok])[:, 1]
    ok = ~np.isnan(s_diff)
    print(f"покрытие: слов с центром {int(ok.sum())} из {len(y)} ({ok.mean():.0%}), "
          f"помеченных среди них {int(y[ok].sum())} из {int(y.sum())}")
    for name, s in (("расстояние до типичного чтения (без обучения)", s_dist),
                    ("классификатор на разнице «слово минус типичное»", s_diff),
                    ("классификатор на самом представлении (те же слова)", s_raw)):
        lo, hi = hp.boot_auc(y[ok], s[ok], grp[ok], 300)
        print(f"  {name:52s} AUC {roc_auc_score(y[ok], s[ok]):.3f}  (90%: {lo:.2f}–{hi:.2f})")
    # планка без звука на тех же словах: длительность слова, этап, место
    ex = extra[ok]
    sb = np.zeros(int(ok.sum()))
    yy, gg = y[ok], grp[ok]
    for tr, te in GroupKFold(n_splits=5).split(ex, yy, gg):
        m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced"))
        sb[te] = m.fit(ex[tr], yy[tr]).predict_proba(ex[te])[:, 1]
    lo, hi = hp.boot_auc(yy, sb, gg, 300)
    print(f"  {'планка: этап, длительность, флаг, место (без звука)':52s} AUC {roc_auc_score(yy, sb):.3f}  (90%: {lo:.2f}–{hi:.2f})")


if __name__ == "__main__":
    main()
