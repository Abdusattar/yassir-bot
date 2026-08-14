# -*- coding: utf-8 -*-
"""
Тест чувствительности на QDAT (23.07.2026) - см. лог сессии и advisor-совет:
Гейт №0 (obadx/quran-muaalem на Хусари/Афаси) измерил только specificity.
QDAT даёт настоящие экспертные метки correct/incorrect по трём правилам
таджвида на одном аяте (Аль-Маида 5:109) - это и есть тест sensitivity.

ВАЖНО (предупреждение ревьюера): статья QDAT разделяет "Separate stretching
of four movements" и "...five movements" как ДВЕ разные валидные категории
разметки текста, но в released CSV только ОДНА бинарная колонка "Separate
tide" - то есть оба варианта (4 и 5 харакят) пулятся в "correct". Поэтому
проверка мадда должна быть по ДЛИНЕ растяжки (порог), не по точному числу
символов - иначе завести тот же confound, что предупреждал ревьюер.
"""
import argparse
import json
from pathlib import Path
import time

import librosa
import pandas as pd
import torch

import quran_transcript as qt
from quran_muaalem import Muaalem

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qdat_common import extract_rule_signals, MADD_IDX, GHUNNAH_IDX, IKHFA_IDX

QDAT_ROOT = Path(r"C:\Users\Admi\.cache\kagglehub\datasets\annealdahi\quran-recitation\versions\1")
CSV_PATH = QDAT_ROOT / "QDAT_Quran Recitation.csv"
AUDIO_DIR = QDAT_ROOT / "FINAL SOUND" / "FINAL SOUND"

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "qdat_sensitivity_results.json"

MOSHAF_GENERIC = qt.MoshafAttributes(
    rewaya="hafs",
    recitation_speed="murattal",
    madd_monfasel_len=4,
    madd_mottasel_len=4,
    madd_mottasel_waqf=4,
    madd_aared_len=4,
    madd_alleen_len=4,
    madd_yaa_alayn_alharfy=6,
)

VERSE_UTHMANI = qt.Aya(5, 109).get().uthmani  # ровно тот текст, на котором считались rule_positions
# ВАЖНО: quran_phonetizer падает (IndexError) на произвольных подстроках аята -
# нужен полный аят целиком (внутреннее состояние зависит от контекста от начала).
# Реальные записи QDAT (8 сек) содержат только хвост "قالوا لا علم..." - это
# ОЖИДАЕМО даст несовпадение в начале выравнивания (недостающая голова текста),
# rule_positions (38/40/43) посчитаны на этом же полном тексте и остаются верны.


def madd_detected_len(signal):
    """Длина растяжки в предсказанном фрагменте (число повторов символа)."""
    if not signal["aligned"] or not signal["predicted_phonemes"]:
        return 0
    return len(signal["predicted_phonemes"])


def ghunnah_detected(signal):
    if not signal["aligned"]:
        return False
    return signal.get("ghonna") == "maghnoon"


def ikhfa_detected(signal):
    """Ихфа: назализованный символ (не обычный 'ن') + ghonna=maghnoon."""
    if not signal["aligned"]:
        return False
    has_nasal_symbol = signal["predicted_phonemes"] is not None and "ں" in signal["predicted_phonemes"]
    return has_nasal_symbol and signal.get("ghonna") == "maghnoon"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=20, help="сколько файлов прогнать (пилот)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    df = pd.read_csv(CSV_PATH)
    df = df.dropna(subset=["The tight noon"])  # 1 строка с NaN
    df = df.rename(columns={
        "Separate tide": "madd",
        "The tight noon": "ghunnah",
        "Concealment": "ikhfa",
    })
    sample = df.sample(n=min(args.n, len(df)), random_state=args.seed)

    print("Строим референс...")
    ref_out = qt.quran_phonetizer(VERSE_UTHMANI, MOSHAF_GENERIC, remove_spaces=True)
    print("Референс:", ref_out.phonemes)
    print("madd idx:", MADD_IDX, "ghunnah idx:", GHUNNAH_IDX, "ikhfa idx:", IKHFA_IDX)
    print("ожидаем на этих индексах:", ref_out.sifat[MADD_IDX].phonemes,
          ref_out.sifat[GHUNNAH_IDX].phonemes, ref_out.sifat[IKHFA_IDX].phonemes)

    print("Загрузка модели...")
    muaalem = Muaalem(device="cpu", dtype=torch.float32)
    print("Готово. Начинаю прогон...")

    results = []
    t0 = time.time()
    for i, row in enumerate(sample.itertuples()):
        wav_path = AUDIO_DIR / f"{row.title}.wav"
        if not wav_path.exists():
            print(f"  [skip] нет файла {wav_path}")
            continue
        wave, _ = librosa.load(str(wav_path), sr=16000, mono=True)
        pred = muaalem([wave], [ref_out], sampling_rate=16000)[0]
        signals = extract_rule_signals(pred, ref_out)

        row_result = {
            "title": row.title,
            "true_madd": int(row.madd),
            "true_ghunnah": int(row.ghunnah),
            "true_ikhfa": int(row.ikhfa),
            "pred_madd_len": madd_detected_len(signals["madd_munfasil"]),
            "pred_ghunnah": ghunnah_detected(signals["ghunnah"]),
            "pred_ikhfa": ikhfa_detected(signals["ikhfa"]),
            "signals": signals,
            "duration_sec": len(wave) / 16000,
        }
        results.append(row_result)
        elapsed = time.time() - t0
        print(f"[{i+1}/{len(sample)}] {row.title} true(madd={row_result['true_madd']},"
              f"ghunnah={row_result['true_ghunnah']},ikhfa={row_result['true_ikhfa']}) "
              f"pred(madd_len={row_result['pred_madd_len']},ghunnah={row_result['pred_ghunnah']},"
              f"ikhfa={row_result['pred_ikhfa']}) [{elapsed:.1f}s elapsed]")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nСохранено: {OUT_PATH}")
    print(f"Всего времени: {time.time()-t0:.1f} сек на {len(results)} файлов "
          f"({(time.time()-t0)/max(len(results),1):.2f} сек/файл)")


if __name__ == "__main__":
    main()
