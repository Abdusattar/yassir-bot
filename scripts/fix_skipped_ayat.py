# -*- coding: utf-8 -*-
"""Ручная реконсиляция 4 аятов, пропущенных scripts/ingest_mufradat.py
из-за расхождения в счёте слов между API Quran Academy и quran_transcript
(2:181, 8:6, 13:37, 37:130) - см. память project_mufradat_skipped_ayat.

Расхождение во всех 4 случаях - устойчивые сочетания ("после того как",
"Ильясину" = عَلَىٰٓ+يَاسِينَ), где API даёт один перевод сразу на
несколько арабских слов. Сопоставлено вручную по РЕАЛЬНЫМ данным обоих
источников (сессия 29.08.2026), ничего не выдумано - см.
feedback_never_invent_quran_translations. "*" - тот же маркер склейки,
что штатно расставляет ingest_mufradat.py для устойчивых сочетаний (см.
core/mufradat.py:_merge_glued_translations/_is_junk).

save_mufradat_word UPDATE-ит существующую строку (surah, ayah, position,
language) на месте, id/progress_key не трогает - идемпотентно, безопасно
запускать повторно (в т.ч. на сервере после синка ingest_mufradat.py,
который эти же 4 аята пропустит по той же причине).

Запускать вручную (в т.ч. на сервере после git pull):
    python scripts/fix_skipped_ayat.py
"""
import sys

sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import quran_transcript as qt
from core.sampler import save_mufradat_word

# (surah, ayah): [(position, translation), ...] - translation "*" где
# quran_transcript-слово поглощено переводом предыдущей позиции.
FIXES = {
    (2, 181): [
        (1, "А кто"), (2, "изменит его"), (3, "после того, как"), (4, "*"),
        (5, "услышал его,"), (6, "то ведь"), (7, "грех за это"),
        (8, "(только) на тех,"), (9, "которые"), (10, "изменяют это."),
        (11, "Поистине,"), (12, "Аллах —"), (13, "слышащий,"), (14, "знающий!"),
    ],
    (8, 6): [
        (1, "Препираются они с тобой"), (2, "об"), (3, "истине,"),
        (4, "после того как"), (5, "*"), (6, "она стала ясной"),
        (7, "как будто"), (8, "их гонят"), (9, "к"), (10, "смерти,"),
        (11, "в то время как они"), (12, "смотрят"),
    ],
    (13, 37): [
        (1, "И так"), (2, "Мы ниспослали его"), (3, "как свод постановлений"),
        (4, "на арабском языке."), (5, "Если же"), (6, "последуешь ты"),
        (7, "за прихотями их"), (8, "после того как"), (9, "*"),
        (10, "пришло к тебе"), (11, "из"), (12, "знания,"), (13, "то нет"),
        (14, "тебе"), (15, "от"), (16, "Аллаха"), (17, "ни"),
        (18, "покровителя,"), (19, "и ни"), (20, "защитника"),
    ],
    (37, 130): [
        (1, "«Мир"), (2, ""), (3, "Ильясину!»"), (4, "*"),
    ],
}

for (surah, ayah), positions in FIXES.items():
    uthmani_words = qt.Aya(surah, ayah).get().uthmani_words
    assert len(positions) == len(uthmani_words), \
        f"{surah}:{ayah} - число позиций реконсиляции ({len(positions)}) != qt ({len(uthmani_words)})"
    for (pos, translation), arabic in zip(positions, uthmani_words):
        save_mufradat_word(surah, ayah, pos, arabic, translation, "ru")
    print(f"{surah}:{ayah} - сохранено {len(positions)} слов")

print("\nDONE")
