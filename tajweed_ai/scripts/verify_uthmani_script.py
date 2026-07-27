# -*- coding: utf-8 -*-
"""
Регрессионный тест на кейс группы 7 (27.07.2026, аят 2:45): студент прислал
муфрадат в кораническом (uthmani) написании (ٱسْتَعِينُوا۟, ٱلصَّلَوٰةِ),
скопированном из мусхаф-приложения. Индекс изначально строился только по
imlaey-написанию - оба слова не находились, ИИ получил повод "исправить"
их на несуществующие ошибки, а find_unconfirmed_words добавил ложное
"не найдено в тексте Корана". Фикс - core/quran_word_index.json теперь
индексирует ОБЕ формы (imlaey + uthmani), см.
tajweed_ai/scripts/build_quran_word_index.py.

Держим оба сценария в одном тесте: (1) слова из репорта находятся,
(2) существующий recall-кейс (Бекхан هلفهم) не сломан дублированием
индекса - см. историю в build_quran_word_index.py про إِيلَافِهِمْ/
إِۦلَـٰفِهِمْ (small yeh как замена буквы, а не украшение).
"""
import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from core.quran_ref import find_unconfirmed_words, strip_quran_confirmed_words, _normalize, _QURAN_INDEX

ok = True

# Дословный кусок репорта пользователя (группа 7, аят 2:45) - НЕ пересобран
# через quran_transcript, скопирован как есть из сообщения.
REPORT = """ ٱسْتَعِينُوا۟ — прибегайте к помощи / просите о помощи
 بِ — через / посредством
 ٱلصَّبْرِ — терпения
 وَ — и
 ٱلصَّلَوٰةِ — молитвы (намаза)
 وَإِنَّهَا — и воистину, она (молитва)
 لَكَبِيرَةٌ — действительно тяжка / велика
 إِلَّا — кроме как
 عَلَى — для
 ٱلْخَٰشِعِينَ — смиренных
 ٱلَّذِينَ — которы"""

AI_VERDICT = (
    "ٱسْتَعِينُوا۟ — не найдено в тексте Корана, ближайшее слово: اسْتَعِينُوا\n"
    "ٱلصَّلَوٰةِ — не найдено в тексте Корана, ближайшее слово: الصَّلَاةَ"
)

print("=== 1. Слова из репорта должны находиться в индексе ===")
for word in ("ٱسْتَعِينُوا۟", "ٱلصَّلَوٰةِ", "ٱلْخَٰشِعِينَ", "ٱلَّذِينَ"):
    n = _normalize(word)
    found = n in _QURAN_INDEX
    print(f"{word!r} -> {n!r} in_index={found}")
    if not found:
        ok = False

print("\n=== 2. find_unconfirmed_words не должен ничего находить в верном тексте ===")
findings = find_unconfirmed_words(REPORT)
print("findings:", findings)
if findings:
    ok = False

print("\n=== 3. Симуляция AI verdict (до фикса дал 2 фантомных 'не найдено') ===")
stripped = strip_quran_confirmed_words(AI_VERDICT, REPORT) or "ВЕРНО"
print("stripped:", repr(stripped))
if stripped != "ВЕРНО":
    ok = False

print("\n=== 4. Recall не сломан: реальная ошибка Бекхана (هلفهم) всё ещё однозначна ===")
n = _normalize("هلفهم")
candidates = set()
from core.quran_ref import _KEYS_BY_LEN, _levenshtein
for length in (len(n) - 1, len(n), len(n) + 1):
    for key in _KEYS_BY_LEN.get(length, ()):
        if _levenshtein(n, key) == 1:
            candidates.add(key)
print("candidates:", candidates)
if candidates != {"خلفهم"}:
    ok = False

print("\n" + "=" * 60)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
