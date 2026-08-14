# -*- coding: utf-8 -*-
"""
Общая логика для теста чувствительности на QDAT (23.07.2026).

Гейт №0 (gate0_muaalem.py) измерил только specificity (не путается ли
obadx/quran-muaalem на заведомо ВЕРНОМ чтении). QDAT даёт то, чего там не
было — размеченные ошибки: 1500 записей студентов на аяте Аль-Маида 109,
с ручной меткой correct/incorrect по трём правилам (Мадд мунфасиль, Гунна,
Ихфа). Задача этого модуля — для каждой записи достать из вывода модели
сигнал именно в той точке аята, где проверяется конкретное правило, и
сравнить с меткой QDAT.

Позиции правил в референсной фонетической разметке — см.
`data/qdat_verse_rule_positions.json` (посчитано отдельно, до скачивания
самого QDAT, см. лог сессии 23.07).
"""
import json
from pathlib import Path

import diff_match_patch as dmp

ROOT = Path(__file__).resolve().parent.parent
RULE_POSITIONS = json.loads(
    (ROOT / "data" / "qdat_verse_rule_positions.json").read_text(encoding="utf-8")
)

MADD_IDX = RULE_POSITIONS["rule_positions"]["madd_munfasil"]["sifat_index"]
GHUNNAH_IDX = RULE_POSITIONS["rule_positions"]["ghunnah"]["sifat_index"]
IKHFA_IDX = RULE_POSITIONS["rule_positions"]["ikhfa"]["sifat_index"]


def align_groups(predicted, ref_out):
    """То же выравнивание predicted-vs-reference, что и в gate0_muaalem.py
    (через quran_muaalem.explain), но возвращает сырые группы с индексами
    вместо готовой таблицы — нужно доставать конкретный ref_idx.
    """
    from quran_muaalem import explain as qm_explain

    dmp_obj = dmp.diff_match_patch()
    diffs = dmp_obj.diff_main(ref_out.phonemes, predicted.phonemes.text)
    ref_chunks = [s.phonemes for s in ref_out.sifat]
    pred_chunks = [s.phonemes_group for s in predicted.sifat]
    groups = qm_explain.segment_groups(ref_chunks, pred_chunks, diffs)
    return groups


def extract_rule_signals(predicted, ref_out):
    """Достаёт сигнал модели в трёх точках правил QDAT.

    Возвращает dict с тремя ключами (madd, ghunnah, ikhfa), каждый —
    dict с предсказанным и ожидаемым состоянием. Если выравнивание не
    нашло группу на нужном ref_idx (студент сильно исказил это место),
    сигнал помечается как aligned=False — это само по себе сильный сигнал
    (сильное расхождение с эталоном в этой точке).
    """
    groups = align_groups(predicted, ref_out)
    by_ref_idx = {g.ref_idx: g for g in groups if g.ref_idx is not None}

    def signal_for(idx, attr_name=None):
        g = by_ref_idx.get(idx)
        if g is None or g.out_idx is None:
            return {"aligned": False, "predicted_phonemes": None, "expected_phonemes": None}
        out = {
            "aligned": True,
            "predicted_phonemes": g.out,
            "expected_phonemes": g.ref,
        }
        if attr_name is not None and g.out_idx < len(predicted.sifat):
            sifa = predicted.sifat[g.out_idx]
            val = getattr(sifa, attr_name, None)
            out[attr_name] = val.text if val is not None else None
        return out

    return {
        "madd_munfasil": signal_for(MADD_IDX),
        "ghunnah": signal_for(GHUNNAH_IDX, attr_name="ghonna"),
        "ikhfa": signal_for(IKHFA_IDX, attr_name="ghonna"),
    }
