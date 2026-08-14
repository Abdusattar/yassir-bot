# -*- coding: utf-8 -*-
"""
Gate 0, второй прогон (23.07.2026): obadx/quran-muaalem вместо TBOGamer22.

Разница с первым прогоном: используем собственный пайплайн проекта
(его модель + его референсный фонетайзер quran_transcript), без нашей
кустарной pointer-matching нарезки, которая была вероятным confound-ом
в результате 2/19 на TBOGamer22.

Меряем на заведомо верном чтении (Хусари, Афаси, аяты 106-112 Аль-Бакара)
раздельно по двум слоям:
  - phoneme-level: совпадает ли распознанная фонемная строка с эталоном
    (транскрипционный слой)
  - sifat-level: среди совпавших фонем, совпадают ли все 10 артикуляционных
    атрибутов (уровень суждения по таджвиду — то, что нам реально нужно)
"""
import json
from pathlib import Path

import diff_match_patch as dmp
import librosa
import torch

import quran_transcript as qt
from quran_muaalem import Muaalem
from quran_muaalem import explain as qm_explain

ROOT = Path(__file__).resolve().parent.parent
CONTROL_DIR = ROOT / "audio" / "control"
OUT_PATH = ROOT / "data" / "gate0_muaalem_results.json"

# Найдено через moshaf_metadata датасета obadx/muaalem-annotated-v3
# (id 0.0 = "المصحف المرتل بقصر المنفصل" — стандартный муратталь Хусари;
#  id 19.0 = Мишари аль-Афаси, муратталь)
MOSHAF_HUSARY = qt.MoshafAttributes(
    rewaya="hafs",
    recitation_speed="murattal",
    madd_monfasel_len=2,
    madd_mottasel_len=4,
    madd_mottasel_waqf=4,
    madd_aared_len=2,
    madd_alleen_len=2,
    madd_yaa_alayn_alharfy=4,
)

MOSHAF_AFASY = qt.MoshafAttributes(
    rewaya="hafs",
    recitation_speed="murattal",
    madd_monfasel_len=4,
    madd_mottasel_len=4,
    madd_mottasel_waqf=4,
    madd_aared_len=4,
    madd_alleen_len=4,
    madd_yaa_alayn_alharfy=6,
)

AYAT = list(range(106, 113))

RECITERS = {
    "husary": {
        "moshaf": MOSHAF_HUSARY,
        "file_tpl": "husary_002{ayah}.mp3",
    },
    "afasy": {
        "moshaf": MOSHAF_AFASY,
        "file_tpl": "002{ayah}.mp3",
    },
}


def sifat_diff_table(predicted, ref_phonemes_out):
    dmp_obj = dmp.diff_match_patch()
    predicted_phonemes = predicted.phonemes.text
    exp_phonemes = ref_phonemes_out.phonemes
    diffs = dmp_obj.diff_main(exp_phonemes, predicted_phonemes)
    return qm_explain.expalin_sifat(predicted.sifat, ref_phonemes_out.sifat, diffs)


def main():
    print("Загрузка модели obadx/muaalem-model-v3_2 (CPU, может занять время)...")
    muaalem = Muaalem(device="cpu", dtype=torch.float32)
    print("Модель загружена.")

    results = []

    for reciter, cfg in RECITERS.items():
        for ayah in AYAT:
            audio_path = CONTROL_DIR / cfg["file_tpl"].format(ayah=ayah)
            if not audio_path.exists():
                print(f"  [skip] нет файла: {audio_path}")
                continue

            uthmani = qt.Aya(2, ayah).get().uthmani
            ref_out = qt.quran_phonetizer(uthmani, cfg["moshaf"], remove_spaces=True)

            wave, _ = librosa.load(str(audio_path), sr=16000, mono=True)

            pred = muaalem([wave], [ref_out], sampling_rate=16000)[0]

            table = sifat_diff_table(pred, ref_out)

            n_groups = len(table)
            n_phoneme_exact = sum(1 for r in table if r["tag"] == "exact")
            n_phoneme_mismatch = n_groups - n_phoneme_exact

            attr_keys = [
                k
                for k in (table[0].keys() if table else [])
                if not k.startswith("exp_") and k not in ("tag", "phonemes", "exp_phonemes")
            ]
            n_sifat_checked = 0
            n_sifat_mismatch = 0
            for row in table:
                if row["tag"] != "exact":
                    continue
                for key in attr_keys:
                    n_sifat_checked += 1
                    if row.get(key) != row.get(f"exp_{key}"):
                        n_sifat_mismatch += 1

            row_result = {
                "reciter": reciter,
                "ayah": ayah,
                "predicted_phonemes": pred.phonemes.text,
                "expected_phonemes": ref_out.phonemes,
                "n_phoneme_groups": n_groups,
                "n_phoneme_exact": n_phoneme_exact,
                "n_phoneme_mismatch": n_phoneme_mismatch,
                "n_sifat_checked": n_sifat_checked,
                "n_sifat_mismatch": n_sifat_mismatch,
            }
            results.append(row_result)
            print(
                f"  {reciter} {ayah}: phoneme exact {n_phoneme_exact}/{n_groups}, "
                f"sifat mismatch {n_sifat_mismatch}/{n_sifat_checked}"
            )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    total_groups = sum(r["n_phoneme_groups"] for r in results)
    total_exact = sum(r["n_phoneme_exact"] for r in results)
    total_sifat_checked = sum(r["n_sifat_checked"] for r in results)
    total_sifat_mismatch = sum(r["n_sifat_mismatch"] for r in results)

    print("\n=== ИТОГ ===")
    if total_groups:
        print(
            f"Phoneme-level точное совпадение: {total_exact}/{total_groups} "
            f"({100 * total_exact / total_groups:.1f}%)"
        )
    if total_sifat_checked:
        print(
            f"Sifat-level ложные срабатывания (среди совпавших фонем): "
            f"{total_sifat_mismatch}/{total_sifat_checked} "
            f"({100 * total_sifat_mismatch / total_sifat_checked:.1f}%)"
        )
    print(f"Сохранено: {OUT_PATH}")


if __name__ == "__main__":
    main()
