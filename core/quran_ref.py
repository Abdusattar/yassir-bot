"""Детерминированная сверка муфрадат-слов с реальным текстом Корана.

Аудит 27.07.2026 (см. wiki/ai_verification.md) показал: модель проверяет
муфрадат "по памяти" (в справочнике нет текста конкретного аята), и это
даёт подтверждённые галлюцинации на боевых данных - например студент
написал وَارْكَعُوا (аят 2:43, дословно верно), а бот "исправил" на
несуществующее в Коране وَرَكَعُوا. Здесь - детерминированный индекс всех
слов Корана (114 сур, построен через quran_transcript оффлайн, см.
core/quran_word_index.json), чтобы отличать реальную ошибку от выдумки
модели без необходимости знать, какой именно аят сдаёт студент.
"""

import json
import os
import re
import unicodedata

_INDEX_PATH = os.path.join(os.path.dirname(__file__), "quran_word_index.json")
with open(_INDEX_PATH, encoding="utf-8") as _f:
    _QURAN_INDEX = json.load(_f)

# Те же диапазоны, что и в core/handlers.py (_HARAKAT_RE/_ARABIC_TOKEN_RE) -
# снимаем огласовки, НЕ трогаем хамзу/алиф/та-марбуту/алиф-максуру, это
# реальные различия, которые муфрадат обязан проверять.
_HARAKAT_RE = re.compile(r"[ً-ْـٰ]")
_ARABIC_TOKEN_RE = re.compile(r"[؀-ۿ]+")


def _normalize(word):
    word = unicodedata.normalize("NFC", word)
    return _HARAKAT_RE.sub("", word).strip()


def _levenshtein(a, b):
    if a == b:
        return 0
    if not a or not b:
        return max(len(a), len(b))
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        prev = cur
    return prev[-1]


def strip_quran_confirmed_words(verdict, submitted_text):
    """Убирает строки, где ИИ придирается к слову, которое студент написал
    ТОЧНО так, как оно есть в реальном тексте Корана - подтверждённая
    27.07.2026 галлюцинация, не настоящая ошибка. Консервативно: если не
    удаётся уверенно определить, о каком именно слове студента идёт речь
    в строке - строку не трогаем (не тот случай, где нужно рисковать)."""
    student_norms = {_normalize(t) for t in _ARABIC_TOKEN_RE.findall(submitted_text)}
    if not student_norms:
        return verdict

    lines = verdict.split("\n")
    keep = []
    for line in lines:
        line_tokens = _ARABIC_TOKEN_RE.findall(line)
        if not line_tokens:
            keep.append(line)
            continue

        referenced_norm = None
        for tok in line_tokens:
            tn = _normalize(tok)
            if tn in student_norms:
                referenced_norm = tn
                break

        if referenced_norm is None:
            # Ни один токен строки не встречается дословно в тексте студента
            # (например бот вывел только исправленную форму) - ищем ближайшее
            # слово студента (опечатка на 1-2 буквы: лишний/пропущенный
            # алиф/хамза и т.п.)
            best, best_dist = None, 3
            for tok in line_tokens:
                tn = _normalize(tok)
                if len(tn) < 3:
                    continue
                for sn in student_norms:
                    d = _levenshtein(tn, sn)
                    if d < best_dist:
                        best, best_dist = sn, d
            referenced_norm = best

        if referenced_norm is not None and referenced_norm in _QURAN_INDEX:
            continue  # слово студента дословно совпадает с Кораном - убираем строку
        keep.append(line)

    return "\n".join(keep).strip()
