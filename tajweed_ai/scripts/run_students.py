# -*- coding: utf-8 -*-
"""
Прогон реальных студенческих записей (Бакыт/Сатар/Нурсултан) через
obadx/quran-muaalem — тест на настоящих ошибках, которые реально поймал
устаз Умар (в отличие от Гейта №0, где было только заведомо верное чтение).

ВАЖНАЯ ОГОВОРКА (см. wiki/ai_tajweed_audio.md, Тест 1/2, 21.07.2026):
то, что именно сказал Умар в голосовых коррекциях — это НЕПОДТВЕРЖДЁННАЯ
человеком транскрипция Gemini. Здесь мы её используем только как "куда
смотреть" ориентир, не как железную истину.
"""
import json
from pathlib import Path

import librosa
import torch

import quran_transcript as qt
from quran_muaalem import Muaalem
from quran_muaalem import explain as qm_explain
import diff_match_patch as dmp

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "students_run_results.json"

# Обычный обучающий профиль Hafs (не канонический чтец - студенты)
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

STUDENTS = {
    "Бакыт": {
        "audio": "Бакыт.mp3",
        "sura": 2,
        "ayat": list(range(106, 113)),
        "umar_flagged": [
            "аятин (2:106) — пропущен танвин/идгам",
            "ва май-йатабаддаль (2:108) — нет гунны",
            "аль-китаби (2:109) — нет сукуна",
        ],
    },
    "Сатар": {
        "audio": "Сатар.ogg",
        "sura": 2,
        "ayat": list(range(89, 94)),
        "umar_flagged": [
            "багьян (2:90) — пропуск изхара в танвине перед гортанной буквой",
        ],
    },
    "Нурсултан": {
        "audio": "Нурсултан.mp3",
        "sura": 2,
        "ayat": list(range(77, 84)),
        "umar_flagged": [
            "та'ламун→я'ламун (замена буквы, ок. 2:78)",
            "неправильная остановка после ан-нар (2:80)",
        ],
    },
}


def build_reference(sura, ayat):
    """quran_phonetizer падает (IndexError в process_sifat/alif_tafkheem_and_tarqeeq),
    если склеить истиазу/басмалу с текстом аятов - рассчитан только на чистый
    айатный текст. Реальные записи студентов начинаются с приветствия и
    истиазы/басмалы, которых тут нет - это ожидаемо даёт нерасшифровываемый
    "мусорный" префикс в diff (не текст Корана, сравнивать не с чем), после
    которого выравнивание само восстанавливается на реальном тексте аята."""
    uthmani_parts = [qt.Aya(sura, a).get().uthmani for a in ayat]
    combined = " ".join(uthmani_parts)
    return combined, qt.quran_phonetizer(combined, MOSHAF_GENERIC, remove_spaces=True)


def diff_table(predicted, ref_out):
    dmp_obj = dmp.diff_match_patch()
    diffs = dmp_obj.diff_main(ref_out.phonemes, predicted.phonemes.text)
    return qm_explain.expalin_sifat(predicted.sifat, ref_out.sifat, diffs)


def main():
    print("Загрузка модели...")
    muaalem = Muaalem(device="cpu", dtype=torch.float32)
    print("Готово.")

    results = {}
    for name, cfg in STUDENTS.items():
        print(f"\n=== {name} ===")
        uthmani, ref_out = build_reference(cfg["sura"], cfg["ayat"])
        print("Текст:", uthmani[:120], "...")

        audio_path = ROOT / "audio" / cfg["audio"]
        wave, _ = librosa.load(str(audio_path), sr=16000, mono=True)
        print(f"Аудио: {len(wave)/16000:.1f} сек")

        pred = muaalem([wave], [ref_out], sampling_rate=16000)[0]
        table = diff_table(pred, ref_out)

        n_exact = sum(1 for r in table if r["tag"] == "exact")
        n_total = len(table)
        from collections import Counter
        tag_counts = Counter(r["tag"] for r in table)
        mismatches = [r for r in table if r["tag"] != "exact"]

        print(f"Phoneme exact: {n_exact}/{n_total}, теги: {dict(tag_counts)}")
        print(f"Умар отметил: {cfg['umar_flagged']}")
        print("Несовпадения (partial/delete — реальные замены на конкретном месте, "
              "insert — обычно смещение выравнивания из-за пропуска/вставки где-то раньше):")
        for r in mismatches:
            print(f"   [{r['tag']}] ref={r.get('exp_phonemes')!r} -> pred={r.get('phonemes')!r}")

        results[name] = {
            "uthmani_reference": uthmani,
            "predicted_phonemes": pred.phonemes.text,
            "expected_phonemes": ref_out.phonemes,
            "n_phoneme_exact": n_exact,
            "n_phoneme_total": n_total,
            "umar_flagged": cfg["umar_flagged"],
            "diff_table": table,
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nСохранено: {OUT_PATH}")


if __name__ == "__main__":
    main()
