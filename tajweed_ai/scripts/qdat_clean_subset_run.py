# -*- coding: utf-8 -*-
"""
Честный (не спутанный) тест sensitivity для мадда и ихфы на QDAT (23.07.2026).

Гунна исключена - счёт по CSV показал 0 файлов "чисто, кроме гунны" на всех
1509 размеченных записях (структурная корреляция меток, не артефакт пилота
n=19). Порог для гунны на этом датасете учить не на чем.

Для мадда и ихфы такие "чистые" подмножества есть (151 и 199 файлов) - в
паре с подвыборкой "все три правила верны" это даёт парное сравнение, где
меняется ТОЛЬКО проверяемое правило, два других зафиксированы как "верно"
в обеих группах. Так и sensitivity, и specificity меряются без confound'а
предыдущего пилота.
"""
import json
import time
from pathlib import Path

import librosa
import pandas as pd
import torch

import quran_transcript as qt
from quran_muaalem import Muaalem

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qdat_common import extract_rule_signals, MADD_IDX, IKHFA_IDX
from qdat_run import MOSHAF_GENERIC, VERSE_UTHMANI, madd_detected_len, ikhfa_detected

QDAT_ROOT = Path(r"C:\Users\Admi\.cache\kagglehub\datasets\annealdahi\quran-recitation\versions\1")
CSV_PATH = QDAT_ROOT / "QDAT_Quran Recitation.csv"
AUDIO_DIR = QDAT_ROOT / "FINAL SOUND" / "FINAL SOUND"

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "qdat_clean_subset_results.jsonl"

CONTROL_SAMPLE_N = 300  # подвыборка из "все три верны" (648) - фиксируем размер ради времени


def load_groups():
    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["The tight noon"])
    df = df.rename(columns={"Separate tide": "madd", "The tight noon": "ghunnah", "Concealment": "ikhfa"})

    clean_except_madd = df[(df["ghunnah"] == 1) & (df["ikhfa"] == 1) & (df["madd"] == 0)]
    clean_except_ikhfa = df[(df["madd"] == 1) & (df["ghunnah"] == 1) & (df["ikhfa"] == 0)]
    all_correct = df[(df["madd"] == 1) & (df["ghunnah"] == 1) & (df["ikhfa"] == 1)]
    control = all_correct.sample(n=min(CONTROL_SAMPLE_N, len(all_correct)), random_state=42)

    return clean_except_madd, clean_except_ikhfa, control


def already_done():
    if not OUT_PATH.exists():
        return set()
    done = set()
    for line in OUT_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            done.add(json.loads(line)["title"])
    return done


def main():
    clean_except_madd, clean_except_ikhfa, control = load_groups()
    print(f"Группа A (чисто кроме мадда, true_madd=0): {len(clean_except_madd)}")
    print(f"Группа B (чисто кроме ихфы, true_ikhfa=0): {len(clean_except_ikhfa)}")
    print(f"Контроль (все три верны, подвыборка): {len(control)}")

    rows = []
    for _, r in clean_except_madd.iterrows():
        rows.append(("madd_test", r))
    for _, r in clean_except_ikhfa.iterrows():
        rows.append(("ikhfa_test", r))
    for _, r in control.iterrows():
        rows.append(("control", r))

    done = already_done()
    print(f"Уже обработано ранее: {len(done)}")

    print("Строим референс...")
    ref_out = qt.quran_phonetizer(VERSE_UTHMANI, MOSHAF_GENERIC, remove_spaces=True)
    print("Загрузка модели Muaalem...")
    muaalem = Muaalem(device="cpu", dtype=torch.float32)
    print(f"Готово. Всего к обработке: {len(rows)} (пропустим уже готовые).")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    n_done = 0
    with open(OUT_PATH, "a", encoding="utf-8") as f:
        for i, (group, row) in enumerate(rows):
            if row.title in done:
                continue
            wav_path = AUDIO_DIR / f"{row.title}.wav"
            if not wav_path.exists():
                continue
            wave, _ = librosa.load(str(wav_path), sr=16000, mono=True)
            pred = muaalem([wave], [ref_out], sampling_rate=16000)[0]
            signals = extract_rule_signals(pred, ref_out)

            result = {
                "title": row.title,
                "group": group,
                "true_madd": int(row.madd),
                "true_ghunnah": int(row.ghunnah),
                "true_ikhfa": int(row.ikhfa),
                "pred_madd_len": madd_detected_len(signals["madd_munfasil"]),
                "pred_ikhfa": ikhfa_detected(signals["ikhfa"]),
                "madd_aligned": signals["madd_munfasil"]["aligned"],
                "ikhfa_aligned": signals["ikhfa"]["aligned"],
            }
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
            f.flush()
            n_done += 1

            if n_done % 20 == 0:
                elapsed = time.time() - t0
                rate = elapsed / n_done
                remaining = (len(rows) - len(done) - n_done) * rate
                print(f"[{n_done}/{len(rows)-len(done)}] {elapsed:.0f}с прошло, "
                      f"~{remaining:.0f}с осталось ({rate:.2f} сек/файл)")

    print(f"\nГотово. Всего строк в {OUT_PATH.name}: {len(done) + n_done}")


if __name__ == "__main__":
    main()
