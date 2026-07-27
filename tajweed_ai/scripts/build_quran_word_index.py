# -*- coding: utf-8 -*-
"""Строит core/quran_word_index.json - статический индекс всех слов Корана
для core/quran_ref.py (см. project_mufradat_quran_index_fix в памяти).

Требует quran_transcript (только локально, НЕ на сервере - сервер
использует уже готовый JSON). Запускать из корня репозитория:
    python tajweed_ai/scripts/build_quran_word_index.py

27.07.2026: индексируем И imlaey, И uthmani форму каждого слова
(нормализованные ОДНОЙ и той же функцией core.quran_ref._normalize), чтобы
студенты, копирующие текст в кораническом (uthmani) написании - со
значками рецитации и рسм-альтернацией و/ي+надстрочный алиф вместо ا
(ٱلصَّلَوٰةِ вместо الصلاة, аят 2:45) - тоже находили совпадение. НЕ
пытаемся угадывать по символам, какие уthmани-значки "декоративны" -
пробовали (расширить _HARAKAT_RE), сломало recall на реальной ошибке
(إِيلَافِهِمْ пишется إِۦلَـٰفِهِمْ - там small yeh это буква, не
украшение). Просто индексируем обе формы как есть - надёжнее угадывания.
"""
import json
import sys

import quran_transcript as qt

sys.path.insert(0, ".")
from core.quran_ref import _normalize

index = {}  # norm -> set of imlaey surface forms
for sura in range(1, 115):
    r0 = qt.Aya(sura, 1).get()
    n_ayat = r0.num_ayat_in_sura
    for i in range(1, n_ayat + 1):
        r = qt.Aya(sura, i).get()
        for iw, uw in zip(r.imlaey_words, r.uthmani_words):
            index.setdefault(_normalize(iw), set()).add(iw)
            index.setdefault(_normalize(uw), set()).add(iw)

compact = {k: sorted(v) for k, v in index.items()}

with open("core/quran_word_index.json", "w", encoding="utf-8") as f:
    json.dump(compact, f, ensure_ascii=False, separators=(",", ":"))

print("keys:", len(compact))
