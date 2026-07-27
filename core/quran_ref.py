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

# Индекс ключей по длине - для find_unconfirmed_words (перебор всех 14868
# ключей на каждое слово студента был бы медленным без этого).
_KEYS_BY_LEN = {}
for _k in _QURAN_INDEX:
    _KEYS_BY_LEN.setdefault(len(_k), []).append(_k)


def _normalize(word):
    word = unicodedata.normalize("NFC", word)
    word = _HARAKAT_RE.sub("", word).strip()
    # ٱ (алиф-васль, U+0671) - тот же алиф, просто уthmani-скрипт вариант
    # написания (студенты иногда копируют текст из приложений с уthmani-
    # шрифтом); не реальное различие в написании (27.07.2026, id=170).
    return word.replace("ٱ", "ا")


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


# Порог длины для find_unconfirmed_words (27.07.2026, разбор advisor):
# короткие арабские слова (< 4 букв после снятия огласовок) на расстоянии
# в 1 букву совпадают сразу с несколькими разными реальными словами Корана
# (напр. وم - на расстоянии 1 от وما/ومن/ثم и т.д.) - для них "ближайшее
# слово" ничего не значит, а флагать их было бы точно той же ошибкой,
# которую только что убрали в strip_quran_confirmed_words, просто с другой
# стороны. Порог 4 проверен на реальных данных (см.
# tajweed_ai/scripts/verify_quran_index_filter.py) - оба подтверждённых
# пропущенных случая (هلفهم, اخيه) проходят порог, ложных срабатываний на
# 16 flagged=0 записях не даёт.
_MIN_UNCONFIRMED_LEN = 4

# Хамза именно НА АЛИФЕ (أ/إ, туда же редкая آ) - единственная буква из
# того, что мы проверяем, у которой реальное ограничение стандартной
# арабской клавиатуры (Arabic 101): нет на основном слое, только через
# Shift/долгое нажатие на ا. В отличие от неё - голая хамза (ء), хамза на
# вав/я (ؤ/ئ), та-марбута (ة) и алиф-максура (ى) - все на основном слое,
# набираются так же легко, как обычная буква, так что различие там -
# по-прежнему настоящая ошибка (обсуждение с пользователем 27.07.2026,
# подтверждено поиском - arabictyping101.com/en/guide/arabic-101-keyboard).
_ALIF_HAMZA_FORMS = set("اأإآ")


def _is_alif_hamza_only_diff(a, b):
    """True, если единственное различие между a и b (расстояние
    Левенштейна == 1) - это одна форма алифа (ا/أ/إ/آ) вместо другой."""
    if len(a) == len(b):
        diffs = [(x, y) for x, y in zip(a, b) if x != y]
        return len(diffs) == 1 and diffs[0][0] in _ALIF_HAMZA_FORMS and diffs[0][1] in _ALIF_HAMZA_FORMS
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    for i in range(len(longer)):
        if longer[:i] + longer[i + 1:] == shorter:
            return longer[i] in _ALIF_HAMZA_FORMS
    return False


def find_unconfirmed_words(submitted_text):
    """Ищет арабские слова студента, которых НЕТ в тексте Корана даже после
    снятия огласовок, но которые однозначно (единственный кандидат) близки
    (расстояние ровно 1 буква) к одному реальному слову Корана - вероятная
    пропущенная ошибка (см. Бекхан هلفهم/خلفهم, Абдульвахид اخيه/أخيه -
    оба пропущены ИИ 25-26.07.2026). Консервативно в обе стороны: слова
    короче _MIN_UNCONFIRMED_LEN и неоднозначные случаи (2+ равнозначных
    кандидата) не трогаем - не гадаем там, где не уверены. Возвращает
    список (исходное_слово, ближайшее_слово_из_Корана)."""
    seen = set()
    findings = []
    for tok in _ARABIC_TOKEN_RE.findall(submitted_text):
        n = _normalize(tok)
        if len(n) < _MIN_UNCONFIRMED_LEN or n in seen or n in _QURAN_INDEX:
            continue
        seen.add(n)

        candidates = set()
        for length in (len(n) - 1, len(n), len(n) + 1):
            for key in _KEYS_BY_LEN.get(length, ()):
                if _levenshtein(n, key) == 1:
                    candidates.add(key)
                    if len(candidates) > 1:
                        break
            if len(candidates) > 1:
                break

        if len(candidates) == 1:
            match = next(iter(candidates))
            if _is_alif_hamza_only_diff(n, match):
                continue  # клавиатурное ограничение (алиф-с-хамзой), не ошибка
            findings.append((tok, _QURAN_INDEX[match][0]))

    return findings
