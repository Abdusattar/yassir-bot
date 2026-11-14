# -*- coding: utf-8 -*-
"""
Нарезка мест «лишней растяжки» (madd_extra, rules_offline v2) для прослушивания
человеком (12.11.2026). Без инференса - по сохранённым pred_groups.

Два набора:
- hit   - флаг на слове, которое пометил Умар устаз (совпадение);
- false - флаг на принятой сдаче без пометок (ложная тревога?).
Вопрос прослушивания: ложные тревоги - это реальная лишняя растяжка, которую
устаз не отметил, или шум модели?

Время места - по позиции вставки в услышанной строке фонем:
доля от длины строки × длительность записи (грубо, поэтому окно ±5 с).

    HIFZ_RESULTS=data/hifz_eval_results_stage2.jsonl python scripts/listen_madd_extra.py
Итог: data/listen_madd_extra/*.wav + index.tsv (что слушать и куда записать ответ).
"""
import csv
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from rules_offline import MADD, load_rows  # noqa: E402

OUT = ROOT / "data" / "listen_madd_extra"
WIN = 5.0


def extra_places(r, qm_explain, dmp, fuzz, min_extra=2):
    """-> [(word_idx, pred_char_pos, out)] - как word_flags, но с позицией в pred."""
    ref_groups, word_groups = r["ref_groups"], r["word_groups"]
    ref = "".join(ref_groups)
    pred_all = [g["g"] for g in r["pred_groups"]]
    full_len = len("".join(pred_all))
    pred_groups, base = pred_all, 0
    if full_len > len(ref) * 1.15:
        al = fuzz.partial_ratio_alignment(ref, "".join(pred_all))
        if al is not None and al.dest_end > al.dest_start:
            starts, off = [], 0
            for g in pred_all:
                starts.append(off)
                off += len(g)
            keep = [(g, st) for g, st in zip(pred_all, starts)
                    if st + len(g) > al.dest_start and st < al.dest_end]
            pred_groups = [g for g, _ in keep]
            base = keep[0][1] if keep else 0
    pred = "".join(pred_groups)
    diffs = dmp.diff_match_patch().diff_main(ref, pred)
    groups = qm_explain.segment_groups(ref_groups, pred_groups, diffs)

    def word_of(ref_idx):
        for i, (lo, hi) in enumerate(word_groups):
            if lo is not None and lo <= ref_idx <= hi:
                return i
        return None

    places, last_word, pos = [], None, base
    for g in groups:
        out = g.out or ""
        if g.ref_idx is not None:
            w = word_of(g.ref_idx)
            if w is not None:
                last_word = w
        elif last_word is not None and len(out) >= min_extra and set(out) <= MADD:
            places.append((last_word, pos, out))
        pos += len(out)
    return places, full_len


def main():
    from quran_muaalem import explain as qm_explain
    import diff_match_patch as dmp
    from rapidfuzz import fuzz
    import librosa
    import soundfile as sf

    import quran_transcript as qt
    from hifz_eval import unit_words
    _aw = {}

    def word_text(r, wi):
        meta = json.loads((ROOT / "data" / "umar_corpus" / str(r["id"]) / "meta.json").read_text(encoding="utf-8"))
        words = unit_words(meta["hifz_page"], meta["hifz_line"] or 0, meta["hifz_stage"] or 1)
        if wi >= len(words):
            return "?"
        _, _, s_, a_, p_, _, _ = words[wi]
        if (s_, a_) not in _aw:
            _aw[(s_, a_)] = qt.Aya(s_, a_).get().uthmani_words
        return _aw[(s_, a_)][p_ - 1]

    rows = [r for r in load_rows() if r.get("verdict_by") == "Умар"
            and r["audio_sec"] / max(1, r["n_words"]) >= 0.3]
    hits, falses = [], []
    for r in rows:
        places, full_len = extra_places(r, qm_explain, dmp, fuzz)
        for w, pos, out in places:
            item = dict(id=r["id"], student=r["student"], page=r["page"], stage=r["stage"],
                        word_idx=w, word=None,
                        heard=out, t=round(pos / max(1, full_len) * r["audio_sec"], 1),
                        audio_sec=r["audio_sec"])
            if w in r["marks"]:
                hits.append(item)
            elif r["verdict"] == "accepted" and not r["marks"]:
                falses.append(item)
    print(f"мест: совпадений {len(hits)}, на чистых принятых {len(falses)}")

    rnd = random.Random(1112)
    pick = []
    for kind, pool, n in (("hit", hits, 8), ("false", falses, 10)):
        seen, chosen = set(), []
        for it in rnd.sample(pool, len(pool)):  # по одному месту на сдачу - разные голоса
            if it["id"] in seen:
                continue
            seen.add(it["id"]); chosen.append(dict(it, kind=kind))
            if len(chosen) == n:
                break
        pick += chosen
    rnd.shuffle(pick)  # слушать вслепую: вид места - только в index.tsv, не в имени файла

    by_id = {r["id"]: r for r in rows}
    for it in pick:
        it["word"] = word_text(by_id[it["id"]], it["word_idx"])
    OUT.mkdir(parents=True, exist_ok=True)
    for i, it in enumerate(pick, 1):
        start = max(0.0, it["t"] - WIN)
        wave, sr = librosa.load(str(ROOT / "data" / "umar_corpus" / str(it["id"]) / "student.ogg"),
                                sr=16000, mono=True, offset=start, duration=2 * WIN)
        it["file"] = f"{i:02d}.wav"
        it["clip_from"] = round(start, 1)
        sf.write(str(OUT / it["file"]), wave, sr)
    with open(OUT / "index.tsv", "w", encoding="utf-8", newline="") as f:
        cols = ["file", "word", "kind", "id", "student", "page", "stage", "word_idx", "heard",
                "t", "clip_from", "audio_sec"]
        wr = csv.DictWriter(f, fieldnames=cols + ["ответ"], delimiter="\t", extrasaction="ignore")
        wr.writeheader()
        for it in pick:
            wr.writerow(it)
    print(f"готово: {len(pick)} кусков в {OUT}")


if __name__ == "__main__":
    main()
